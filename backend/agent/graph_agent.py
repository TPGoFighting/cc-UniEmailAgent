"""GraphAgent — LangGraph 状态机驱动层。

将 graph_builder 中的 LangGraph 有向图作为状态机引擎，
在节点间注入 ClaudeAgent 的实时流式执行（爬取阶段），
对外暴露与 HermesOrchestrator 完全兼容的接口。
"""

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from agent.claude_agent import ClaudeAgent
from agent.graph_builder import (
    CrawlState,
    plan_node,
    crawl_post_node,
    verify_node,
    export_node,
    route_after_plan,
    route_after_crawl,
    route_after_verify,
    build_graph,
)
from agent.tracing import create_run, end_run

logger = logging.getLogger(__name__)


class GraphAgent:
    """LangGraph 驱动的 Agent — 兼容 HermesOrchestrator 接口。

    职责:
    - execute(): 按 LangGraph 路由决策逐步执行 plan→crawl→verify→export
    - execute_query(): 简单问答委托给 ClaudeAgent
    - stop_task(): 中断正在执行的任务
    """

    def __init__(self):
        self._claude = ClaudeAgent()
        self._graph = build_graph()
        self._stopped_tasks: set[str] = set()

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def stop_task(self, task_id: str = "") -> bool:
        """中断指定任务的执行。"""
        self._stopped_tasks.add(task_id)
        return self._claude.stop_task(task_id)

    # ── 简单问答（委托给 ClaudeAgent） ──

    async def execute_query(
        self,
        message: str,
        task_id: str,
        task_output_dir: str = "",
    ) -> AsyncGenerator[dict, None]:
        """简单问答：直接委托给 ClaudeAgent，不经过爬取状态机。"""
        async for log in self._claude.execute_query(message, task_id, task_output_dir):
            yield log

    # ── 爬取编排（LangGraph 驱动） ──

    async def execute(
        self,
        message: str,
        task_id: str = "",
        intent_result=None,
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        """LangGraph 状态机编排执行。

        intent_result: intent_router 分类结果
        **kwargs: 兼容 HermesOrchestrator/ClaudeAgent 额外参数（忽略不使用）。
        """
        self._stopped_tasks.discard(task_id)

        uni_name = intent_result.university_name if intent_result else ""
        target_depts = intent_result.target_departments if intent_result else []

        run_id = create_run("graph_execute", {
            "task_id": task_id,
            "university": uni_name,
            "message": message[:200],
            "engine": "langgraph",
        })

        # ── 构建初始状态 ──
        state: CrawlState = {
            "task_id": task_id,
            "message": message,
            "university_name": uni_name,
            "target_departments": target_depts,
            "phase": "plan",
            "retry_count": 0,
            "error": "",
            "crawl_data": [],
            "quality_report": None,
            "output_files": [],
        }

        try:
            # ── 阶段 1: plan ──
            yield {
                "type": "log",
                "message": "系统分析中...",
                "timestamp": self._timestamp(),
            }

            plan_result = plan_node(state)
            state.update(plan_result)
            state["phase"] = route_after_plan(state)

            if state["phase"] == "complete":
                yield {
                    "type": "error",
                    "message": "无法识别目标大学，请检查任务描述",
                    "timestamp": self._timestamp(),
                }
                end_run(run_id, {"phase": "complete", "reason": "plan_failed"})
                yield {"type": "done", "message": "任务执行完毕", "timestamp": self._timestamp()}
                return

            # ── 主循环：按图路由逐步执行 ──
            _start_time = time.time()
            _MAX_TOTAL_SECONDS = 3600

            while state["phase"] != "complete":
                if task_id in self._stopped_tasks:
                    yield {
                        "type": "log",
                        "message": "任务已被手动终止",
                        "timestamp": self._timestamp(),
                    }
                    break

                if time.time() - _start_time > _MAX_TOTAL_SECONDS:
                    yield {
                        "type": "log",
                        "message": "任务运行超过 3600 秒，自动终止",
                        "timestamp": self._timestamp(),
                    }
                    break

                if state["phase"] == "crawl":
                    # ── 爬取阶段（流式执行 ClaudeAgent） ──
                    yield {
                        "type": "log",
                        "message": "开始采集数据...",
                        "timestamp": self._timestamp(),
                    }

                    crawl_data: list[dict] = []
                    try:
                        async for log in self._claude.execute(
                            state["message"],
                            task_id,
                            intent_result=intent_result,
                            is_crawl_session=True,
                        ):
                            crawl_data.append(log)
                            yield log
                    except Exception as e:
                        logger.error(f"crawl phase error: {e}")
                        yield {
                            "type": "error",
                            "message": f"爬取执行异常: {str(e)[:200]}",
                            "timestamp": self._timestamp(),
                        }

                    # 爬取完成 → 更新状态
                    state["crawl_data"] = crawl_data
                    state.update(crawl_post_node(state))
                    state["phase"] = route_after_crawl(state)

                elif state["phase"] == "verify":
                    # ── 验证阶段 ──
                    yield {
                        "type": "log",
                        "message": "验证数据质量...",
                        "timestamp": self._timestamp(),
                    }

                    verify_result = verify_node(state)
                    state.update(verify_result)
                    state["phase"] = route_after_verify(state)

                    report = state.get("quality_report") or {}
                    if report.get("warnings"):
                        for w in report["warnings"][:3]:
                            yield {
                                "type": "log",
                                "message": f"  {w}",
                                "timestamp": self._timestamp(),
                            }

                    if state["phase"] == "plan":
                        # 需要重试
                        state["retry_count"] += 1
                        retry = state["retry_count"]
                        yield {
                            "type": "log",
                            "message": f"质量验证未通过，第 {retry} 次重试...",
                            "timestamp": self._timestamp(),
                        }
                        plan_result = plan_node(state)
                        state.update(plan_result)
                        state["phase"] = route_after_plan(state)

                elif state["phase"] == "export":
                    # ── 导出阶段 ──
                    yield {
                        "type": "log",
                        "message": "导出结果文件...",
                        "timestamp": self._timestamp(),
                    }

                    export_result = export_node(state)
                    state.update(export_result)
                    state["phase"] = "complete"
                    break

                elif state["phase"] == "complete":
                    break

                else:
                    logger.warning(f"未知阶段: {state['phase']}")
                    break

            end_run(run_id, {
                "phase": state.get("phase", "unknown"),
                "retry_count": state.get("retry_count", 0),
                "quality_score": (state.get("quality_report") or {}).get("quality_score", 0),
                "files": len(state.get("output_files", [])),
            })

            yield {"type": "done", "message": "任务执行完毕", "timestamp": self._timestamp()}

        except Exception as e:
            logger.error(f"GraphAgent 执行异常: {e}")
            yield {
                "type": "error",
                "message": f"GraphAgent 异常: {str(e)[:300]}",
                "timestamp": self._timestamp(),
            }
            end_run(run_id, error=str(e)[:200])
            yield {"type": "done", "message": "任务执行完毕", "timestamp": self._timestamp()}
