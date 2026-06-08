"""Check task progress."""
import httpx, json, sys

task_id = sys.argv[1]
r = httpx.get(f"http://localhost:8010/api/history/{task_id}", params={"limit": 0, "offset": 8})
data = r.json()
msgs = data.get("messages", [])
task = data.get("task", {})
print(f"Status: {task.get('status','?')} | Total: {data.get('total',0)}")
for m in msgs[-10:]:
    role = m.get("role", m.get("type","?"))
    content = str(m.get("content", m.get("message","")))[:200].replace("\n"," ")
    print(f"  [{role}] {content}")
