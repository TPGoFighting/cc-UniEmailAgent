"""南京大学教师邮箱爬取脚本"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent.playwright_agent import PlaywrightAgent


async def main():
    task_id = "test123"
    message = "帮我抓取南京大学教师邮箱"

    agent = PlaywrightAgent()

    async for event in agent.execute(message, task_id=task_id):
        t = event.get("type", "?")
        msg = event.get("message", "")
        if t == "log":
            print(f"  {msg}")
        elif t == "download":
            print(f"  📥 {msg} → {event.get('filename', '?')}")
        elif t == "error":
            print(f"  ❌ {msg}")
        elif t == "done":
            print(f"  ✅ {msg}")
            break
        else:
            print(f"  [{t}] {msg}")

    print("\n完成！检查 outputs/test123/ 目录")


if __name__ == "__main__":
    asyncio.run(main())
