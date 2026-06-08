"""Monitor NJU crawl task via WebSocket."""
import asyncio, json, sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

async def monitor(task_id):
    import websockets
    uri = f"ws://localhost:8010/ws/{task_id}"
    print(f"[{time.strftime('%H:%M:%S')}] Connecting to {uri}")
    sys.stdout.flush()
    
    t0 = time.time()
    try:
        async with websockets.connect(uri, ping_timeout=300, max_size=10_000_000) as ws:
            print(f"[{time.strftime('%H:%M:%S')}] CONNECTED! Waiting for agent output...\n")
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
                    sys.stdout.flush()
                    break
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] ERROR: {type(e).__name__}: {e}")
        sys.stdout.flush()

if __name__ == "__main__":
    asyncio.run(monitor(sys.argv[1]))
