"""通过 API 提交邮箱抓取任务并接收实时日志"""
import asyncio
import json
import aiohttp

BACKEND = "http://localhost:8000"


async def main():
    message = "抓取南京大学计算机学院教师邮箱，导出CSV"

    async with aiohttp.ClientSession() as session:
        # 1. 创建任务
        print("📤 创建任务...")
        async with session.post(f"{BACKEND}/api/chat", json={"message": message}) as resp:
            data = await resp.json()
            task_id = data["task_id"]
            print(f"✅ 任务已创建: {task_id}")

        # 2. 连接 WebSocket 接收实时日志
        print("🔌 连接 WebSocket...\n")
        async with session.ws_connect(f"{BACKEND}/ws/{task_id}") as ws:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    log = json.loads(msg.data)
                    log_type = log.get("type", "unknown")

                    if log_type == "log":
                        print(log.get("message", ""))
                    elif log_type == "download":
                        print(f"\n📥 下载链接: {BACKEND}{log['url']}")
                        print(f"📄 文件名: {log['filename']}")
                    elif log_type == "error":
                        print(f"\n❌ 错误: {log.get('message', '')}")
                    elif log_type == "done":
                        print(f"\n✅ {log.get('message', '')}")
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print(f"WebSocket 错误: {ws.exception()}")
                    break


if __name__ == "__main__":
    asyncio.run(main())
