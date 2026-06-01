"""对话历史持久化管理器 — JSON 文件存储。"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
INDEX_FILE = DATA_DIR / "index.json"

# 敏感信息过滤模式：匹配常见 API Key、Token、密码等
_SENSITIVE_PATTERNS = [
    # XCrawl API Key: xc-xxx
    (re.compile(r'(?i)(xcrawl_api_key["\']?\s*[:=]\s*["\']?)(xc-[a-zA-Z0-9]{20,})(["\'\s,\]}])'), r'\1***REDACTED***\3'),
    # OpenAI / 通用 sk- 开头的 key
    (re.compile(r'(?i)(["\']?\w*api_key["\']?\s*[:=]\s*["\']?)(sk-[a-zA-Z0-9]{20,})(["\'\s,\]}])'), r'\1***REDACTED***\3'),
    # 通用 authorization / bearer token
    (re.compile(r'(?i)(authorization["\']?\s*[:=]\s*["\']?(?:bearer\s+)?)[a-zA-Z0-9._-]{20,}(["\'\s,\]}])'), r'\1***REDACTED***\2'),
    # 通用 password / passwd / secret
    (re.compile(r'(?i)(password["\']?\s*[:=]\s*["\']?)[^\s"\'\]\)]{4,}(["\'\s,\]}])'), r'\1***REDACTED***\2'),
]


def _filter_sensitive(text: str) -> str:
    """过滤文本中的敏感信息（API Key、Token、密码等）。"""
    if not isinstance(text, str):
        return text
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _atomic_write(filepath: Path, data) -> None:
    """原子写入：先写临时文件，再重命名，防止写入中断导致文件损坏。"""
    import time
    tmp = filepath.with_suffix(filepath.suffix + ".tmp")
    for i in range(10):
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, filepath)  # Windows/Linux 均为原子操作
            return
        except PermissionError:
            if i == 9:
                raise
            time.sleep(0.05)


def _ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)


class HistoryManager:
    """管理对话历史的持久化存储。

    结构：
    - data/index.json  → [{"id": "task-xxx", "title": "...", "date": "...", "status": "..."}]
    - data/{task_id}.json  → {"id": "task-xxx", "title": "...", "date": "...", "status": "...", "messages": [...]}
    """

    def create_task(self, task_id: str, title: str) -> dict:
        """创建新任务条目，返回任务元数据。"""
        _ensure_data_dir()
        now = datetime.now()
        task = {
            "id": task_id,
            "title": _filter_sensitive(title[:80]),
            "date": now.strftime("%Y-%m-%d"),
            "status": "running",
            "messages": [],
        }
        self._save(task)
        self._update_index(task_id, task["title"], task["date"], "running")
        return task

    def add_message(self, task_id: str, message: dict) -> None:
        """向指定任务追加一条消息（自动过滤敏感信息）。"""
        task = self._load(task_id)
        if task is None:
            logger.warning(f"任务 {task_id} 不存在，无法追加消息")
            return
        # 过滤消息内容中的敏感信息
        filtered = message.copy()
        for field in ("content", "message"):
            if field in filtered and isinstance(filtered[field], str):
                filtered[field] = _filter_sensitive(filtered[field])
        task["messages"].append(filtered)
        self._save(task)

    def update_status(self, task_id: str, status: str) -> None:
        """更新任务状态（completed / failed / running）。"""
        task = self._load(task_id)
        if task is None:
            logger.warning(f"任务 {task_id} 不存在，无法更新状态")
            return
        task["status"] = status
        self._save(task)
        self._update_index(task_id, task.get("title", ""), task.get("date", ""), status)

    def get_all(self) -> list[dict]:
        """获取所有历史任务（不含消息内容，仅元数据）。"""
        _ensure_data_dir()
        if not INDEX_FILE.exists():
            return []
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 按日期倒序
            data.sort(key=lambda t: t.get("date", ""), reverse=True)
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"读取历史索引失败: {e}")
            return []

    def get(self, task_id: str) -> dict | None:
        """获取指定任务的完整记录（含消息）。"""
        task = self._load(task_id)
        if task is None:
            return None
        # 过滤掉 messages 中的占位空数组 guard
        return task

    def rename_task(self, task_id: str, new_title: str) -> dict | None:
        """重命名任务。"""
        task = self._load(task_id)
        if task is None:
            return None
        title = _filter_sensitive(new_title[:80])
        task["title"] = title
        self._save(task)
        self._update_index(task_id, title, task.get("date", ""), task.get("status", "completed"), task.get("pinned", False))
        return task

    def toggle_pin(self, task_id: str) -> dict | None:
        """切换置顶状态。"""
        task = self._load(task_id)
        if task is None:
            return None
        task["pinned"] = not task.get("pinned", False)
        self._save(task)
        self._update_index(task_id, task.get("title", ""), task.get("date", ""), task.get("status", "completed"), task["pinned"])
        return task

    def delete_task(self, task_id: str) -> bool:
        """删除任务文件并从索引中移除。"""
        fp = self._filepath(task_id)
        if fp.exists():
            fp.unlink()
        self._remove_from_index(task_id)
        return True

    def search(self, query: str) -> list[dict]:
        """按标题模糊搜索（大小写不敏感）。"""
        _ensure_data_dir()
        if not INDEX_FILE.exists():
            return []
        q = query.lower().strip()
        if not q:
            return self.get_all()
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
        results = [t for t in data if q in t.get("title", "").lower()]
        results.sort(key=lambda t: t.get("date", ""), reverse=True)
        return results

    def _remove_from_index(self, task_id: str) -> None:
        """从索引中删除指定任务。"""
        _ensure_data_dir()
        if not INDEX_FILE.exists():
            return
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                tasks = json.load(f)
        except (json.JSONDecodeError, OSError):
            return
        tasks = [t for t in tasks if t.get("id") != task_id]
        try:
            _atomic_write(INDEX_FILE, tasks)
        except OSError as e:
            logger.error(f"更新索引失败: {e}")

    def _filepath(self, task_id: str) -> Path:
        """获取任务文件路径（防止路径遍历）。"""
        safe = task_id.replace("/", "_").replace("\\", "_").replace("..", "_")
        return DATA_DIR / f"{safe}.json"

    def _save(self, task: dict) -> None:
        """原子写入单个任务文件。"""
        _ensure_data_dir()
        fp = self._filepath(task["id"])
        try:
            _atomic_write(fp, task)
        except OSError as e:
            logger.error(f"保存任务 {task['id']} 失败: {e}")

    def _load(self, task_id: str) -> dict | None:
        """读取单个任务文件。"""
        import time
        fp = self._filepath(task_id)
        if not fp.exists():
            return None
        for i in range(10):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    return json.load(f)
            except PermissionError:
                if i == 9:
                    raise
                time.sleep(0.05)
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"读取任务 {task_id} 失败: {e}")
                return None

    def _update_index(self, task_id: str, title: str, date: str, status: str, pinned: bool = False) -> None:
        """更新索引文件。"""
        _ensure_data_dir()
        tasks = []
        if INDEX_FILE.exists():
            try:
                with open(INDEX_FILE, "r", encoding="utf-8") as f:
                    tasks = json.load(f)
            except (json.JSONDecodeError, OSError):
                tasks = []

        # 更新或插入
        found = False
        for t in tasks:
            if t.get("id") == task_id:
                t["title"] = title
                t["date"] = date
                t["status"] = status
                t["pinned"] = pinned
                found = True
                break
        if not found:
            tasks.insert(0, {"id": task_id, "title": title, "date": date, "status": status, "pinned": pinned})

        try:
            _atomic_write(INDEX_FILE, tasks)
        except OSError as e:
            logger.error(f"更新索引失败: {e}")


# 全局单例
history = HistoryManager()
