"""LLM Provider 统一接口 — 封装 DeepSeek / OpenAI / Anthropic API 调用。

支持：
- 流式输出（text chunks + tool_use deltas）
- 工具调用（function calling / tool_use blocks）
- 多 provider 自动切换
- Token 用量追踪
"""

from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 消息类型定义
# ═══════════════════════════════════════════════════════════════

@dataclass
class Message:
    """对话消息。"""
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | list[dict[str, Any]] = ""
    tool_calls: list[dict[str, Any]] | None = None  # assistant 消息的工具调用
    tool_call_id: str | None = None  # tool 消息的工具调用 ID
    name: str | None = None  # tool 消息的工具名称

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role}
        if self.role == "tool":
            d["tool_call_id"] = self.tool_call_id
            d["name"] = self.name
            d["content"] = self.content if isinstance(self.content, str) else json.dumps(self.content, ensure_ascii=False)
        elif self.role == "assistant" and self.tool_calls:
            d["content"] = self.content or ""
            d["tool_calls"] = self.tool_calls
        else:
            d["content"] = self.content
        return d


@dataclass
class ProviderConfig:
    """Provider 配置。"""
    api_key: str = ""
    base_url: str = ""
    model: str = ""


@dataclass
class Usage:
    """Token 用量。"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class StreamEvent:
    """流式事件——统一所有 provider 的输出格式。"""
    type: str  # "text" | "tool_use" | "tool_result" | "done" | "error"
    content: str = ""  # text 片段
    tool_name: str = ""  # 工具名称（tool_use 时）
    tool_input: dict[str, Any] | None = None  # 工具参数（tool_use 时）
    tool_call_id: str = ""  # 工具调用 ID
    index: int = 0  # 工具调用序号
    usage: Usage | None = None  # 最终用量

    def to_json(self) -> str:
        return json.dumps({
            "type": self.type,
            "content": self.content,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_call_id": self.tool_call_id,
            "index": self.index,
            "usage": {
                "prompt_tokens": self.usage.prompt_tokens if self.usage else 0,
                "completion_tokens": self.usage.completion_tokens if self.usage else 0,
                "total_tokens": self.usage.total_tokens if self.usage else 0,
            } if self.usage else None,
        }, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# Provider 抽象基类
# ═══════════════════════════════════════════════════════════════

class LLMProvider(ABC):
    """LLM Provider 抽象基类。"""

    def __init__(self, config: ProviderConfig | None = None):
        self.config = config or ProviderConfig()

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        signal=None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """流式聊天。tools 为 OpenAI 格式的工具定义列表。

        Args:
            tool_choice: 工具选择策略。None 或 "auto" 让模型自行决定，
                        "any" 或 "required" 强制调工具，
                        {"type": "function", "function": {"name": "xxx"}} 强制调指定工具。
        """
        ...  # pragma: no cover

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> tuple[str, list[dict[str, Any]], Usage]:
        """非流式聊天。返回 (文本内容, 工具调用列表, 用量)。"""
        ...  # pragma: no cover


# ═══════════════════════════════════════════════════════════════
# OpenAI / DeepSeek 兼容 Provider
# ═══════════════════════════════════════════════════════════════

class OpenAILikeProvider(LLMProvider):
    """兼容 OpenAI / DeepSeek / 任何 OpenAI 兼容 API 的 Provider。"""

    SUPPORTED_MODELS = {
        "deepseek-chat": "DeepSeek V3",
        "deepseek-reasoner": "DeepSeek R1",
        "deepseek/deepseek-v4-flash": "DeepSeek V4 Flash",
        "gpt-4o": "GPT-4o",
        "gpt-4o-mini": "GPT-4o Mini",
        "gpt-4": "GPT-4 Turbo",
    }

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        signal=None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = tools
            # tool_choice 优先：None/"auto"/"any"/"required"/{"type":"function","function":{"name":"xxx"}}
            if tool_choice is not None:
                kwargs["tool_choice"] = tool_choice
            else:
                kwargs["tool_choice"] = "auto"

        try:
            stream = await client.chat.completions.create(**kwargs)
            tool_call_buffers: dict[int, dict[str, Any]] = {}

            async for chunk in stream:
                if signal and hasattr(signal, "is_set") and signal.is_set():
                    break

                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    # 用量信息（最后一个 chunk）
                    if chunk.usage:
                        yield StreamEvent(
                            type="done",
                            usage=Usage(
                                prompt_tokens=chunk.usage.prompt_tokens or 0,
                                completion_tokens=chunk.usage.completion_tokens or 0,
                                total_tokens=(chunk.usage.prompt_tokens or 0) + (chunk.usage.completion_tokens or 0),
                            ),
                        )
                    continue

                # 文本 delta
                if delta.content:
                    yield StreamEvent(type="text", content=delta.content)

                # 工具调用 delta（流式）
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_call_buffers:
                            tool_call_buffers[idx] = {
                                "id": tc.id or "",
                                "function": {"name": "", "arguments": ""},
                                "type": "function",
                            }
                        buf = tool_call_buffers[idx]
                        if tc.id:
                            buf["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                buf["function"]["name"] += tc.function.name
                            if tc.function.arguments:
                                buf["function"]["arguments"] += tc.function.arguments

                # finish_reason: 返回完整工具调用
                # DeepSeek 有时用 "stop" 代替 "tool_calls"，所以只要 buffer 非空就 flush
                if chunk.choices and chunk.choices[0].finish_reason:
                    reason = chunk.choices[0].finish_reason
                    if tool_call_buffers and reason in ("tool_calls", "stop", "length"):
                        for idx in sorted(tool_call_buffers.keys()):
                            tc = tool_call_buffers[idx]
                            try:
                                args = json.loads(tc["function"]["arguments"])
                            except json.JSONDecodeError:
                                args = {}
                            yield StreamEvent(
                                type="tool_use",
                                tool_name=tc["function"]["name"],
                                tool_input=args,
                                tool_call_id=tc["id"],
                                index=idx,
                            )
                        tool_call_buffers.clear()

            # 如果 stream 结束但没用 usage chunk，发 done
            yield StreamEvent(type="done")

        except Exception as e:
            logger.error(f"OpenAI/DeepSeek API 调用失败: {e}", exc_info=True)
            yield StreamEvent(type="error", content=str(e))

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> tuple[str, list[dict[str, Any]], Usage]:
        """非流式调用。"""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        resp = await client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        text = choice.message.content or ""

        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": args,
                    },
                })

        usage = Usage(
            prompt_tokens=resp.usage.prompt_tokens or 0 if resp.usage else 0,
            completion_tokens=resp.usage.completion_tokens or 0 if resp.usage else 0,
            total_tokens=(resp.usage.prompt_tokens or 0) + (resp.usage.completion_tokens or 0) if resp.usage else 0,
        )

        return text, tool_calls, usage


# ═══════════════════════════════════════════════════════════════
# Provider 工厂
# ═══════════════════════════════════════════════════════════════

def create_provider() -> LLMProvider:
    """从环境变量自动创建合适的 Provider。

    优先级: DeepSeek → OpenAI → Anthropic
    """
    # 尝试 DeepSeek
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if api_key:
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
        model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        return OpenAILikeProvider(ProviderConfig(
            api_key=api_key,
            base_url=base_url,
            model=model,
        ))

    # 尝试 OpenAI
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        base_url = os.environ.get("OPENAI_BASE_URL", "")
        model = os.environ.get("OPENAI_API_MODEL", "gpt-4o-mini")
        return OpenAILikeProvider(ProviderConfig(
            api_key=api_key,
            base_url=base_url,
            model=model,
        ))

    # 尝试 Anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        from .provider_anthropic import AnthropicProvider
        model = os.environ.get("ANTHROPIC_API_MODEL", "claude-sonnet-4-20250514")
        return AnthropicProvider(ProviderConfig(
            api_key=api_key,
            base_url=os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
            model=model,
        ))

    logger.warning("未配置任何 API Key，创建空 Provider")
    return OpenAILikeProvider(ProviderConfig(
        api_key="no-key",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
    ))
