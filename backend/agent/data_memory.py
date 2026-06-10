"""DataMemory — 爬取结果数据的存储与检索（RAG 增强版）。

与 CrawlMemory（存储爬取经验）分开，使用独立的 JSON 文件和独立的向量索引。
支持：
- 关键词搜索（快速模糊匹配）
- 语义搜索（DeepSeek embedding + cosine 相似度）
- 混合搜索（关键词 + 语义加权）
"""

import json
import os
import logging
import re
import time
import math
from pathlib import Path
from datetime import datetime
from typing import Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_DATA_FILE = _DATA_DIR / "data_memory.json"
_VECTOR_DIR = _DATA_DIR / "data_vectors"

_EMBEDDING_DIM = 1792  # deepseek-embedding 输出维度


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算余弦相似度。"""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _get_embedding_client() -> Optional[AsyncOpenAI]:
    """获取 embedding API 客户端。优先使用 UI 配置的 key。"""
    from agent.config import get_effective_llm_settings
    api_key, base_url = get_effective_llm_settings()
    if not api_key:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return None
    return AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")


class DataMemory:
    """爬取结果数据的存储与检索，与 CrawlMemory 完全独立。"""

    _instance: "DataMemory | None" = None

    def __init__(self):
        self._rows: list[dict] = []
        self._vectors: list[list[float]] = []
        self._ready = False
        self._load()

    def _load(self):
        """从 JSON 文件加载已有数据和向量。"""
        try:
            if _DATA_FILE.exists():
                with open(_DATA_FILE, encoding="utf-8") as f:
                    raw = json.load(f)
                self._rows = raw.get("rows", [])
                self._vectors = raw.get("vectors", [])
                logger.info(f"[DataMemory] 已加载 {len(self._rows)} 条数据记录, {len(self._vectors)} 个向量")
            self._ready = True
        except Exception as e:
            logger.warning(f"[DataMemory] 加载失败: {e}")
            self._ready = True  # 空数据也视为就绪

    def _save(self):
        """持久化到 JSON 文件。"""
        try:
            _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump({"rows": self._rows, "vectors": self._vectors}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[DataMemory] 保存失败: {e}")

    @classmethod
    def get_instance(cls) -> "DataMemory":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── 写入 ──────────────────────────────────────────

    def index_csv(self, csv_path: str, university: str, task_id: str) -> int:
        """将 CSV 文件中的教师数据索引到 DataMemory。"""
        import csv
        added = 0
        try:
            with open(csv_path, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = (row.get("姓名") or "").strip()
                    email = (row.get("邮箱") or "").strip()
                    if not name or not email:
                        continue
                    dept = (row.get("学院") or row.get("department") or "").strip()
                    title = (row.get("职称") or row.get("title") or "").strip()

                    # 避免重复索引
                    existing_ids = {r["id"] for r in self._rows}
                    row_id = f"{university}_{email}"
                    if row_id in existing_ids:
                        continue

                    text = f"{name} | {email} | {dept} | {title}"
                    self._rows.append({
                        "id": row_id,
                        "university": university,
                        "name": name,
                        "email": email,
                        "department": dept,
                        "title": title,
                        "text": text,
                        "task_id": task_id,
                        "indexed_at": datetime.now().isoformat(),
                    })
                    self._vectors.append([])  # 占位，后续可由 embed_all 填充
                    added += 1

            self._save()
            logger.info(f"[DataMemory] 已索引 {added} 条记录 ({university})")
        except Exception as e:
            logger.warning(f"[DataMemory] 索引失败: {e}")
        return added

    async def embed_all(self):
        """为所有未 embedding 的记录生成向量。"""
        client = _get_embedding_client()
        if not client:
            logger.warning("[DataMemory] 无 API key，跳过 embedding")
            return 0

        to_embed = [(i, row) for i, (row, vec) in enumerate(zip(self._rows, self._vectors)) if not vec]
        if not to_embed:
            return 0

        logger.info(f"[DataMemory] 开始 embedding {len(to_embed)} 条记录...")
        embedded = 0
        # 分批处理，每批 20 条
        batch_size = 20
        for start in range(0, len(to_embed), batch_size):
            batch = to_embed[start:start + batch_size]
            texts = [row["text"] for _, row in batch]
            try:
                resp = await client.embeddings.create(
                    model="deepseek-embedding",
                    input=texts,
                )
                for (idx, _), emb in zip(batch, resp.data):
                    self._vectors[idx] = emb.embedding
                embedded += len(batch)
            except Exception as e:
                logger.warning(f"[DataMemory] embedding 批处理失败: {e}")
            time.sleep(0.1)  # 限速

        self._save()
        logger.info(f"[DataMemory] embedding 完成: {embedded} 条")
        return embedded

    # ── 检索 ──────────────────────────────────────────

    def search_keyword(self, query: str, university: str = "", limit: int = 20) -> list[dict]:
        """关键词搜索数据记录。快速模糊匹配，无需 embedding。"""
        if not self._ready or not self._rows:
            return []

        query_lower = query.lower()
        words = re.findall(r"[\w\u4e00-\u9fff]+", query_lower)
        if not words:
            return []

        scored: list[tuple[float, dict]] = []
        for row in self._rows:
            if university and row["university"] != university:
                continue
            text_lower = row["text"].lower()
            score = sum(1 for w in words if w in text_lower)
            if score > 0:
                scored.append((float(score), row))

        scored.sort(key=lambda x: -x[0])
        return [r for _, r in scored[:limit]]

    async def search_semantic(self, query: str, university: str = "", limit: int = 20) -> list[dict]:
        """语义搜索：用 query embedding 找最相似的数据记录。"""
        if not self._ready or not self._rows:
            return []
        # 没有向量数据时降级到关键词
        if not any(self._vectors):
            logger.info("[DataMemory] 无向量数据，降级到关键词搜索")
            return self.search_keyword(query, university, limit)

        client = _get_embedding_client()
        if not client:
            return self.search_keyword(query, university, limit)

        try:
            resp = await client.embeddings.create(
                model="deepseek-embedding",
                input=[query],
            )
            query_vec = resp.data[0].embedding
        except Exception as e:
            logger.warning(f"[DataMemory] query embedding 失败，降级到关键词: {e}")
            return self.search_keyword(query, university, limit)

        scored: list[tuple[float, dict]] = []
        for row, vec in zip(self._rows, self._vectors):
            if university and row["university"] != university:
                continue
            if vec:
                score = _cosine_similarity(query_vec, vec)
                if score > 0.3:  # 相似度阈值
                    scored.append((score, row))

        scored.sort(key=lambda x: -x[0])
        return [r for _, r in scored[:limit]]

    async def search_hybrid(self, query: str, university: str = "", limit: int = 20) -> list[dict]:
        """混合搜索：语义 + 关键词，结果去重合并排序。"""
        kw_results = self.search_keyword(query, university, limit)
        sem_results = await self.search_semantic(query, university, limit)

        # 去重合并：关键词结果优先，语义结果补充
        seen_ids = set()
        merged: list[dict] = []
        for r in kw_results + sem_results:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                merged.append(r)
        return merged[:limit]

    async def search(self, query: str, university: str = "", limit: int = 20) -> list[dict]:
        """默认检索方法：混合搜索。"""
        return await self.search_hybrid(query, university, limit)

    def search_by_university(self, university: str) -> list[dict]:
        """按高校名精确检索。"""
        if not self._ready or not university:
            return []
        return [r for r in self._rows if r["university"] == university]

    def get_stats(self, university: str = "") -> dict:
        """获取统计数据。"""
        if not self._ready:
            return {}
        rows = self._rows if not university else [r for r in self._rows if r["university"] == university]
        total = len(rows)
        with_email = sum(1 for r in rows if r.get("email"))
        depts = set(r.get("department", "") for r in rows if r.get("department"))
        return {
            "total": total,
            "with_email": with_email,
            "no_email": total - with_email,
            "departments": len(depts),
            "universities": len(set(r["university"] for r in rows)) if not university else None,
        }

    def clear(self):
        """清空所有数据。"""
        self._rows = []
        self._vectors = []
        self._save()
        logger.info("[DataMemory] 已清空所有数据")


# ── 便捷函数 ──

async def search_data(query: str, university: str = "", limit: int = 20) -> list[dict]:
    """便捷函数：触发 embedding 后执行混合搜索。"""
    dm = DataMemory.get_instance()
    # 如果有未 embedding 的数据，异步触发（不阻塞查询）
    await dm.embed_all()
    return await dm.search(query, university, limit)


def index_csv_to_memory(csv_path: str, university: str, task_id: str) -> int:
    """便捷函数：同步索引 CSV 到 DataMemory（用于任务完成后的自动索引）。"""
    return DataMemory.get_instance().index_csv(csv_path, university, task_id)
