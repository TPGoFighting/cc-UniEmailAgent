"""NJU Crawl Test - create task, connect WS, monitor progress."""
import asyncio
import json
import sys
import os
from datetime import datetime

try:
    import httpx
    import websockets
except ImportError:
    os.system(f"{sys.executable} -m pip install httpx websockets -q")
    import httpx
    import websockets


async def run_test():
    # 1. Create the crawl task
    msg = "请爬取南京大学（Nanjing University）全校各院系的教师邮箱信息，包括姓名、邮箱、学院、职称。务必确保数据完整准确，覆盖所有学院。并输出详细的每一步操作日志。"
    
    print("=" * 60)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Creating NJU crawl task...")
    print("=" * 60)
    
    async with httpx.AsyncClient() as client:
        resp = await client.post("http://localhost:8010/api/chat", json={"message": msg})
        data = resp.json()
        task_id = data["task_id"]
        print(f"Task ID: {task_id}")
        print(f"URL: ws://localhost:8010/ws/{task_id}")
    
    # 2. Check initial task state
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://localhost:8010/api/history/{task_id}")
        state = resp.json()
        status = state.get("task", {}).get("status", "unknown")
        msg_count = state.get("total", 0)
        print(f"Initial state: status={status}, messages={msg_count}")
    
    # 3. Connect WebSocket and monitor
    uri = f"ws://localhost:8010/ws/{task_id}"
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Connecting to WebSocket...")
    
    msg_count = 0
    agent_logs = []
    start_time = datetime.now()
    
    try:
        async with websockets.connect(uri, ping_timeout=300, max_size=10_000_000) as ws:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] WebSocket Connected! Monitoring agent behavior...\n")
            
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=600)
                    data = json.loads(msg)
                    ts = datetime.now().strftime("%H:%M:%S")
                    msg_count += 1
                    
                    msg_type = data.get("type", "?")
                    message = str(data.get("message", data.get("msg", "")))
                    agent_logs.append({"ts": ts, "type": msg_type, "message": message})
                    
                    # Print with formatting based on type
                    prefix = {
                        "log": "  [LOG]",
                        "progress": "[PROG]",
                        "error": "[ERR!]",
                        "done": "[DONE]",
                        "agent": "[AGNT]",
                        "download": "[DOWN]",
                        "text": "[TEXT]",
                    }.get(msg_type, f"[{msg_type}]")
                    
                    short_msg = message[:250].replace("\n", " ")
                    print(f"[{ts}] {prefix} {short_msg}")
                    sys.stdout.flush()
                    
                    if msg_type == "done":
                        elapsed = (datetime.now() - start_time).total_seconds()
                        print(f"\n{'=' * 60}")
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] TASK COMPLETE!")
                        print(f"Total time: {elapsed:.0f}s | Total messages: {msg_count}")
                        print(f"Final message: {message}")
                        print(f"{'=' * 60}")
                        break
                        
                except asyncio.TimeoutError:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [TIMEOUT] No msg for 600s at {elapsed:.0f}s")
                    break
                    
    except websockets.exceptions.ConnectionClosed as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] WS closed: {e.code} {e.reason}")
        print(f"Total time: {elapsed:.0f}s | Messages received: {msg_count}")
    
    except Exception as e:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] WS Error: {type(e).__name__}: {e}")
    
    # 4. Print summary
    print(f"\n{'=' * 60}")
    print(f"AGENT BEHAVIOR SUMMARY:")
    print(f"{'=' * 60}")
    
    # Check for error messages
    errors = [l for l in agent_logs if l["type"] == "error"]
    done_msgs = [l for l in agent_logs if l["type"] == "done"]
    progress_msgs = [l for l in agent_logs if l["type"] in ("log", "progress", "text", "agent")]
    
    print(f"Total messages: {msg_count}")
    print(f"Error messages: {len(errors)}")
    print(f"Done messages: {len(done_msgs)}")
    print(f"Progress/Log messages: {len(progress_msgs)}")
    
    if errors:
        print(f"\nERRORS FOUND:")
        for e in errors:
            print(f"  - {e['ts']}: {e['message'][:200]}")
    
    # 5. Check output files
    print(f"\n{'=' * 60}")
    print(f"OUTPUT FILES:")
    print(f"{'=' * 60}")
    output_dir = os.path.join(os.path.dirname(__file__), "backend", "outputs", task_id)
    if os.path.exists(output_dir):
        files = os.listdir(output_dir)
        print(f"Output directory: {output_dir}")
        print(f"Files ({len(files)}):")
        for f in files:
            fpath = os.path.join(output_dir, f)
            fsize = os.path.getsize(fpath)
            print(f"  - {f} ({fsize} bytes)")
    else:
        # Try flat output dir
        flat_dir = os.path.join(os.path.dirname(__file__), "backend", "outputs")
        if os.path.exists(flat_dir):
            files = [f for f in os.listdir(flat_dir) if os.path.isfile(os.path.join(flat_dir, f))]
            print(f"Flat output dir: {flat_dir}")
            print(f"Files ({len(files)}):")
            for f in sorted(files, key=lambda x: os.path.getmtime(os.path.join(flat_dir, x)), reverse=True)[:10]:
                fpath = os.path.join(flat_dir, f)
                fsize = os.path.getsize(fpath)
                print(f"  - {f} ({fsize} bytes)")
        else:
            print(f"Output directory not found: {output_dir}")
    
    # 6. Also check history for output filenames
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://localhost:8010/api/history/{task_id}")
        state = resp.json()
        msgs = state.get("messages", [])
        down_msgs = [m for m in msgs if m.get("type") == "download" or m.get("role") == "download"]
        if down_msgs:
            print(f"\nDownload links from history ({len(down_msgs)}):")
            for m in down_msgs[-5:]:
                print(f"  - {m.get('filename', '?')}: {m.get('url', '?')}")
    
    print(f"\n[DONE] Test completed at {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(run_test())
