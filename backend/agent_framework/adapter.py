"""适配器 — 将 DirectorAgent 包装为现有 Agent 接口。

使 main.py 可以无缝替换 HermesAgent。
暴露相同的 execute() / stop_task() / execute_query() 接口。
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, AsyncGenerator

from .director import DirectorAgent
from .provider import create_provider

# 记忆系统导入（可选，失败时静默降级）
try:
    from agent.skill_manager import load_skills_prompt
    from agent.memory import search_mem0
    _HAS_MEMORY = True
except ImportError:
    _HAS_MEMORY = False
    load_skills_prompt = None
    search_mem0 = None

logger = logging.getLogger(__name__)


class DirectorAgentAdapter:
    """适配器：DirectorAgent → 原有 Agent 接口。

    接口兼容:
    - execute(message, task_id, ...) -> AsyncGenerator[dict]
    - execute_query(message, task_id, ...) -> AsyncGenerator[dict]
    - stop_task(task_id) -> bool
    """

    def __init__(self):
        self._active_directors: dict[str, DirectorAgent] = {}
        self._active_tasks: dict[str, asyncio.Task] = {}

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def stop_task(self, task_id: str) -> bool:
        """终止正在运行的任务。"""
        # 通知 Director 停止
        director = self._active_directors.get(task_id)
        if director:
            director.stop()
            logger.info(f"DirectorAgent {task_id} 停止信号已发送")

        # 取消 asyncio task
        task = self._active_tasks.pop(task_id, None)
        if task and not task.done():
            task.cancel()
            logger.info(f"DirectorAgent {task_id} 异步任务已取消")
            return True
        return bool(director)

    async def execute(
        self,
        message: str,
        task_id: str = "",
        is_continuation: bool = False,
        is_crawl_session: bool = True,
        current_user_message: str | None = None,
        intent_result=None,
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        """执行任务。"""
        provider = create_provider()

        # 检查 API Key
        import os
        has_key = bool(os.environ.get("DEEPSEEK_API_KEY") or
                       os.environ.get("OPENAI_API_KEY") or
                       os.environ.get("ANTHROPIC_API_KEY"))

        if not has_key:
            yield {
                "type": "error",
                "message": (
                    "❌ 未配置 API Key\n\n"
                    "请在 `backend/.env` 中配置以下任一环境变量:\n"
                    "- `DEEPSEEK_API_KEY`（推荐，国内直连速度快）\n"
                    "- `OPENAI_API_KEY`\n"
                    "- `ANTHROPIC_API_KEY`\n\n"
                    "配置后可享用毫秒级流式 AI Agent 响应！"
                ),
                "timestamp": self._timestamp(),
            }
            yield {"type": "done", "message": "无 API Key", "timestamp": self._timestamp()}
            return

        if not task_id:
            import uuid
            task_id = f"director-{uuid.uuid4().hex[:8]}"

        # ── 前置记忆加载：从文件技能库 + Mem0 向量库获取历史经验 ──
        memory_context = ""
        if _HAS_MEMORY and is_crawl_session and intent_result:
            uni_name = getattr(intent_result, "university_name", "") or ""
            try:
                parts: list[str] = []
                if uni_name and load_skills_prompt:
                    skill_text = load_skills_prompt(uni_name)
                    if skill_text:
                        parts.append(skill_text)
                if uni_name and search_mem0:
                    mem0_text = search_mem0(message[:200], uni_name)
                    if mem0_text:
                        parts.append(mem0_text)
                if parts:
                    memory_context = "\n\n---\n\n".join(parts)
                    logger.info(
                        f"[Memory] 已加载 {len(parts)} 个记忆来源"
                        f"（大学={uni_name}, 总长={len(memory_context)}）"
                    )
            except Exception as e:
                logger.warning(f"[Memory] 前置加载失败（不影响任务）: {e}")

        director = DirectorAgent(provider=provider, task_id=task_id)
        self._active_directors[task_id] = director

        # 在异步任务中执行
        async def _run():
            async for log in director.execute(
                user_message=message,
                task_id=task_id,
                intent_result=intent_result,
                is_continuation=is_continuation,
                is_crawl_session=is_crawl_session,
                memory_context=memory_context,
            ):
                yield log
            self._active_directors.pop(task_id, None)
            self._active_tasks.pop(task_id, None)

        try:
            async for log in _run():
                yield log
        except asyncio.CancelledError:
            yield {"type": "log", "message": "任务已取消", "timestamp": self._timestamp()}
        except Exception as e:
            logger.error(f"DirectorAgent 执行异常: {e}", exc_info=True)
            yield {"type": "error", "message": f"执行异常: {str(e)[:200]}",
                   "timestamp": self._timestamp()}
        finally:
            self._active_directors.pop(task_id, None)

    async def execute_query(
        self,
        message: str,
        task_id: str,
        task_output_dir: str = "",
    ) -> AsyncGenerator[dict, None]:
        """简单问答（非爬取任务）。"""
        provider = create_provider()
        director = DirectorAgent(provider=provider, task_id=task_id)

        yield {"type": "log", "message": "💬 分析中...", "timestamp": self._timestamp()}

        async for log in director.execute(
            user_message=message,
            task_id=task_id,
            is_crawl_session=False,
        ):
            yield log
