"""调试脚本：检查当前 asyncio 事件循环的子进程支持"""
import asyncio
import os
import sys

async def main():
    loop = asyncio.get_running_loop()
    print(f"Loop type: {type(loop).__name__}")
    print(f"Loop MRO: {[c.__name__ for c in type(loop).__mro__]}")
    print(f"Has subprocess_exec: {hasattr(loop, 'subprocess_exec')}")
    if hasattr(loop, 'subprocess_exec'):
        print(f"subprocess_exec: {loop.subprocess_exec}")
    print(f"Has _make_subprocess_transport: {hasattr(loop, '_make_subprocess_transport')}")

    # 测试 create_subprocess_exec
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", "print('hello')",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        print(f"Subprocess test: OK - {stdout.decode().strip()}")
    except NotImplementedError as e:
        print(f"Subprocess test: NotImplementedError - '{e}'")
    except Exception as e:
        print(f"Subprocess test: {type(e).__name__} - {e}")

asyncio.run(main())
