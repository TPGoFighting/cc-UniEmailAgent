"""Mem0 持久记忆系统 — 自动从爬取历史中学习模式。

环境变量：
  MEM0_ENABLED: 是否启用 Mem0 记忆搜索和写入（默认 "false"）
  MEM0_HISTORY_DB: SQLite 历史数据库路径（默认 "data/mem0.db"）
  MEM0_QDRANT_PATH: Qdrant 本地向量库路径（默认 "data/mem0_qdrant"）

所有调用均内置 try/except 兜底，失败时静默回退到文件系统技能库。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

_MEM0_ENABLED = os.environ.get("MEM0_ENABLED", "false").lower() in ("1", "true", "yes")
_MEM0_HISTORY_DB = os.environ.get("MEM0_HISTORY_DB", "data/mem0.db")
_MEM0_QDRANT_PATH = os.environ.get("MEM0_QDRANT_PATH", "data/mem0_qdrant")


class CrawlMemory:
    """Mem0 客户端封装，提供爬取经验的持久记忆能力。

    使用单例模式，全局共享一个 Mem0 实例。
    默认不启用（MEM0_ENABLED=false），启用后才初始化连接。
    """

    _instance: CrawlMemory | None = None

    def __init__(self) -> None:
        self._ready = False
        self._memory = None

        if not _MEM0_ENABLED:
            return

        try:
            from mem0 import Memory  # noqa: F811

            deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
            openai_key = os.environ.get("OPENAI_API_KEY", "")
            openai_base = os.environ.get("OPENAI_BASE_URL", "")

            # LLM 配置：优先 DeepSeek，其次 OpenAI
            if deepseek_key:
                llm_api_key = deepseek_key
                llm_model = "deepseek-chat"
                llm_base = "https://api.deepseek.com/v1"
            elif openai_key:
                llm_api_key = openai_key
                llm_model = os.environ.get("OPENAI_API_MODEL", "gpt-4o-mini")
                llm_base = openai_base or "https://api.openai.com/v1"
            else:
                logger.warning("[Mem0] 未找到任何 API Key，跳过初始化")
                return

            # Embedder 配置：优先 OpenAI（DeepSeek 无 embedding API）
            embedder_key = openai_key or deepseek_key
            if openai_key:
                embedder_model = "text-embedding-3-small"
                embedder_base = openai_base or "https://api.openai.com/v1"
            else:
                # 仅 DeepSeek 时，尝试用其作为 embedding 代理（可能不可用，由 mem0 自身报错）
                embedder_model = "text-embedding-3-small"
                embedder_base = "https://api.deepseek.com/v1"

            config = {
                "version": "v1.1",
                "history_db_path": _MEM0_HISTORY_DB,
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "path": _MEM0_QDRANT_PATH,
                        "collection_name": "crawl_experiences",
                        "on_disk": True,
                    },
                },
                "llm": {
                    "provider": "openai",
                    "config": {
                        "model": llm_model,
                        "api_key": llm_api_key,
                        "openai_base_url": llm_base,
                    },
                },
                "embedder": {
                    "provider": "openai",
                    "config": {
                        "model": embedder_model,
                        "api_key": embedder_key,
                        "openai_base_url": embedder_base,
                    },
                },
            }

            self._memory = Memory.from_config(config)
            self._ready = True
            logger.info(
                "[Mem0] 初始化成功 (LLM: %s / Embedder: %s / VS: Qdrant local)",
                llm_model, embedder_model,
            )

        except Exception as e:
            logger.warning(f"[Mem0] 初始化失败（回退到文件系统技能库）: {e}")
            self._ready = False

    @classmethod
    def get_instance(cls) -> CrawlMemory:
        """获取全局单例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（测试用）。"""
        cls._instance = None

    # ── 搜索 ────────────────────────────────────────────────

    def search_relevant(self, query: str, university: str = "", limit: int = 5) -> str:
        """搜索与当前任务相关的历史经验，返回 Markdown 格式文本。

        失败时返回空字符串（不影响主流程）。
        """
        if not self._ready or self._memory is None:
            return ""

        try:
            search_query = f"{university} {query}".strip() if university else query
            results = self._memory.search(search_query, top_k=limit)
            if not results:
                return ""

            parts: list[str] = []
            for r in results:
                text = r.get("memory", "")
                if text:
                    parts.append(f"- {text}")

            if not parts:
                return ""

            return "## 🧠 Mem0 历史经验（AI 自动提取）\n\n" + "\n".join(parts) + "\n\n"

        except Exception as e:
            logger.warning(f"[Mem0] 搜索失败: {e}")
            return ""

    # ── 写入 ────────────────────────────────────────────────

    def add_crawl_experience(
        self,
        university: str,
        task_id: str,
        experience: str,
        metadata: dict | None = None,
    ) -> bool:
        """将爬取经验写入 Mem0 持久记忆。

        通过 messages 方式存储，失败时返回 False。
        """
        if not self._ready or self._memory is None:
            return False

        try:
            meta = metadata or {}
            meta.update({
                "university": university,
                "task_id": task_id,
                "timestamp": datetime.now().isoformat(),
            })

            messages = [
                {
                    "role": "user",
                    "content": f"从 {university} 的爬取任务中学习到以下经验",
                },
                {
                    "role": "assistant",
                    "content": experience,
                },
            ]

            self._memory.add(messages, user_id="uni_email_crawler", metadata=meta)
            logger.info(f"[Mem0] 经验已写入: {university} ({task_id[:8]})")
            return True

        except Exception as e:
            logger.warning(f"[Mem0] 写入失败: {e}")
            return False

    # ── 状态查询 ────────────────────────────────────────────

    def is_ready(self) -> bool:
        """Mem0 是否已成功初始化。"""
        return self._ready

    def get_all_memories(self, university: str = "") -> list[dict]:
        """获取所有记忆（调试/管理用）。"""
        if not self._ready or self._memory is None:
            return []

        try:
            if university:
                return self._memory.get_all(filters={"university": university})
            return self._memory.get_all()
        except Exception as e:
            logger.warning(f"[Mem0] 获取全部记忆失败: {e}")
            return []


# ═══════════════════════════════════════════════════════════════
# 快捷函数（供 main.py 调用，内部再次 try/except 兜底）
# ═══════════════════════════════════════════════════════════════

def search_mem0(query: str, university: str = "") -> str:
    """搜索 Mem0 历史经验。失败返回 ""。"""
    try:
        return CrawlMemory.get_instance().search_relevant(query, university)
    except Exception:
        return ""


def save_to_mem0(university: str, task_id: str, experience: str) -> bool:
    """保存爬取经验到 Mem0。失败返回 False。"""
    try:
        return CrawlMemory.get_instance().add_crawl_experience(university, task_id, experience)
    except Exception:
        return False
