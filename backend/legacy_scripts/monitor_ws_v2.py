"""Monitor NJU crawl - v2. Runs inline to avoid import issues."""
import asyncio
import json
import sys
import time
import os

# Ensure websockets is installed
try:
    import websockets
except ImportError:
    os.system(f"{sys.executable} -m pip install websockets -q")
    import websockets

TASK_ID = sys.argv[1] if len(sys.argv) > 1 else "3cfa8ef9-04ca-432c-b24c-a366fa35ffbe"
URI = f"ws://localhost:8010/ws/{TASK_ID}"

print(f"[{time.strftime('%H:%M:%S')}] Starting monitor for task {TASK_ID[:8]}")
print(f"[{time.strftime('%H:%M:%S')}] Connecting to {URI}")
sys.stdout.flush()

t0 = time.time()

async def main():
    try:
        async with websockets.connect(URI, ping_timeout=300, max_size=10_000_000) as ws:
            print(f"[{time.strftime('%H:%M:%S')}] CONNECTED! Agent is running...\n")
            sys.stdout.flush()
            
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=600)
                    data = json.loads(msg)
                    t = time.strftime("%H:%M:%S")
                    mt = data.get("type", "?")
                    m = str(data.get("message", data.get("msg", "")))[:300].replace("\n", " ")
                    elapsed = int(time.time() - t0)
                    
                    icon = {"log":"  LOG","progress":"PROG","error":"!!!!","done":"DONE","agent":"AGNT","text":"TEXT","download":"DOWN"}.get(mt, f"{mt:>4}")
                    print(f"[{t} +{elapsed}s] [{icon}] {m}")
                    sys.stdout.flush()
                    
                    if mt == "done":
                        print(f"\n{'='*60}")
                        print(f"DONE at +{int(time.time()-t0)}s")
                        print(f"{'='*60}")
                        break
                except asyncio.TimeoutError:
                    print(f"[{time.strftime('%H:%M:%S')}] TIMEOUT (no msg for 600s)")
                    break
    except websockets.exceptions.ConnectionClosed as e:
        print(f"[{time.strftime('%H:%M:%S')}] WS CLOSED: code={e.code} reason={e.reason}")
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] ERROR: {type(e).__name__}: {e}")
    
    print(f"[{time.strftime('%H:%M:%S')}] Monitor ended. Total: {int(time.time()-t0)}s")

asyncio.run(main())
