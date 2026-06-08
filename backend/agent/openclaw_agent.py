"""DeepSeek Agent — 后端直接调 DeepSeek API，不依赖外部 CLI"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import AsyncGenerator

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


class OpenClawAgent:
    """使用 DeepSeek API 直接执行任务（名称保留 OpenClaw 以兼容路由）。"""

    def __init__(self):
        self._stopped_tasks: set[str] = set()
        self.active_procs: dict[str, asyncio.Task] = {}

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def stop_task(self, task_id: str = "") -> bool:
        self._stopped_tasks.add(task_id)
        proc = self.active_procs.get(task_id)
        if proc and not proc.done():
            proc.cancel()
            return True
        return False

    def _get_api_key(self) -> tuple[str, str]:
        """获取 DeepSeek API key 和 base URL。"""
        key = os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            # 从 .env 文件读取
            env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
            try:
                with open(env_path, encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("DEEPSEEK_API_KEY"):
                            key = line.split("=", 1)[1].strip()
                            break
            except OSError:
                pass
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
        return key, base_url

    async def _call_deepseek(
        self, messages: list[dict], task_id: str = ""
    ) -> AsyncGenerator[str, None]:
        """调用 DeepSeek 流式 API，逐 token 产出。"""
        from openai import AsyncOpenAI

        api_key, base_url = self._get_api_key()
        if not api_key:
            yield json.dumps({
                "type": "error",
                "message": "未配置 DeepSeek API Key",
                "timestamp": self._timestamp(),
            })
            return

        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        try:
            stream = await client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                max_tokens=4096,
                temperature=0.3,
                stream=True,
            )
            async for chunk in stream:
                if task_id in self._stopped_tasks:
                    break
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            logger.error(f"DeepSeek API error: {e}")
            yield json.dumps({
                "type": "error",
                "message": f"API 调用失败: {str(e)[:200]}",
                "timestamp": self._timestamp(),
            })

    async def execute(
        self,
        message: str,
        task_id: str = "",
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        """执行任务：直接调 DeepSeek API 完成。"""
        self._stopped_tasks.discard(task_id)

        yield {"type": "log", "message": "🤖 DeepSeek 思考中...", "timestamp": self._timestamp()}

        messages = [
            {"role": "system", "content": "你是一个高校教师邮箱爬取助手。回答简洁专业，用中文。"},
            {"role": "user", "content": message},
        ]

        full_text = ""
        try:
            async for chunk in self._call_deepseek(messages, task_id):
                if chunk.startswith("{"):
                    try:
                        data = json.loads(chunk)
                        if data.get("type") == "error":
                            yield data
                            return
                    except json.JSONDecodeError:
                        pass
                else:
                    full_text += chunk

            if full_text:
                yield {"type": "text", "message": full_text, "timestamp": self._timestamp()}
            else:
                yield {"type": "log", "message": "DeepSeek 未返回有效内容", "timestamp": self._timestamp()}

            yield {"type": "done", "message": "任务完成", "timestamp": self._timestamp()}

        except Exception as e:
            logger.error(f"execute error: {e}")
            yield {"type": "error", "message": f"执行异常: {str(e)[:200]}", "timestamp": self._timestamp()}
