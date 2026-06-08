"""增量爬取可靠性保障 — 前置备份 + Diff 校验 + 自动回滚"""

from __future__ import annotations

import csv
import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 阈值常量 ──

FATAL_ROW_DECREASE_RATIO = 0.80   # 行数减少超过 20% → 致命
WARN_ROW_DECREASE_RATIO = 0.95    # 行数减少 5%~20% → 警告
WARN_EMAIL_RATE_DROP = 0.30       # 邮箱有效率下降超 30 个百分点 → 警告

# 邮箱正则
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# CSV 列名别名映射 → 规范名
_COLUMN_ALIASES = {
    "姓名": "姓名", "教师姓名": "姓名",
    "邮箱": "邮箱", "email": "邮箱", "电子邮箱": "邮箱",
    "学院": "学院", "所在学院": "学院", "院系": "学院", "所属院系": "学院",
    "职称": "职称",
    "主页链接": "主页链接", "官网主页链接": "主页链接",
    "序号": "序号",
    "院校名称": "院校名称",
}


@dataclass
class DiffResult:
    """新旧数据对比结果"""
    old_rows: int = 0
    new_rows: int = 0
    added_rows: int = 0
    changed_rows: int = 0      # 姓名+学院 相同但邮箱/职称不同
    removed_rows: int = 0
    old_email_rate: float = 0.0
    new_email_rate: float = 0.0
    is_fatal: bool = False
    is_warning: bool = False
    fatal_reasons: list[str] = field(default_factory=list)
    warn_reasons: list[str] = field(default_factory=list)
    summary: str = ""


# ── 公开 API ──

def find_main_csv(task_dir: str | Path) -> Path | None:
    """在任务目录中找主 CSV 文件（排除 backup_ 前缀的）。"""
    task_dir = Path(task_dir)
    if not task_dir.exists():
        return None
    csv_files = sorted(
        f for f in task_dir.glob("*.csv")
        if not f.name.startswith("backup_") and f.stat().st_size > 50
    )
    if not csv_files:
        return None
    # 优先返回最大的那个（最可能是完整数据）
    return max(csv_files, key=lambda f: f.stat().st_size)


def backup_csv(task_dir: str | Path) -> Path | None:
    """在增量任务启动前，复制主 CSV → backup_{timestamp}.csv。返回备份路径。"""
    src = find_main_csv(task_dir)
    if src is None:
        logger.info("[Reliability] 无现有 CSV 可备份，跳过")
        return None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = src.parent / f"backup_{ts}.csv"
    shutil.copy2(src, dst)
    logger.info(f"[Reliability] 已备份: {src.name} → {dst.name} ({src.stat().st_size} bytes)")
    return dst


def compute_diff(backup_path: str | Path, task_dir: str | Path) -> DiffResult:
    """对比备份 CSV 和当前主 CSV，计算差异。

    返回 DiffResult。若找不到新 CSV 则返回 is_fatal=True 的哨兵结果。
    """
    backup_path = Path(backup_path)
    task_dir = Path(task_dir)

    new_csv = find_main_csv(task_dir)
    if new_csv is None:
        return DiffResult(
            is_fatal=True,
            fatal_reasons=["增量任务完成后未找到任何 CSV 产物"],
            summary="❌ 致命：任务未产出 CSV 文件",
        )

    old_records = _read_csv(backup_path)
    new_records = _read_csv(new_csv)

    old_keyed = {_row_key(r): r for r in old_records}
    new_keyed = {_row_key(r): r for r in new_records}
    old_keys = set(old_keyed.keys())
    new_keys = set(new_keyed.keys())

    added = len(new_keys - old_keys)
    removed = len(old_keys - new_keys)
    common = old_keys & new_keys
    changed = sum(
        1 for k in common
        if old_keyed[k].get("邮箱") != new_keyed[k].get("邮箱")
        or old_keyed[k].get("职称") != new_keyed[k].get("职称")
    )

    old_email_count = sum(1 for r in old_records if _has_email(r))
    new_email_count = sum(1 for r in new_records if _has_email(r))
    old_email_rate = old_email_count / len(old_records) if old_records else 0.0
    new_email_rate = new_email_count / len(new_records) if new_records else 0.0

    result = DiffResult(
        old_rows=len(old_records),
        new_rows=len(new_records),
        added_rows=added,
        changed_rows=changed,
        removed_rows=removed,
        old_email_rate=old_email_rate,
        new_email_rate=new_email_rate,
    )

    _evaluate(result, old_rows=len(old_records))
    result.summary = _build_summary(result)
    return result


def auto_rollback(backup_path: str | Path, task_dir: str | Path) -> Path | None:
    """从备份恢复数据：用 backup 覆盖当前主 CSV。返回恢复后的文件路径。"""
    backup_path = Path(backup_path)
    task_dir = Path(task_dir)

    current = find_main_csv(task_dir)
    target = current or (task_dir / "data.csv")

    shutil.copy2(backup_path, target)
    logger.warning(
        f"[Reliability] ⚠️ 自动回滚: {backup_path.name} → {target.name}"
    )
    return target


# ── 内部辅助 ──

def _read_csv(path: Path) -> list[dict[str, str]]:
    """读取 CSV，自动识别并规范化列名。"""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []

    reader = csv.DictReader(StringIO(text))
    if reader.fieldnames is None:
        return []

    normalized_fields = [_normalize_column(f) for f in reader.fieldnames]
    records: list[dict[str, str]] = []
    for row in reader:
        record: dict[str, str] = {}
        for raw_key, norm_key in zip(reader.fieldnames or [], normalized_fields):
            value = row.get(raw_key, "") or ""
            if norm_key:  # 忽略无法识别的列
                record[norm_key] = value.strip()
        # 至少要有姓名或邮箱才计入
        if record.get("姓名") or record.get("邮箱"):
            records.append(record)
    return records


def _normalize_column(name: str) -> str:
    """将原始列名映射为规范名，无法识别则返回空字符串。"""
    cleaned = name.strip().replace("﻿", "")  # 去 BOM
    return _COLUMN_ALIASES.get(cleaned, cleaned)


def _row_key(record: dict[str, str]) -> str:
    """生成行的复合键：姓名 + 学院（用于去重匹配）。"""
    name = record.get("姓名", "").strip()
    dept = record.get("学院", "").strip()
    return f"{name}|{dept}"


def _has_email(record: dict[str, str]) -> bool:
    """判断记录中是否包含有效邮箱。"""
    email = record.get("邮箱", "")
    return bool(email and _EMAIL_RE.search(email))


def _evaluate(result: DiffResult, *, old_rows: int) -> None:
    """根据阈值规则填充 is_fatal / is_warning / 原因列表。"""
    # 行数致命判定：新行数 < 旧行数 × 80%
    if old_rows > 0 and result.new_rows < old_rows * FATAL_ROW_DECREASE_RATIO:
        result.is_fatal = True
        pct = (1 - result.new_rows / old_rows) * 100
        result.fatal_reasons.append(
            f"数据行数从 {old_rows} 骤降至 {result.new_rows}（减少 {pct:.0f}%，超过 20% 阈值）"
        )

    # 行数警告判定：新行数 < 旧行数 × 95%
    if old_rows > 0 and not result.is_fatal and result.new_rows < old_rows * WARN_ROW_DECREASE_RATIO:
        result.is_warning = True
        pct = (1 - result.new_rows / old_rows) * 100
        result.warn_reasons.append(
            f"数据行数从 {old_rows} 减少至 {result.new_rows}（减少 {pct:.1f}%）"
        )

    # 邮箱率警告判定：下降超 30 个百分点
    rate_drop = result.old_email_rate - result.new_email_rate
    if rate_drop > WARN_EMAIL_RATE_DROP:
        result.is_warning = True
        result.warn_reasons.append(
            f"邮箱有效率从 {result.old_email_rate:.0%} 降至 {result.new_email_rate:.0%}"
            f"（下降 {rate_drop:.0%}）"
        )


def _build_summary(result: DiffResult) -> str:
    """构建人类可读的 Diff 摘要。"""
    parts: list[str] = []

    if result.is_fatal:
        parts.append("## 🔴 增量 Diff 摘要 — 致命错误\n")
        for r in result.fatal_reasons:
            parts.append(f"- 🔴 {r}")
    elif result.is_warning:
        parts.append("## 🟡 增量 Diff 摘要 — 警告\n")
        for r in result.warn_reasons:
            parts.append(f"- 🟡 {r}")
    else:
        parts.append("## 🟢 增量 Diff 摘要 — 正常\n")

    parts.append(f"- 旧数据: {result.old_rows} 行 | 新数据: {result.new_rows} 行")
    parts.append(
        f"- 新增: +{result.added_rows} | 变更: ~{result.changed_rows}"
        f" | 移除: -{result.removed_rows}"
    )
    parts.append(
        f"- 邮箱率: {result.old_email_rate:.1%} → {result.new_email_rate:.1%}"
    )

    return "\n".join(parts)
