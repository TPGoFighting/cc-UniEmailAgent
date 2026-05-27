"""测试 uvicorn 中子进程创建的 FastAPI 小应用"""
from fastapi import FastAPI
import asyncio
import traceback

app = FastAPI()

@app.get("/test")
async def test():
    try:
        cmd = [
            "claude", "-p", "--output-format", "stream-json",
            "--verbose", "--no-session-persistence",
            "--permission-mode", "bypassPermissions",
            "--max-budget-usd", "1.0", "--model", "deepseek-v4-pro",
            "say hi",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=10)
        proc.kill()
        return {"status": "ok", "pid": proc.pid, "first": str(line[:100])}
    except NotImplementedError as e:
        return {"status": "error", "type": "NotImplementedError", "msg": str(e)}
    except Exception as e:
        return {"status": "error", "type": type(e).__name__, "msg": str(e), "tb": traceback.format_exc()[:500]}
