"""端到端测试：南京工程学院计算机工程学院"""
import asyncio, json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))

async def test():
    import httpx
    base = "http://localhost:8071"

    # 1. 创建任务
    print("=== 1. 创建任务 ===")
    async with httpx.AsyncClient() as c:
        resp = await c.post(f"{base}/api/chat", json={"message": "帮我抓取南京工程学院计算机工程学院的教师邮箱信息"})
        task_id = resp.json()["task_id"]
        print(f"Task: {task_id}")

    # 2. 连 WS（触发 Agent）
    print("\n=== 2. 连接 WebSocket ===")
    import websockets
    uri = f"ws://localhost:8071/ws/{task_id}"
    async with websockets.connect(uri) as ws:
        print("WS 已连接，Agent 启动...\n")
        start = time.time()
        while time.time() - start < 180:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=190)
                data = json.loads(msg)
                t = data.get("type","")
                m = str(data.get("message",""))
                if t == "text":
                    print(f"[TEXT] {m[:100]}")
                elif t == "log":
                    if "调用:" in m:
                        print(f"  ⚡ {m[:80]}")
                    elif "📋" in m:
                        print(f"  📊 {m[:100]}")
                    elif "✅" in m:
                        print(f"  ✅ {m[:100]}")
                elif t == "download":
                    print(f"  📄 {data.get('filename','?')}")
                elif t == "done":
                    print(f"\n✅ 完成: {m[:200]}")
                    break
                elif t in ("error","error_user"):
                    print(f"  ❌ {m[:100]}")
            except asyncio.TimeoutError:
                print("超时")
                break
            except websockets.ConnectionClosed:
                break

    # 3. 检查输出
    print("\n=== 3. 结果 ===")
    out_dir = f"D:/Work/test/UniEmailAgent/backend/outputs/{task_id}"
    if os.path.exists(out_dir):
        files = [f for f in os.listdir(out_dir) if f.endswith((".csv",".xlsx",".md"))]
        print(f"输出文件 ({len(files)}):")
        for f in files:
            fp = os.path.join(out_dir, f)
            print(f"  {f} ({os.path.getsize(fp)} bytes)")
    else:
        print("无输出目录")

if __name__ == "__main__":
    asyncio.run(test())
