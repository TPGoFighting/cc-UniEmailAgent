"""Worker Agent — 子任务执行器（多 Agent 并行）。

参考 Claude Code 的 Coordinator + AgentTool 模式：
- Director Agent 负责任务拆解和协调
- Worker Agent 负责执行具体的子任务（如单个学院的爬取）
- 多个 Worker 可以并行执行

每个 Worker 拥有独立的：
- LLM Provider
- 工具注册中心（可选限制工具集）
- 对话上下文
- 任务 ID
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator

from .provider import LLMProvider, StreamEvent, create_provider
from .tool import ToolRegistry, ToolResult
from .tools import register_all_tools

logger = logging.getLogger(__name__)

MAX_WORKER_TURNS = 20


class WorkerAgent:
    """Worker Agent — 独立执行子任务。

    由 Director Agent 创建，处理一个具体的子任务（如爬取某个学院）。
    完成后返回结构化结果给 Director。
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        worker_id: str = "",
        parent_task_id: str = "",
        restricted_tools: list[str] | None = None,
    ):
        self.provider = provider or create_provider()
        self.registry = ToolRegistry()

        # 注册工具（可以限制工具集）
        register_all_tools(self.registry)
        if restricted_tools:
            all_tools = self.registry.get_all()
            for t in all_tools:
                if t.name not in restricted_tools:
                    self.registry.unregister(t.name)

        self.messages: list[dict[str, Any]] = []
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.parent_task_id = parent_task_id
        self._stop_requested = False
        self._start_time = 0.0
        self._tool_use_count = 0

    def stop(self):
        self._stop_requested = True

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _build_system_prompt(self, task_context: str) -> str:
        """构建 Worker 的系统提示。"""
        tool_names = self.registry.get_names()
        return f"""你是一个 Worker Agent，负责执行特定的子任务。

## 你的任务
{task_context}

## 可用工具
{', '.join(tool_names)}

## 规则
- 专注于完成分配的子任务
- 使用工具与外界交互
- 最终给出明确的结果报告
- 不要尝试做任务范围之外的事情

Worker ID: {self.worker_id}
父任务: {self.parent_task_id}
最大轮次: {MAX_WORKER_TURNS}"""

    async def execute(
        self,
        task_prompt: str,
        task_context: str = "",
    ) -> tuple[str, dict[str, Any]]:
        """执行子任务。返回 (最终文本, 元数据)。"""
        self._stop_requested = False
        self._start_time = datetime.now()
        self._tool_use_count = 0

        system_prompt = self._build_system_prompt(task_context)
        self.messages = [{"role": "system", "content": system_prompt}]
        self.messages.append({"role": "user", "content": task_prompt})

        final_text: list[str] = []
        tool_results_data: list[dict] = []
        consecutive_text = 0

        for turn in range(MAX_WORKER_TURNS):
            if self._stop_requested:
                break

            if turn > 0 and consecutive_text >= 2:
                break

            text_chunks: list[str] = []
            tool_calls: list[dict] = []

            try:
                async for event in self.provider.chat_stream(
                    messages=self.messages,
                    tools=self.registry.to_openai_tools() or None,
                    temperature=0.3,
                    max_tokens=4096,
                ):
                    if self._stop_requested:
                        break
                    if event.type == "text":
                        text_chunks.append(event.content)
                    elif event.type == "tool_use":
                        tool_calls.append({
                            "id": event.tool_call_id,
                            "type": "function",
                            "function": {
                                "name": event.tool_name,
                                "arguments": json.dumps(event.tool_input or {}, ensure_ascii=False),
                            },
                        })
            except Exception as e:
                logger.error(f"Worker LLM 调用失败: {e}")
                break

            full_text = "".join(text_chunks)

            # 记录 assistant 消息
            assistant_msg: dict[str, Any] = {"role": "assistant"}
            if tool_calls:
                assistant_msg["content"] = full_text or ""
                assistant_msg["tool_calls"] = tool_calls
            else:
                assistant_msg["content"] = full_text
            self.messages.append(assistant_msg)

            if tool_calls:
                consecutive_text = 0
                self._tool_use_count += len(tool_calls)

                for tc in tool_calls:
                    tool_name = tc["function"]["name"]
                    tool_input = tc["function"]["arguments"]

                    # arguments 可能是 JSON 字符串，需解析为字典
                    if isinstance(tool_input, str):
                        try:
                            tool_input = json.loads(tool_input)
                        except json.JSONDecodeError:
                            tool_input = {}

                    tool_obj = self.registry.get(tool_name)

                    if not tool_obj:
                        result_str = f"❌ 未知工具: {tool_name}"
                    else:
                        try:
                            validated = tool_obj.validate(tool_input)
                            result = await tool_obj.call(validated)
                            result_str = result.data[:500]
                            tool_results_data.append({
                                "tool": tool_name,
                                "input": tool_input,
                                "result": result.data[:200],
                                "files": result.files_created,
                            })
                        except Exception as e:
                            result_str = f"❌ 工具错误: {e}"

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": tool_name,
                        "content": result_str,
                    })

                final_text.extend(text_chunks)
            else:
                consecutive_text += 1
                final_text.append(full_text)

        result_text = "".join(final_text).strip()
        return result_text or "（无输出）", {
            "worker_id": self.worker_id,
            "turns": turn + 1,
            "tool_uses": self._tool_use_count,
            "tool_results": tool_results_data,
        }
