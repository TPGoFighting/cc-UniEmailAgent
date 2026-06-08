import asyncio, sys
sys.path.insert(0, '.')
from agent.hermes_agent import HermesAgent

async def t():
    agent = HermesAgent()
    async for log in agent.execute(
        '用中文回复：成功',
        task_id='debug-test',
        is_crawl_session=True
    ):
        t = log.get('type', '?')
        m = str(log.get('message', ''))[:120]
        if t == 'text':
            print(f'[text  ] |{m}|', flush=True)
        elif t == 'log':
            # Only print non-empty logs
            if m.strip():
                print(f'[log   ] {m}', flush=True)
        else:
            print(f'[{t:6s}] {m}', flush=True)
        if t in ('done', 'error'):
            break
        # Also dump the reply_text to debug
asyncio.run(t())
