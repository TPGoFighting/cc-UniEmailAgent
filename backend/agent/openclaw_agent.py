"""OpenClaw Agent — 通过 OpenClaw CLI 执行任务，从 session 文件提取结果"""

import asyncio
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator
import time

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

SESSIONS_PATH = Path("/root/.openclaw/agents/main/sessions/sessions.json")
OC_STATE_DIR = Path("/root/.openclaw")


class OpenClawAgent:
    """使用 OpenClaw agent CLI 执行任务，从 session 文件提取结果。"""

    def __init__(self):
        self.active_procs: dict[str, subprocess.Popen] = {}
        self._stopped_tasks: set[str] = set()

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def stop_task(self, task_id: str = "") -> bool:
        self._stopped_tasks.add(task_id)
        proc = self.active_procs.get(task_id)
        if proc:
            proc.kill()
            del self.active_procs[task_id]
            return True
        return False

    def _get_last_session_text(self) -> str:
        """从 OpenClaw sessions.json 读取最近一次 assistant 回复。"""
        try:
            if not SESSIONS_PATH.exists():
                return ""
            data = json.loads(SESSIONS_PATH.read_text(encoding="utf-8"))
            # 找到 session key 包含 "uniemail-" 的最新 session
            target_sessions = []
            for key, session in data.items():
                if "uniemail-" in key or key.startswith("session:"):
                    msgs = session.get("messages", [])
                    if msgs:
                        target_sessions.append((key, msgs))
            if not target_sessions:
                return ""
            # 取最后一个 session 的最后一条 assistant 消息
            _, msgs = target_sessions[-1]
            for m in reversed(msgs):
                if m.get("role") == "assistant":
                    content = m.get("content", "")
                    if isinstance(content, list):
                        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
                        return "\n".join(texts)
                    return str(content)
            return ""
        except Exception as e:
            logger.warning(f"读取 OpenClaw session 失败: {e}")
            return ""

    async def execute(
        self,
        message: str,
        task_id: str = "",
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        """执行任务：调用 OpenClaw agent CLI，从 session 文件读结果。"""
        self._stopped_tasks.discard(task_id)

        yield {"type": "log", "message": "🚀 通过 OpenClaw 执行...", "timestamp": self._timestamp()}

        session_key = f"uniemail-{task_id[:8]}" if task_id else "uniemail-default"

        # 写 prompt 到临时文件
        prompt_file = f"/tmp/oc_prompt_{task_id[:8]}.txt"
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(message)

        # 写包装脚本
        script_file = f"/tmp/oc_run_{task_id[:8]}.sh"
        with open(script_file, "w") as f:
            f.write(f"""#!/bin/bash
export HOME=/root
openclaw agent --local -m "$(cat {prompt_file})" --json --session-key {session_key} >/dev/null 2>&1
""")
        os.chmod(script_file, 0o755)

        cmd = [script_file]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self.active_procs[task_id] = proc

            await asyncio.wait_for(proc.wait(), timeout=600)
            self.active_procs.pop(task_id, None)

            # 从 session 文件读取回复
            result_text = self._get_last_session_text()

            if result_text:
                yield {"type": "text", "message": result_text, "timestamp": self._timestamp()}
            else:
                yield {"type": "log", "message": "OpenClaw 执行完毕（无文本回复）", "timestamp": self._timestamp()}

            yield {"type": "done", "message": "任务执行完毕", "timestamp": self._timestamp()}

        except asyncio.TimeoutError:
            logger.warning(f"OpenClaw task {task_id[:8]} timeout")
            yield {"type": "error", "message": "任务执行超时（600s）", "timestamp": self._timestamp()}
        except Exception as e:
            logger.error(f"OpenClaw execute error: {e}")
            yield {"type": "error", "message": f"执行异常: {str(e)[:200]}", "timestamp": self._timestamp()}
        finally:
            for f in [prompt_file, script_file]:
                try:
                    os.remove(f)
                except OSError:
                    pass
