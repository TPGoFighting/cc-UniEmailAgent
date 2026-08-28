"""Director Agent — 在进程内的 AI Agent 推理循环。

架构参考:
- PageAgent (alibaba/page-agent): Reflection-Before-Action 循环 + MacroTool 模式
- Claude Code (pengchengneo/Claude-Code): 工具注册/权限/进度事件系统

核心改进:
1. Step MacroTool — LLM 每次只调用一个"step"工具，强制 reflection 后行动
2. 活动事件 — 实时推送 thinking/executing/executed 到前端
3. Worker 进度 — 并行 Worker 每个步骤实时可见
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator

from .provider import LLMProvider, StreamEvent, create_provider
from .tool import Tool, ToolRegistry, ToolResult

logger = logging.getLogger(__name__)

# 最大推理轮次
MAX_TURNS = 50
# 无工具调用时的最长连续文本轮次
MAX_TEXT_TURNS = 3


class DirectorAgent:
    """Director Agent — 主 Agent 循环。

    采用 PageAgent 的 Reflection-Before-Action 模式：
    每步 LLM 必须输出:
    1. evaluation_previous_goal — 对上一轮的评价
    2. memory — 当前进展总结
    3. next_goal — 本轮目标
    4. action — 一个具体的工具调用

    工作流程:
    1. 构建消息列表（system + 历史 + 最新 tool_results）
    2. 调用 LLM（强制使用 "step" 工具）
    3. 解析 step 工具内部嵌套的真实工具调用
    4. 执行工具 → 结果追加到 context → 回到 2
    5. 无工具调用或达到上限 → 结束
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        task_id: str = "",
    ):
        self.provider = provider or create_provider()
        self.registry = ToolRegistry()
        self.messages: list[dict[str, Any]] = []
        self.task_id = task_id or f"agent-{uuid.uuid4().hex[:8]}"
        self._stop_requested = False
        self._start_time = 0.0
        self._tool_use_count = 0
        self._total_tokens = 0

        # 注册工具（传入 task_id 供 dispatch_workers 使用）
        from .tools import register_all_tools
        register_all_tools(self.registry, task_id=self.task_id)

    def stop(self):
        """请求停止当前任务。"""
        self._stop_requested = True
        logger.info(f"DirectorAgent {self.task_id} 停止请求已提交")

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    # ── 系统提示词构建 ──────────────────────────────────────────

    def _build_system_prompt(self, intent_result: Any = None, memory_context: str = "") -> str:
        """构建系统提示词（含 Reflection-Before-Action 约束）。"""
        intent_text = ""
        if intent_result:
            uni = getattr(intent_result, "university_name", None) or ""
            colleges = getattr(intent_result, "college_names", None) or ""
            intent_type = getattr(intent_result, "intent_type", "")
            intent_text = (
                f"\n## 当前任务上下文\n"
                f"- 意图类型: {intent_type}\n"
                f"- 目标大学: {uni}\n"
                f"- 目标学院: {colleges}\n"
            )

        system_prompt = f"""你是 UniEmail Agent，一个高校教师邮箱智能采集助手。

## 核心规则

1. **持续行动直到任务完成** — 不要提前汇报结果，必须爬取完所有数据再总结
2. **每轮只调一个工具**，不要同时发起多个调用
3. **行动前先思考**：在消息中说一句本轮目标，然后立刻调用工具
4. **失败就换方案**：搜索无结果就试直接 URL，访问失败就跳过

## 工作流程

1. **搜索目标** — 用 web_search 或 browser_navigate 找到大学官网
2. **找师资入口** — 在官网找到「师资队伍」「教师名录」或学院列表页
3. **爬取数据** — 进入学院师资页面，提取教师姓名、职称、邮箱
4. **保存 CSV** — 使用 file_write 保存 csv 到 outputs/ 目录
5. **汇报结果** — 总结爬取了多少教师和邮箱

## 爬取技巧

- **优先用 web_fetch（HTTP）而非 browser_navigate**，速度更快
- 只有 web_fetch 拿不到动态内容时才用 browser_navigate
- 拿到页面后用浏览器提取 email 或 file_write 保存 CSV
- **2 个以上学院用 dispatch_workers 并行爬取**
- CSV 列名: 姓名、职称、邮箱、学院、来源
- 要获取邮箱必须访问教师个人详情页，列表页一般没有邮箱
- 过滤 admin@、webmaster@ 等公共邮箱
- 搜索失败时直接试: cs.{{大学拼音}}.edu.cn, cse.{{大学拼音}}.edu.cn, teacher.{{大学拼音}}.edu.cn

## 输出要求

- 用中文自然语言回复
- 关键进度用 emoji 标记
- 不要输出技术细节（文件路径、工具名、exit code 等）
- 每轮输出简洁，控制在 2-3 行{intent_text}

## 任务信息
- 任务 ID: {self.task_id}
- 输出目录: outputs/{self.task_id}/
- 最大轮次: {MAX_TURNS}
"""
        if memory_context:
            system_prompt += f"\n## 🧠 历史经验参考\n\n以下是从过往任务中提取的相关经验，请仔细阅读并应用到本次任务中：\n\n{memory_context}\n"
        return system_prompt.strip()

    # ── 主执行循环 ────────────────────────────────────────────────

    async def execute(
        self,
        user_message: str,
        task_id: str = "",
        intent_result=None,
        is_continuation: bool = False,
        is_crawl_session: bool = True,
        memory_context: str = "",
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        """执行任务。

        Yields:
            dict 事件:
              - text / log / download / done / error (同前)
              - activity: {type: "thinking"|"executing"|"executed", ...}
              - worker_progress: {name, status, found, emails, error}
        """
        if task_id:
            self.task_id = task_id

        self._stop_requested = False
        self._start_time = time.time()
        self._tool_use_count = 0
        self._total_tokens = 0

        yield {"type": "log", "message": "🚀 Director Agent 启动（Reflection 模式）",
               "timestamp": self._timestamp()}
        logger.info(f"[Director] 任务开始: {self.task_id}")

        # 构建 system prompt + 初始消息
        system_prompt = self._build_system_prompt(intent_result, memory_context)
        self.messages = [{"role": "system", "content": system_prompt}]
        self.messages.append({"role": "user", "content": user_message})

        # 非爬取任务：简洁问答
        if not is_crawl_session:
            async for event in self._run_conversational():
                yield event
            return

        # 为 dispatch_workers 工具注入进度回调 → 转发为 activity/worker_progress 事件
        await self._wire_dispatch_progress()

        # ── 主循环（Reflection-Before-Action） ──
        consecutive_text_replies = 0

        for turn in range(MAX_TURNS):
            if self._stop_requested:
                yield {"type": "log", "message": "⏹️ 用户已请求停止",
                       "timestamp": self._timestamp()}
                break

            # 连续文本轮次检测
            if turn > 0 and consecutive_text_replies >= MAX_TEXT_TURNS:
                yield {"type": "log",
                       "message": f"✅ 连续 {MAX_TEXT_TURNS} 轮无工具调用",
                       "timestamp": self._timestamp()}
                break

            # ── 发送 thinking 活动事件 ──
            yield {"type": "activity", "activity": {"type": "thinking"},
                   "timestamp": self._timestamp()}

            # ── 调用 LLM（正常工具列表，auto tool_choice） ──
            text_chunks: list[str] = []
            tool_calls_collected: list[dict] = []
            saw_error = False

            async for event in self._call_llm(
                tools=None,  # 使用 registry 中所有已注册工具
                tool_choice="auto",
                temperature=0.3 if turn > 0 else 0.5,
            ):
                if event.type == "text":
                    text_chunks.append(event.content)
                    yield {"type": "text", "message": event.content,
                           "timestamp": self._timestamp()}

                elif event.type == "tool_use":
                    tool_calls_collected.append({
                        "id": event.tool_call_id,
                        "type": "function",
                        "function": {
                            "name": event.tool_name,
                            "arguments": json.dumps(event.tool_input or {}, ensure_ascii=False),
                        },
                    })
                    # 发送 executing 活动事件
                    yield {"type": "activity", "activity": {
                        "type": "executing",
                        "tool": event.tool_name,
                        "input": event.tool_input,
                    }, "timestamp": self._timestamp()}
                    logger.info(
                        f"[Director] 工具调用 #{self._tool_use_count + 1}: "
                        f"{event.tool_name}({json.dumps(event.tool_input, ensure_ascii=False)[:150]})"
                    )

                elif event.type == "error":
                    saw_error = True
                    yield {"type": "error", "message": f"LLM 错误: {event.content}",
                           "timestamp": self._timestamp()}

                elif event.type == "done" and event.usage:
                    self._total_tokens += (event.usage.prompt_tokens or 0) + (event.usage.completion_tokens or 0)

            if saw_error:
                break

            full_text = "".join(text_chunks)

            # 将 assistant 消息追加到对话上下文
            assistant_msg: dict[str, Any] = {"role": "assistant"}
            if tool_calls_collected:
                assistant_msg["content"] = full_text or ""
                assistant_msg["tool_calls"] = tool_calls_collected
            else:
                assistant_msg["content"] = full_text
            self.messages.append(assistant_msg)

            # 执行工具
            if tool_calls_collected:
                consecutive_text_replies = 0
                self._tool_use_count += len(tool_calls_collected)

                for tc in tool_calls_collected:
                    if self._stop_requested:
                        break

                    tool_name = tc["function"]["name"]
                    tool_input = tc["function"]["arguments"]

                    if isinstance(tool_input, str):
                        try:
                            tool_input = json.loads(tool_input)
                        except json.JSONDecodeError:
                            tool_input = {}
                        tc["function"]["arguments"] = tool_input  # 更新为 dict

                    # 执行真实工具
                    result = await self._execute_tool(tool_name, tool_input, tc["id"])

                    result_data = result.data[:800]

                    # 重要：DeepSeek 要求 arguments 是 JSON 字符串，不能是 dict
                    tc["function"]["arguments"] = json.dumps(tool_input, ensure_ascii=False)

                    # 将 tool_result 追加到上下文
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result_data,
                    })

                    # ── 发送 executed 活动事件 ──
                    yield {"type": "activity", "activity": {
                        "type": "executed",
                        "tool": tool_name,
                        "summary": result_data[:150],
                    }, "timestamp": self._timestamp()}

                    # 输出摘要
                    yield {"type": "log",
                           "message": f"📋 {tool_name}: {result_data[:200]}",
                           "timestamp": self._timestamp()}

                    # flush dispatch_workers 进度事件
                    if tool_name == "dispatch_workers" and self._dispatch_events:
                        for evt in self._dispatch_events:
                            yield evt
                        self._dispatch_events.clear()

                    # 文件通知
                    for fp in result.files_created:
                        fpath = Path(fp)
                        yield {
                            "type": "download",
                            "message": f"📄 {fpath.name}",
                            "filename": fpath.name,
                            "url": f"/api/download/{self.task_id}/{fpath.name}",
                            "timestamp": self._timestamp(),
                        }
            else:
                consecutive_text_replies += 1

            # 无文本也无工具调用 → 结束
            if not full_text and not tool_calls_collected:
                break

        # ── 结束 ──
        duration = time.time() - self._start_time
        yield {
            "type": "done",
            "message": (
                f"✅ 任务完成\n"
                f"- 轮次: {turn + 1} | 工具调用: {self._tool_use_count} 次\n"
                f"- 耗时: {duration:.0f}s | Token: {self._total_tokens}"
            ),
            "timestamp": self._timestamp(),
        }
        logger.info(
            f"[Director] 任务结束: {self.task_id}, "
            f"耗时={duration:.0f}s, 工具={self._tool_use_count}, Token={self._total_tokens}"
        )

    # ── Worker 进度转发 ──────────────────────────────────────────

    async def _wire_dispatch_progress(self):
        """连接 dispatch_workers 的进度回调。"""
        self._dispatch_events: list[dict] = []

        dispatch_tool = self.registry.get("dispatch_workers")
        if dispatch_tool and hasattr(dispatch_tool, "_progress_callback"):
            async def _on_worker_progress(name: str, status: str, found: int, emails: int, error: str):
                event = {
                    "type": "worker_progress",
                    "worker_progress": {
                        "name": name,
                        "status": status,
                        "found": found,
                        "emails": emails,
                        "error": error,
                    },
                    "timestamp": self._timestamp(),
                }
                self._dispatch_events.append(event)
            dispatch_tool._progress_callback = _on_worker_progress

    # ── 对话模式 ──────────────────────────────────────────────────

    async def _run_conversational(self) -> AsyncGenerator[dict, None]:
        """简洁对话模式（无工具调用）。"""
        text_parts: list[str] = []
        async for event in self._call_llm(temperature=0.7, max_tokens=1024):
            if event.type == "text":
                text_parts.append(event.content)
                yield {"type": "text", "message": event.content,
                       "timestamp": self._timestamp()}
            elif event.type == "done" and event.usage:
                self._total_tokens = (event.usage.prompt_tokens or 0) + (event.usage.completion_tokens or 0)

        self.messages.append({"role": "assistant", "content": "".join(text_parts)})
        yield {"type": "done", "message": "回答完毕", "timestamp": self._timestamp()}

    # ── LLM 调用 ──────────────────────────────────────────────────

    async def _call_llm(
        self, temperature: float = 0.3, max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """调用 LLM 流式 API。

        Args:
            tools: 工具描述列表（传入 step_tool 时覆盖 registry）
            tool_choice: 工具选择策略
        """
        if tools is None:
            tools = self.registry.to_openai_tools()

        try:
            async for event in self.provider.chat_stream(
                messages=self.messages,
                tools=tools if tools else None,
                temperature=temperature,
                max_tokens=max_tokens,
                tool_choice=tool_choice,
            ):
                if self._stop_requested:
                    break
                yield event

        except Exception as e:
            logger.error(f"LLM 调用失败: {e}", exc_info=True)
            yield StreamEvent(type="error", content=str(e))

    # ── 工具执行 ──────────────────────────────────────────────────

    async def _execute_tool(
        self, tool_name: str, tool_input: dict[str, Any], tool_call_id: str,
    ) -> ToolResult:
        """执行工具。"""
        tool = self.registry.get(tool_name)
        if not tool:
            return ToolResult(data=f"❌ 未知工具: {tool_name}")

        try:
            validated = tool.validate(tool_input)
            result = await tool.call(validated)
            return result
        except ValueError as e:
            return ToolResult(data=f"❌ 参数错误: {e}")
        except Exception as e:
            logger.error(f"工具 '{tool_name}' 执行失败: {e}", exc_info=True)
            return ToolResult(data=f"❌ 工具异常: {str(e)[:300]}")
