"""Monitor WebSocket for UniEmailAgent crawl task."""
import asyncio
import json
import sys
from datetime import datetime

try:
    import websockets
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "httpx", "websockets", "-q"])
    import websockets


async def monitor():
    task_id = sys.argv[1] if len(sys.argv) > 1 else "f3652d5e-375e-4c47-a7ca-84da0f19e100"
    url = f"ws://localhost:8010/ws/{task_id}"

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Connecting to WS: {url}")
    sys.stdout.flush()
    try:
        async with websockets.connect(url, ping_timeout=300, max_size=10_000_000) as ws:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] WS Connected! Monitoring agent...")
            sys.stdout.flush()
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=600)
                    data = json.loads(msg)
                    ts = datetime.now().strftime("%H:%M:%S")
                    msg_type = data.get("type", "?")
                    message = str(data.get("message", data.get("msg", "")))[:300]
                    print(f"[{ts}] [{msg_type}] {message}")
                    sys.stdout.flush()
                except asyncio.TimeoutError:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [TIMEOUT] No msg for 600s")
                    sys.stdout.flush()
                    break
    except websockets.exceptions.ConnectionClosed:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] WS Connection closed (agent done)")
        sys.stdout.flush()
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] WS Error: {e}")
        sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(monitor())
