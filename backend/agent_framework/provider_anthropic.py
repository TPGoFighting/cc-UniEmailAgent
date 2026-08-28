"""Anthropic Claude API Provider — 支持 Messages API + Tool Use。

参考 Claude Code 的 tool_use block 设计，和 Anthropic 原生工具调用格式。
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator

from .provider import LLMProvider, ProviderConfig, StreamEvent, Usage

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """Anthropic Claude Messages API Provider。"""

    API_VERSION = "2023-06-01"

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        signal=None,
    ) -> AsyncGenerator[StreamEvent, None]:
        import httpx

        # 转换消息格式：OpenAI → Anthropic
        anthropic_messages = self._convert_messages(messages)
        system_prompt = self._extract_system(messages)

        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }

        body: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": anthropic_messages,
            "stream": True,
        }

        # 添加 system prompt（Anthropic 的 system 是顶层参数）
        if system_prompt:
            body["system"] = system_prompt

        # 添加工具定义
        if tools:
            # 转换 OpenAI 格式 → Anthropic 格式
            anthropic_tools = []
            for tool in tools:
                if tool.get("type") == "function":
                    fn = tool.get("function", {})
                    anthropic_tools.append({
                        "name": fn.get("name", ""),
                        "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters", {}),
                    })
            if anthropic_tools:
                body["tools"] = anthropic_tools

        base_url = self.config.base_url.rstrip("/")
        url = f"{base_url}/v1/messages"

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", url, headers=headers, json=body) as resp:
                    if resp.status_code != 200:
                        error_text = await resp.aread()
                        logger.error(f"Anthropic API error {resp.status_code}: {error_text}")
                        yield StreamEvent(type="error", content=f"API {resp.status_code}: {error_text[:500]}")
                        return

                    # 流式解析 SSE
                    tool_use_buffers: dict[int, dict[str, Any]] = {}
                    current_block_index = 0
                    content_block_type = ""

                    async for line in resp.aiter_lines():
                        if signal and hasattr(signal, "is_set") and signal.is_set():
                            break

                        if not line.startswith("data:"):
                            continue

                        data_str = line[5:].strip()
                        if not data_str or data_str == "[DONE]":
                            continue

                        try:
                            event = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        event_type = event.get("type", "")

                        if event_type == "message_start":
                            # 消息开始
                            msg = event.get("message", {})
                            usage_data = msg.get("usage", {})
                            if usage_data:
                                yield StreamEvent(type="done", usage=Usage(
                                    prompt_tokens=usage_data.get("input_tokens", 0),
                                    completion_tokens=usage_data.get("output_tokens", 0),
                                    total_tokens=usage_data.get("input_tokens", 0) + usage_data.get("output_tokens", 0),
                                ))

                        elif event_type == "content_block_start":
                            block = event.get("content_block", {})
                            current_block_index = event.get("index", 0)
                            content_block_type = block.get("type", "")
                            if content_block_type == "tool_use":
                                tool_use_buffers[current_block_index] = {
                                    "name": block.get("name", ""),
                                    "input": "",
                                    "id": block.get("id", ""),
                                }

                        elif event_type == "content_block_delta":
                            delta = event.get("delta", {})
                            delta_type = delta.get("type", "")
                            idx = event.get("index", 0)

                            if delta_type == "text_delta":
                                yield StreamEvent(type="text", content=delta.get("text", ""))

                            elif delta_type == "input_json_delta":
                                if idx in tool_use_buffers:
                                    tool_use_buffers[idx]["input"] += delta.get("partial_json", "")

                        elif event_type == "content_block_stop":
                            if current_block_index in tool_use_buffers:
                                buf = tool_use_buffers.pop(current_block_index)
                                try:
                                    args = json.loads(buf["input"]) if buf["input"] else {}
                                except json.JSONDecodeError:
                                    args = {"raw": buf["input"]}
                                yield StreamEvent(
                                    type="tool_use",
                                    tool_name=buf["name"],
                                    tool_input=args,
                                    tool_call_id=buf["id"],
                                    index=current_block_index,
                                )

                        elif event_type == "message_delta":
                            usage_data = event.get("usage", {})
                            if usage_data:
                                yield StreamEvent(type="done", usage=Usage(
                                    prompt_tokens=0,
                                    completion_tokens=usage_data.get("output_tokens", 0),
                                    total_tokens=usage_data.get("output_tokens", 0),
                                ))
                                return

                        elif event_type == "message_stop":
                            if not tool_use_buffers:
                                yield StreamEvent(type="done")

                        elif event_type == "error":
                            error_data = event.get("error", {})
                            yield StreamEvent(type="error", content=str(error_data.get("message", "")))

            yield StreamEvent(type="done")

        except Exception as e:
            logger.error(f"Anthropic API 调用失败: {e}", exc_info=True)
            yield StreamEvent(type="error", content=str(e))

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> tuple[str, list[dict[str, Any]], Usage]:
        """非流式：收集所有事件后返回。"""
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        final_usage = Usage()

        async for event in self.chat_stream(messages, tools, temperature, max_tokens):
            if event.type == "text":
                text_parts.append(event.content)
            elif event.type == "tool_use":
                tool_calls.append({
                    "id": event.tool_call_id,
                    "type": "function",
                    "function": {
                        "name": event.tool_name,
                        "arguments": event.tool_input or {},
                    },
                })
            elif event.type == "done" and event.usage:
                final_usage = event.usage

        return "".join(text_parts), tool_calls, final_usage

    # ── 辅助方法 ──

    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """将 OpenAI 格式消息转为 Anthropic 格式。"""
        result: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                continue  # system 在 Anthropic 中是顶层参数
            elif role == "tool":
                result.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.get("tool_call_id", ""),
                            "content": content,
                        }
                    ],
                })
            elif role == "assistant":
                content_blocks: list[dict] = []
                if content:
                    content_blocks.append({"type": "text", "text": content})
                for tc in msg.get("tool_calls", []):
                    try:
                        args = tc.get("function", {}).get("arguments", {})
                        if isinstance(args, str):
                            args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": tc.get("function", {}).get("name", ""),
                        "input": args,
                    })
                result.append({"role": "assistant", "content": content_blocks})
            else:
                result.append({"role": role, "content": content})

        return result

    def _extract_system(self, messages: list[dict[str, Any]]) -> str:
        """提取 system prompt。"""
        parts: list[str] = []
        for msg in messages:
            if msg.get("role") == "system":
                content = msg.get("content", "")
                if content:
                    parts.append(content if isinstance(content, str) else str(content))
        return "\n\n".join(parts)
