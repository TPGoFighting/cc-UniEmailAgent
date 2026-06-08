"""南京大学教师邮箱爬取脚本（新架构版本）"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# 自动选择可用引擎：Hermes Orchestrator > ClaudeAgent > PlaywrightAgent
try:
    import shutil
    if shutil.which("hermes"):
        from agent.hermes_agent import HermesOrchestrator
        agent = HermesOrchestrator()
        print("使用 Hermes Orchestrator（智能编排引擎）")
    else:
        from agent.claude_agent import ClaudeAgent
        agent = ClaudeAgent()
        print("使用 Claude Agent")
except Exception:
    from agent.playwright_agent import PlaywrightAgent
    agent = PlaywrightAgent()
    print("使用 Playwright Agent（内置浏览器）")


async def main():
    task_id = "test123"
    message = "帮我抓取南京大学教师邮箱"

    async for event in agent.execute(message, task_id=task_id):
        t = event.get("type", "?")
        msg = event.get("message", "")
        if t == "log":
            print(f"  {msg}")
        elif t == "text":
            print(f"  {msg}")
        elif t == "download":
            print(f"  📥 {msg} → {event.get('filename', '?')}")
        elif t == "error":
            print(f"  ❌ {msg}")
        elif t == "done":
            print(f"  ✅ {msg}")
            break

    print("\n完成！检查 outputs/test123/ 目录")


if __name__ == "__main__":
    asyncio.run(main())
