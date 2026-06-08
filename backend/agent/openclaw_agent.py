"""OpenClaw Agent — 通过 OpenClaw CLI 执行任务（DeepSeek API 驱动）"""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


class OpenClawAgent:
    """使用 OpenClaw agent CLI 执行任务，支持 DeepSeek API。"""

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

    async def execute(
        self,
        message: str,
        task_id: str = "",
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        """执行任务：调用 OpenClaw agent CLI，解析 JSON 输出。"""
        self._stopped_tasks.discard(task_id)

        # 暂不支持非爬取场景
        yield {"type": "log", "message": "🚀 准备通过 OpenClaw 执行...", "timestamp": self._timestamp()}

        # 写 prompt 到临时文件（避免命令行长度限制）
        prompt_file = f"/tmp/oc_prompt_{task_id[:8]}.txt"
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(message)

        # 写包装脚本（绕过 su 引号嵌套问题）
        script_file = f"/tmp/oc_run_{task_id[:8]}.sh"
        session_key = f"uniemail-{task_id[:8]}"
        with open(script_file, "w") as f:
            f.write(f"""#!/bin/bash
openclaw agent --local -m "$(cat {prompt_file})" --json --session-key {session_key}
""")
        os.chmod(script_file, 0o755)

        cmd = ["su", "-", "uniemail", "-c", script_file]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self.active_procs[task_id] = proc

            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
            self.active_procs.pop(task_id, None)

            if proc.returncode != 0:
                err_text = stderr.decode("utf-8", errors="replace")[-500:]
                logger.warning(f"OpenClaw exit code {proc.returncode}: {err_text}")
                yield {
                    "type": "error",
                    "message": f"OpenClaw 执行失败（退出码 {proc.returncode}）",
                    "timestamp": self._timestamp(),
                }
                return

            # 解析 JSON 输出
            output = stdout.decode("utf-8", errors="replace")
            data = json.loads(output)
            completion = data.get("completion", {})
            result_text = completion.get("text", "") or completion.get("message", "")

            if result_text:
                yield {"type": "text", "message": result_text, "timestamp": self._timestamp()}

            yield {"type": "done", "message": "任务执行完毕", "timestamp": self._timestamp()}

        except asyncio.TimeoutError:
            logger.warning(f"OpenClaw task {task_id[:8]} timeout")
            yield {"type": "error", "message": "任务执行超时（600s）", "timestamp": self._timestamp()}
        except Exception as e:
            logger.error(f"OpenClaw execute error: {e}")
            yield {"type": "error", "message": f"执行异常: {str(e)[:200]}", "timestamp": self._timestamp()}
        finally:
            # 清理临时文件
            for f in [prompt_file, f"/tmp/oc_stderr_{task_id[:8]}.txt"]:
                try:
                    os.remove(f)
                except OSError:
                    pass
