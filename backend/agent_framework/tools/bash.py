"""Bash 命令执行工具 — 运行 shell 命令。"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Any

from ..tool import Tool, ToolResult

logger = logging.getLogger(__name__)


class BashTool(Tool):
    """执行 shell 命令并获取输出。"""

    name = "bash"
    description = """执行 shell 命令并获取输出结果。
适用于运行 Python 脚本、数据处理、文件操作等。
命令在项目根目录下执行，超时 60 秒。
"""
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 shell 命令",
            },
            "timeout": {
                "type": "integer",
                "description": "超时秒数（默认 30，最大 120）",
                "default": 30,
            },
            "workdir": {
                "type": "string",
                "description": "工作目录（默认项目根目录）",
            },
        },
        "required": ["command"],
    }

    async def call(self, input_data: dict[str, Any]) -> ToolResult:
        command = input_data["command"]
        timeout = min(input_data.get("timeout", 30), 120)
        workdir = input_data.get("workdir", "")

        # 安全检查：禁止危险命令
        dangerous = ["rm -rf /", "mkfs", "dd if=", "> /dev/sda", ":(){ :|:& };:"]
        for d in dangerous:
            if d in command:
                return ToolResult(data=f"命令因安全策略被拒绝: 包含危险操作 '{d[:20]}...'")

        try:
            loop = asyncio.get_event_loop()

            def _run():
                return subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=workdir or None,
                    shell=True,
                    timeout=timeout,
                )

            proc = await loop.run_in_executor(None, _run)

            out = proc.stdout.decode("utf-8", errors="replace").strip() if proc.stdout else ""
            err = proc.stderr.decode("utf-8", errors="replace").strip() if proc.stderr else ""

            result_parts = []
            if out:
                if len(out) > 3000:
                    result_parts.append("**stdout**（" + str(len(out)) + " 字符，显示前 3000）:\n" + out[:3000])
                else:
                    result_parts.append("**stdout**:\n" + out)
            if err:
                if len(err) > 1000:
                    result_parts.append("**stderr**（" + str(len(err)) + " 字符）:\n" + err[:1000])
                else:
                    result_parts.append("**stderr**:\n" + err)
            if not result_parts:
                result_parts.append("命令执行完毕（无输出）")

            return ToolResult(
                data="\n\n".join(result_parts),
                metadata={
                    "exit_code": proc.returncode or 0,
                    "stdout_len": len(out),
                    "stderr_len": len(err),
                },
            )

        except subprocess.TimeoutExpired:
            return ToolResult(data="命令超时（" + str(timeout) + "s）: " + command[:100] + "...")
        except Exception as e:
            err_name = type(e).__name__
            err_msg = str(e) or err_name
            logger.warning("bash 执行失败: %s: %s", err_name, err_msg)
            return ToolResult(data="命令执行失败: " + err_msg)
