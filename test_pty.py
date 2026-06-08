import asyncio, shlex

async def t():
    cmd = ['script', '-qfc', 
           f"hermes chat -q {shlex.quote('用中文回复：成功')} --yolo -m deepseek/deepseek-v4-flash --cli",
           '/dev/null']
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    
    count = 0
    try:
        async for raw in proc.stdout:
            line = raw.decode('utf-8', errors='replace').strip()
            if line:
                count += 1
                if count <= 5:
                    print(f'  LINE {count}: {line[:120]}')
    except:
        pass
    
    await proc.wait()
    print(f'Total lines: {count}')
    # Show last 3 lines
    print(f'Return code: {proc.returncode}')

asyncio.run(t())
