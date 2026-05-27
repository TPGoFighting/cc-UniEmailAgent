"""OpenClaw Agent Runtime — 通过子进程调用 OpenClaw CLI，真实执行浏览器任务。"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

# 安全限制
MAX_STEPS = 30
MAX_RETRIES = 3
TIMEOUT_SECONDS = 300


class OpenClawAgent:
    """真实的 OpenClaw Agent 包装器。

    通过 asyncio 子进程调用 `openclaw agent` CLI，
    解析 JSON 输出，流式推送日志。

    如果 OpenClaw 不可用（缺少 API key 等），
    自动降级到 PlaywrightDirectAgent。
    """

    def __init__(self):
        self._check_openclaw()

    def _check_openclaw(self) -> bool:
        """检查 OpenClaw 是否可用。"""
        import shutil

        path = shutil.which("openclaw")
        if not path:
            logger.warning("OpenClaw 未找到，将使用回退模式")
            return False
        logger.info(f"OpenClaw 已就绪: {path}")
        return True

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    async def execute(self, message: str) -> AsyncGenerator[dict, None]:
        """执行任务。先尝试 OpenClaw，失败则回退到 Playwright。"""
        try:
            async for log in self._run_openclaw(message):
                yield log
        except Exception as e:
            logger.warning(f"OpenClaw 执行失败: {e}，回退到 Playwright 模式")
            yield {
                "type": "log",
                "message": f"OpenClaw 不可用（{e}），切换到内置浏览器 Agent",
                "timestamp": self._timestamp(),
            }
            from agent.playwright_agent import PlaywrightAgent

            fallback = PlaywrightAgent()
            async for log in fallback.execute(message):
                yield log

    async def _run_openclaw(self, message: str) -> AsyncGenerator[dict, None]:
        """通过子进程运行 OpenClaw agent。"""
        import shutil

        if not shutil.which("openclaw"):
            raise RuntimeError("OpenClaw CLI 未安装")

        yield {
            "type": "log",
            "message": "正在启动 OpenClaw Agent...",
            "timestamp": self._timestamp(),
        }

        cmd = [
            "openclaw",
            "agent",
            "--local",
            "--message", message,
            "--thinking", "high",
            "--timeout", str(TIMEOUT_SECONDS),
            "--json",
        ]

        env = os.environ.copy()

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        step_count = 0

        try:
            async for line in process.stdout:
                line = line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                step_count += 1
                if step_count > MAX_STEPS:
                    process.kill()
                    yield {
                        "type": "log",
                        "message": f"达到最大步数限制 ({MAX_STEPS})，任务已终止",
                        "timestamp": self._timestamp(),
                    }
                    break

                # 尝试解析 JSON
                parsed = self._parse_line(line)
                yield {
                    "type": "log",
                    "message": parsed,
                    "timestamp": self._timestamp(),
                }

            await asyncio.wait_for(process.wait(), timeout=10)

        except asyncio.TimeoutError:
            process.kill()
            yield {
                "type": "error",
                "message": f"任务超时 ({TIMEOUT_SECONDS}s)，已终止",
                "timestamp": self._timestamp(),
            }
            return

        if process.returncode != 0:
            stderr = await process.stderr.read()
            err_text = stderr.decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"OpenClaw 异常退出 (code={process.returncode}): {err_text}")

        yield {
            "type": "done",
            "message": "Agent 任务执行完毕",
            "timestamp": self._timestamp(),
        }

    def _parse_line(self, line: str) -> str:
        """解析 OpenClaw 输出行。尝试 JSON，失败则返回原文。"""
        try:
            data = json.loads(line)
            # 提取有意义的文本
            if isinstance(data, dict):
                text = data.get("text") or data.get("message") or data.get("content") or data.get("result")
                if text:
                    return str(text)[:500]
                # 嵌套解析
                for key in ("choices", "delta", "content"):
                    if key in data:
                        inner = data[key]
                        if isinstance(inner, list) and inner:
                            return str(inner[0].get("content", line))[:500]
                        if isinstance(inner, dict):
                            return str(inner.get("content", line))[:500]
            return line[:500]
        except (json.JSONDecodeError, TypeError):
            return line[:500]
