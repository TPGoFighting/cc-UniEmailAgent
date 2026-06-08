"""Checkpoint — 断点续传支持。

爬取过程中每个学院完成后写入 checkpoint，中断后重新连接时自动跳过已完成学院。
"""
import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


def save_checkpoint(task_id: str, university: str, college: str, status: str,
                    total_colleges: int, done_colleges: list[dict],
                    output_files: list[str] = None) -> bool:
    """写入爬取进度 checkpoint。

    Args:
        task_id: 任务 ID
        university: 大学名称
        college: 刚完成的学院名
        status: "done" | "skipped" | "failed"
        total_colleges: 总学院数
        done_colleges: 已完成学院列表 [{"name": str, "found": int, "emails": int, "status": str}]
        output_files: 已生成的输出文件列表
    """
    try:
        cp_path = _checkpoint_path(task_id)
        cp = {
            "task_id": task_id,
            "university": university,
            "total_colleges": total_colleges,
            "done_colleges": done_colleges,
            "output_files": output_files or [],
            "updated_at": datetime.now().isoformat(),
            "last_college": college,
            "last_status": status,
        }
        cp_path.parent.mkdir(parents=True, exist_ok=True)
        cp_path.write_text(json.dumps(cp, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"[Checkpoint] {university} - {college}: {status} ({len(done_colleges)}/{total_colleges})")
        return True
    except Exception as e:
        logger.warning(f"[Checkpoint] 写入失败: {e}")
        return False


def load_checkpoint(task_id: str) -> dict | None:
    """读取 checkpoint，不存在返回 None。"""
    try:
        cp_path = _checkpoint_path(task_id)
        if cp_path.exists():
            return json.loads(cp_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[Checkpoint] 读取失败: {e}")
    return None


def get_resume_briefing(task_id: str, university: str) -> str | None:
    """生成断点续传简报。

    如果检测到已有 checkpoint，返回 markdown 格式的续传指引。
    """
    cp = load_checkpoint(task_id)
    if not cp:
        return None

    done_names = {c["name"] for c in cp.get("done_colleges", [])}
    total = cp.get("total_colleges", 0)
    done_count = len(done_names)

    if done_count == 0:
        return None

    lines = [
        f"## 🔄 断点续传 — {university}（已完成 {done_count}/{total} 个学院）\n",
        "以下学院已在之前执行中完成，**跳过不要重复爬取**：",
    ]
    for c in cp.get("done_colleges", []):
        found = c.get("found", 0)
        emails = c.get("emails", 0)
        lines.append(f"- ✅ {c['name']}（{found} 人, {emails} 邮箱）")

    lines.append(f"\n还有 {total - done_count} 个学院需要继续爬取。")
    return "\n".join(lines)


def clear_checkpoint(task_id: str) -> None:
    """任务完成后清理 checkpoint。"""
    try:
        cp_path = _checkpoint_path(task_id)
        if cp_path.exists():
            cp_path.unlink()
    except Exception:
        pass


def _checkpoint_path(task_id: str) -> Path:
    """获取 checkpoint 文件路径。"""
    from pathlib import Path
    base = Path(__file__).resolve().parent.parent / "outputs" / task_id.replace("/", "_").replace("\\", "_")
    return base / "checkpoint.json"
