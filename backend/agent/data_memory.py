"""DataMemory — 爬取结果数据的存储与检索。

与 CrawlMemory（存储爬取经验）分开，使用独立的 JSON 文件和独立的 Qdrant 集合。
"""
import json
import os
import logging
import re
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_DATA_FILE = _DATA_DIR / "data_memory.json"
_VECTOR_DIR = _DATA_DIR / "data_vectors"

_EMBEDDING_DIM = 768  # sentence-transformers/all-MiniLM-L6-v2

class DataMemory:
    """爬取结果数据的存储与检索，与 CrawlMemory 完全独立。"""

    _instance: "DataMemory | None" = None

    def __init__(self):
        self._rows: list[dict] = []
        self._vectors: list[list[float]] = []
        self._ready = False
        self._load()

    def _load(self):
        """从 JSON 文件加载已有数据。"""
        try:
            if _DATA_FILE.exists():
                with open(_DATA_FILE, encoding="utf-8") as f:
                    raw = json.load(f)
                self._rows = raw.get("rows", [])
                self._vectors = raw.get("vectors", [])
                logger.info(f"[DataMemory] 已加载 {len(self._rows)} 条数据记录")
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
                    self._vectors.append([])  # 占位，后续可用 embedding 填充
                    added += 1

            self._save()
            logger.info(f"[DataMemory] 已索引 {added} 条记录 ({university})")
        except Exception as e:
            logger.warning(f"[DataMemory] 索引失败: {e}")
        return added

    # ── 检索 ──────────────────────────────────────────

    def search(self, query: str, university: str = "", limit: int = 20) -> list[dict]:
        """关键词搜索数据记录。返回匹配的记录列表。"""
        if not self._ready or not self._rows:
            return []

        query_lower = query.lower()
        # 提取关键词：中文词 + 英文词
        words = re.findall(r"[\w\u4e00-\u9fff]+", query_lower)
        if not words:
            return []

        scored = []
        for row in self._rows:
            if university and row["university"] != university:
                continue
            text_lower = row["text"].lower()
            score = sum(1 for w in words if w in text_lower)
            if score > 0:
                scored.append((score, row))

        scored.sort(key=lambda x: -x[0])
        return [r for _, r in scored[:limit]]

    def search_by_university(self, university: str) -> list[dict]:
        """按大学名检索所有数据。"""
        if not self._ready:
            return []
        return [r for r in self._rows if r["university"] == university]

    def get_stats(self, university: str = "") -> dict:
        """获取统计数据。"""
        rows = self._rows
        if university:
            rows = [r for r in rows if r["university"] == university]
        if not rows:
            return {"total": 0}
        depts = set(r["department"] for r in rows if r["department"])
        titles = {}
        for r in rows:
            t = r["title"] or "未知"
            titles[t] = titles.get(t, 0) + 1
        return {
            "total": len(rows),
            "with_email": len([r for r in rows if r["email"]]),
            "departments": len(depts),
            "title_distribution": titles,
        }

    def universities(self) -> list[str]:
        """返回已索引的大学列表。"""
        return sorted(set(r["university"] for r in self._rows))


# ── 快捷函数 ──────────────────────────────────────────

def search_data(query: str, university: str = "") -> list[dict]:
    """搜索爬取数据。"""
    try:
        return DataMemory.get_instance().search(query, university)
    except Exception:
        return []

def index_csv_to_memory(csv_path: str, university: str, task_id: str) -> int:
    """索引 CSV 到 DataMemory。"""
    try:
        return DataMemory.get_instance().index_csv(csv_path, university, task_id)
    except Exception:
        return 0
