"""并行派发工具 — 将多个子任务同时分发给 Worker 并行执行。

Director Agent 在发现多个学院需要爬取时，调用此工具：
1. 将学院列表拆分为独立子任务
2. 每个子任务由一个 Worker Agent 独立处理
3. 多个 Worker 通过 asyncio.gather 并行执行
4. 汇总所有 Worker 的结果返回给 Director

Worker 工具有限（think + web_fetch + file_write），避免浏览器冲突。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Callable, Coroutine

from ..tool import Tool, ToolResult

logger = logging.getLogger(__name__)


class DispatchWorkersTool(Tool):
    """并行派发多个 Worker Agent 分别处理不同学院的爬取。"""

    name = "dispatch_workers"
    description = """并行派发多个 Worker Agent，分别爬取不同学院的教师邮箱。

当你发现目标大学有多个学院需要爬取时使用此工具。
相比串行逐个爬取，并行可以节省 3-6 倍时间。

使用流程：
1. 先用 browser_navigate/web_fetch 发现所有学院的师资页面 URL
2. 将学院名称和对应的 URL 整理为 tasks 列表
3. 调用此工具并行爬取
4. 收到结果后汇总报告

注意：
- 每个 Worker 只使用 web_fetch（HTTP 请求），不会打开浏览器
- 建议每批 2-6 个学院，数量适中即可
- Worker 会自动提取邮箱并保存 CSV 到 outputs/ 目录
"""
    input_schema = {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "学院全称，如「计算机科学与技术学院」",
                        },
                        "url": {
                            "type": "string",
                            "description": "该学院的师资/教师介绍页面 URL",
                        },
                        "notes": {
                            "type": "string",
                            "description": "可选：对该页面结构的额外提示，如「页面是表格结构」",
                        },
                    },
                    "required": ["name", "url"],
                },
                "description": "要并行爬取的学院列表。同一批任务应具有相似的页面结构。",
            },
            "university": {
                "type": "string",
                "description": "大学全称，如「南京大学」",
            },
            "max_workers": {
                "type": "integer",
                "description": "最大并行 Worker 数（默认 4，建议 2-6）",
                "default": 4,
            },
            "save_csv": {
                "type": "boolean",
                "description": "是否让 Worker 自动保存 CSV 到 outputs/ 目录（默认 true）",
                "default": True,
            },
        },
        "required": ["tasks", "university"],
    }
    is_readonly = False

    def __init__(
        self,
        task_id: str = "",
        progress_callback: Callable[[str, str, int, int, str], Coroutine[Any, Any, None]] | None = None,
    ):
        """初始化。

        Args:
            task_id: 父任务 ID
            progress_callback: 进度回调，签名 (name, status, found, emails, error) -> None
                每次 Worker 完成时调用，status 为 "done" 或 "error"
        """
        super().__init__()
        self._task_id = task_id
        self._progress_callback = progress_callback

    async def call(self, input_data: dict[str, Any]) -> ToolResult:
        tasks: list[dict] = input_data.get("tasks", [])
        university: str = input_data.get("university", "目标大学")
        max_workers: int = min(input_data.get("max_workers", 4), 8)
        save_csv: bool = input_data.get("save_csv", True)

        if not tasks:
            return ToolResult(data="❌ 任务列表为空，请提供至少一个学院")

        logger.info(
            f"[Dispatch] 派发 {len(tasks)} 个 Worker 并行爬取"
            f"（大学={university}, 最大并行={max_workers}）"
        )

        start_time = time.time()

        # ── 创建并行的 Worker 任务 ──
        semaphore = asyncio.Semaphore(max_workers)

        async def run_worker(task: dict) -> dict:
            """单个 Worker 的执行逻辑。"""
            async with semaphore:
                college_name = task.get("name", "未知学院")
                college_url = task.get("url", "")
                notes = task.get("notes", "")

                # 构建 Worker 的系统上下文
                context_parts = [
                    f"你正在爬取 {university} 下「{college_name}」的教师邮箱。",
                    f"目标页面: {college_url}",
                ]
                if notes:
                    context_parts.append(f"页面提示: {notes}")
                context_parts.append(
                    "请使用 web_fetch 获取页面，然后提取其中的教师姓名、职称、邮箱。"
                )
                if save_csv:
                    context_parts.append(
                        "提取后使用 file_write 以 CSV 格式保存，"
                        f"文件名用 '{college_name}_teachers.csv'。"
                        "CSV 列名: 姓名、职称、邮箱"
                    )

                task_prompt = (
                    f"请爬取 {university} {college_name} 的教师邮箱。\n"
                    f"URL: {college_url}\n\n"
                    "步骤:\n"
                    "1. 使用 web_fetch 获取该页面内容\n"
                    "2. 从页面中提取教师的姓名、职称、邮箱\n"
                    "3. 过滤公共邮箱（admin@, webmaster@, info@ 等）\n"
                    "4. 保存为 CSV 文件\n"
                    "5. 报告你找到了多少位教师和邮箱\n\n"
                    "注意：如果页面没有直接列出邮箱，尝试寻找「教师名录」「师资队伍」等子页面链接。"
                )

                try:
                    from ..worker import WorkerAgent
                    worker = WorkerAgent(
                        provider=None,  # 使用默认 provider
                        worker_id=f"worker-{college_name[:6]}",
                        parent_task_id=self._task_id,
                        restricted_tools=["think", "web_fetch", "file_write"],
                    )
                    text, meta = await worker.execute(
                        task_prompt=task_prompt,
                        task_context="\n".join(context_parts),
                    )
                    result = {
                        "name": college_name,
                        "url": college_url,
                        "success": True,
                        "text": text,
                        "meta": meta,
                    }
                    # 进度回调
                    if self._progress_callback:
                        found = 0
                        emails = 0
                        fm = re.search(r"找到\s*(\d+)\s*(?:位|名|个).*(?:教师|教授)", text)
                        if fm:
                            found = int(fm.group(1))
                        em = re.search(r"(\d+)\s*个邮箱", text)
                        if em:
                            emails = int(em.group(1))
                        try:
                            await self._progress_callback(college_name, "done", found, emails, "")
                        except Exception:
                            pass
                    return result
                except Exception as e:
                    logger.error(f"Worker [{college_name}] 失败: {e}")
                    result = {
                        "name": college_name,
                        "url": college_url,
                        "success": False,
                        "error": str(e)[:200],
                        "meta": {},
                    }
                    if self._progress_callback:
                        try:
                            await self._progress_callback(college_name, "error", 0, 0, str(e)[:100])
                        except Exception:
                            pass
                    return result

        # ── 并行执行所有 Worker ──
        results = await asyncio.gather(*[run_worker(t) for t in tasks])

        duration = time.time() - start_time

        # ── 汇总结果 ──
        success_count = sum(1 for r in results if r["success"])
        fail_count = len(results) - success_count

        summary_lines = [
            f"## 并行爬取完成",
            f"- 大学: {university}",
            f"- 学院数: {len(tasks)} | 成功: {success_count} | 失败: {fail_count}",
            f"- 并行度: {max_workers} | 耗时: {duration:.0f}s",
            "",
        ]

        for r in results:
            name = r["name"]
            if r["success"]:
                meta = r.get("meta", {})
                turns = meta.get("turns", "?")
                tools = meta.get("tool_uses", "?")
                # 从结果文本中提取找到的数量
                text = r.get("text", "")
                summary_lines.append(f"### ✅ {name}")
                summary_lines.append(f"{text[:300]}")
                summary_lines.append(f"（轮次: {turns} | 工具调用: {tools} 次）")
            else:
                summary_lines.append(f"### ❌ {name}")
                summary_lines.append(f"错误: {r.get('error', '未知错误')}")
            summary_lines.append("")

        total_turns = sum(
            r.get("meta", {}).get("turns", 0) for r in results if r["success"]
        )
        total_tool_uses = sum(
            r.get("meta", {}).get("tool_uses", 0) for r in results if r["success"]
        )

        summary_lines.append(
            f"**总计: {success_count}/{len(tasks)} 学院完成, "
            f"总轮次 {total_turns}, 总工具调用 {total_tool_uses}, "
            f"并行耗时 {duration:.0f}s**"
        )

        result_text = "\n".join(summary_lines)

        # 构建元数据
        metadata = {
            "total_tasks": len(tasks),
            "success_count": success_count,
            "fail_count": fail_count,
            "duration_seconds": duration,
            "max_workers": max_workers,
            "total_worker_turns": total_turns,
            "total_worker_tool_uses": total_tool_uses,
            "results": [
                {
                    "name": r["name"],
                    "success": r["success"],
                    "turns": r.get("meta", {}).get("turns", 0),
                    "tool_uses": r.get("meta", {}).get("tool_uses", 0),
                    "error": r.get("error", None),
                }
                for r in results
            ],
        }

        return ToolResult(
            data=result_text,
            metadata=metadata,
        )
