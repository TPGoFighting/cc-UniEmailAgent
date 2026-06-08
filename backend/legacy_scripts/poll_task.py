"""Poll task status periodically."""
import httpx, json, sys, time

task_id = sys.argv[1]
interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
max_checks = int(sys.argv[3]) if len(sys.argv) > 3 else 60

for i in range(max_checks):
    try:
        r = httpx.get(f"http://localhost:8010/api/history/{task_id}")
        d = r.json()
        t = d.get("task", {})
        msgs = d.get("messages", [])
        status = t.get("status", "?")
        print(f"[+{i*interval}s] Status: {status} | Messages: {len(msgs)}")
        for m in msgs[-2:]:
            role = m.get("role", m.get("type", "?"))
            content = str(m.get("content", m.get("message", "")))[:200].replace("\n", " ")
            print(f"  [{role}] {content}")
        sys.stdout.flush()
        if status in ("completed", "failed"):
            print(f"\nTask ended with status: {status}")
            if status == "completed":
                # Check output files
                out_dir = f"D:/Work/test/UniEmailAgent/backend/outputs/{task_id}"
                import os
                if os.path.exists(out_dir):
                    files = os.listdir(out_dir)
                    print(f"\nOutput files ({len(files)}):")
                    for f in sorted(files, key=lambda x: os.path.getmtime(os.path.join(out_dir, x)), reverse=True):
                        size = os.path.getsize(os.path.join(out_dir, f))
                        print(f"  {f} ({size} bytes)")
            break
    except Exception as e:
        print(f"[+{i*interval}s] Error: {e}")
    time.sleep(interval)
