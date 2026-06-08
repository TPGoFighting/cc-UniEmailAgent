"""质量评估模块 — 对爬取结果做完整质量评估，生成 quality_report.json。

评估维度：
  1. 邮箱覆盖率 — 有邮箱的记录/总记录
  2. 数据完整性 — 必填字段空值率
  3. 邮箱格式校验 — 正则校验
  4. 学院覆盖率 — 对比配置中的学院列表
  5. 脏数据检测 — 姓名列是否含非人名内容
  6. 去重率 — 重复邮箱/重复姓名比例
  7. 职称分布 — 统计各职称数量

所有评估函数纯本地运行，无外部 API 调用。
"""

import csv
import json
import logging
import re
from pathlib import Path
from collections import Counter

logger = logging.getLogger(__name__)

# ── 邮箱正则（与 constants.EMAIL_RE 保持一致） ──
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# ── 脏数据关键词 — 姓名列中出现这些说明不是真实人名 ──
_DIRTY_NAME_KEYWORDS = [
    "首页", "返回", "更多", "详情", "查看", "下载", "搜索", "登录", "注册",
    "师资队伍", "教授", "副教授", "讲师", "助教", "首页", "上一页", "下一页",
    "English", "Home", "About", "Contact", "Faculty", "Staff",
    "学院概况", "学院简介", "新闻", "通知", "公告", "招生", "培养",
    "学术报告", "学术讲座", "科研团队", "教师名录", "教师列表",
    "网站首页", "网站地图", "友情链接", "版权信息",
    "书记信箱", "院长信箱", "联系我们", "关于我们",
    "上一页", "下一页", "末页", "第", "页",
    "共", "条记录", "每页", "显示",
    "院士", "研究员", "副研究员", "工程师", "高级工程师",
]


def _is_valid_email(email: str) -> bool:
    """校验单个邮箱格式。"""
    if not email or not email.strip():
        return False
    return bool(_EMAIL_RE.match(email.strip()))


def _is_dirty_name(name: str) -> bool:
    """检测姓名是否可能为脏数据（导航文字、系统字段等）。"""
    name = name.strip()
    if not name:
        return True
    # 长度异常
    if len(name) < 2 or len(name) > 6:
        return True
    # 含数字或特殊符号
    if re.search(r"[0-9@#￥%&*()（）《》【】\[\]]", name):
        return True
    # 纯英文且很短
    if re.match(r"^[A-Za-z\s]{1,15}$", name):
        return True
    # 包含脏数据关键词
    if any(kw in name for kw in _DIRTY_NAME_KEYWORDS):
        return True
    # 至少包含2个汉字
    if not re.search(r"[一-鿿]{2,}", name):
        return True
    return False


def validate_crawl_output(
    csv_path: str,
    task_id: str = "",
    university_config: dict | None = None,
) -> dict:
    """对爬取结果做完整质量评估，返回评估报告字典。

    Args:
        csv_path: CSV 文件路径
        task_id: 任务 ID（可选，用于日志）
        university_config: 大学配置字典，可选字段：
            - departments: list[str] — 期望的学院列表
            - min_email_rate: float — 最低邮箱覆盖率阈值（默认 0.7）

    Returns:
        评估报告字典，包含 quality_score、passed、warnings 等字段。
    """
    path = Path(csv_path)
    report = {
        "task_id": task_id,
        "csv_file": str(path.name),
        "quality_score": 0,
        "passed": False,
        "warnings": [],
        "details": {
            "total_rows": 0,
            "email_coverage": {},
            "completeness": {},
            "email_validation": {},
            "department_coverage": {},
            "dirty_data": {},
            "dedup": {},
            "title_distribution": {},
        },
    }

    if not path.exists():
        report["warnings"].append(f"CSV 文件不存在: {csv_path}")
        return report

    # ── 读取 CSV ──
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as e:
        report["warnings"].append(f"CSV 读取失败: {e}")
        return report

    total = len(rows)
    report["details"]["total_rows"] = total
    if total == 0:
        report["warnings"].append("CSV 文件为空（无数据行）")
        return report

    # 自动检测列名（兼容中文/英文）
    col_name = _find_col(rows[0] if rows else {}, ["姓名", "name"])
    col_email = _find_col(rows[0] if rows else {}, ["邮箱", "email"])
    col_dept = _find_col(rows[0] if rows else {}, ["学院", "department", "dept"])
    col_title = _find_col(rows[0] if rows else {}, ["职称", "title"])

    # ── 1. 邮箱覆盖率 ──
    email_count = sum(1 for r in rows if r.get(col_email, "").strip())
    email_rate = email_count / total if total > 0 else 0
    min_rate = (university_config or {}).get("min_email_rate", 0.7)
    report["details"]["email_coverage"] = {
        "total_rows": total,
        "rows_with_email": email_count,
        "rows_without_email": total - email_count,
        "rate": round(email_rate, 4),
    }
    if email_rate < min_rate:
        report["warnings"].append(
            f"邮箱覆盖率 {email_rate:.1%} 低于阈值 {min_rate:.0%}（{email_count}/{total}）"
        )

    # ── 2. 数据完整性（必填字段空值率） ──
    completeness = {}
    for field, col in [("姓名", col_name), ("邮箱", col_email), ("学院", col_dept)]:
        if col:
            empty = sum(1 for r in rows if not r.get(col, "").strip())
            completeness[field] = {
                "total": total,
                "empty": empty,
                "fill_rate": round(1 - empty / total, 4) if total > 0 else 0,
            }
            if empty > total * 0.5:
                report["warnings"].append(f"字段「{field}」空值率超过 50%（{empty}/{total}）")
    report["details"]["completeness"] = completeness

    # ── 3. 邮箱格式校验 ──
    valid_emails = 0
    invalid_emails = 0
    invalid_samples: list[str] = []
    for r in rows:
        email = r.get(col_email, "").strip()
        if email:
            if _is_valid_email(email):
                valid_emails += 1
            else:
                invalid_emails += 1
                if len(invalid_samples) < 5:
                    invalid_samples.append(email)
    report["details"]["email_validation"] = {
        "total_emails": email_count,
        "valid": valid_emails,
        "invalid": invalid_emails,
        "invalid_samples": invalid_samples,
    }
    if invalid_emails > 0:
        report["warnings"].append(
            f"发现 {invalid_emails} 个格式异常的邮箱"
            + (f"（如 {', '.join(invalid_samples[:3])}）" if invalid_samples else "")
        )

    # ── 4. 学院覆盖率 ──
    expected_depts = (university_config or {}).get("departments", [])
    if expected_depts and col_dept:
        actual_depts: set[str] = set()
        for r in rows:
            dept = r.get(col_dept, "").strip()
            if dept:
                actual_depts.add(dept)
        matched = []
        missing = []
        for expected in expected_depts:
            # 模糊匹配：expected 的前2个字在 actual 中任一学院出现
            found = any(expected[:2] in d for d in actual_depts)
            if found:
                matched.append(expected)
            else:
                missing.append(expected)
        report["details"]["department_coverage"] = {
            "expected_count": len(expected_depts),
            "matched_count": len(matched),
            "actual_count": len(actual_depts),
            "matched": matched,
            "missing": missing,
            "actual_departments": sorted(actual_depts),
        }
        if missing:
            report["warnings"].append(
                f"学院覆盖率 {len(matched)}/{len(expected_depts)}，"
                f"缺失: {', '.join(missing[:5])}"
            )
    elif not col_dept:
        report["details"]["department_coverage"] = {"note": "未检测到学院列"}

    # ── 5. 脏数据检测 ──
    if col_name:
        dirty_count = sum(1 for r in rows if _is_dirty_name(r.get(col_name, "")))
        dirty_rate = dirty_count / total if total > 0 else 0
        dirty_samples = []
        for r in rows:
            name = r.get(col_name, "").strip()
            if _is_dirty_name(name) and len(dirty_samples) < 10:
                dirty_samples.append(name)
        report["details"]["dirty_data"] = {
            "total_rows": total,
            "dirty_count": dirty_count,
            "dirty_rate": round(dirty_rate, 4),
            "dirty_samples": dirty_samples,
        }
        if dirty_count > 0:
            report["warnings"].append(
                f"检测到 {dirty_count} 条脏数据（姓名列含非人名的系统文字/导航词）"
            )
    else:
        report["details"]["dirty_data"] = {"note": "未检测到姓名列"}

    # ── 6. 去重率 ──
    if col_email and col_name:
        seen_emails: set[str] = set()
        seen_names: set[str] = set()
        dup_email = 0
        dup_name = 0
        for r in rows:
            email = r.get(col_email, "").strip()
            name = r.get(col_name, "").strip()
            if email:
                if email in seen_emails:
                    dup_email += 1
                else:
                    seen_emails.add(email)
            if name:
                if name in seen_names:
                    dup_name += 1
                else:
                    seen_names.add(name)
        report["details"]["dedup"] = {
            "total_rows": total,
            "duplicate_emails": dup_email,
            "duplicate_names": dup_name,
            "unique_emails": len(seen_emails),
            "unique_names": len(seen_names),
        }
        if dup_email > 0:
            report["warnings"].append(f"发现 {dup_email} 个重复邮箱")
        if dup_name > 0:
            report["warnings"].append(f"发现 {dup_name} 个重复姓名（含不同邮箱）")
    else:
        report["details"]["dedup"] = {"note": "缺少姓名或邮箱列，跳过去重检测"}

    # ── 7. 职称分布 ──
    if col_title:
        title_counts: Counter[str] = Counter()
        for r in rows:
            title = r.get(col_title, "").strip()
            if title:
                title_counts[title] += 1
        report["details"]["title_distribution"] = dict(
            title_counts.most_common(20)
        )
    else:
        report["details"]["title_distribution"] = {"note": "未检测到职称列"}

    # ── 计算综合质量分数 ──
    score = _compute_quality_score(report["details"], report["warnings"], email_rate)
    report["quality_score"] = score
    report["passed"] = score >= 60 and len(report["warnings"]) <= 3

    logger.info(
        f"质量评估完成: {path.name} — score={score}, passed={report['passed']}, "
        f"warnings={len(report['warnings'])}"
    )
    return report


def _find_col(row: dict, candidates: list[str]) -> str:
    """从候选列名中找到实际存在的列名。"""
    for c in candidates:
        if c in row:
            return c
    return candidates[0]  # 回退到第一个候选


def _compute_quality_score(details: dict, warnings: list[str], email_rate: float) -> int:
    """根据各维度计算综合质量分数 (0-100)。"""
    score = 100

    # 邮箱覆盖率（权重 30）
    if email_rate == 0:
        score -= 45  # 零邮箱严重扣分，确保 passed=False
    elif email_rate < 0.3:
        score -= 30
    elif email_rate < 0.5:
        score -= 20
    elif email_rate < 0.7:
        score -= 10

    # 数据完整性（权重 20）
    completeness: dict = details.get("completeness", {})
    for field_info in completeness.values():
        if isinstance(field_info, dict):
            fill_rate = field_info.get("fill_rate", 1)
            if fill_rate < 0.3:
                score -= 10
            elif fill_rate < 0.5:
                score -= 5

    # 邮箱格式（权重 15）
    email_val: dict = details.get("email_validation", {})
    if isinstance(email_val, dict) and email_val.get("total_emails", 0) > 0:
        invalid = email_val.get("invalid", 0)
        invalid_rate = invalid / email_val["total_emails"]
        if invalid_rate > 0.3:
            score -= 15
        elif invalid_rate > 0.1:
            score -= 8
        elif invalid_rate > 0:
            score -= 3

    # 脏数据（权重 20）
    dirty: dict = details.get("dirty_data", {})
    if isinstance(dirty, dict) and "dirty_rate" in dirty:
        dirty_rate = dirty["dirty_rate"]
        if dirty_rate > 0.3:
            score -= 20
        elif dirty_rate > 0.1:
            score -= 10
        elif dirty_rate > 0:
            score -= 3

    # 去重（权重 10）
    dedup: dict = details.get("dedup", {})
    if isinstance(dedup, dict) and "total_rows" in dedup:
        dup_total = dedup.get("duplicate_emails", 0)
        total = dedup["total_rows"]
        if total > 0:
            dup_rate = dup_total / total
            if dup_rate > 0.3:
                score -= 10
            elif dup_rate > 0.1:
                score -= 5

    # 学院缺失（权重 5）
    dept_coverage: dict = details.get("department_coverage", {})
    if isinstance(dept_coverage, dict) and "missing" in dept_coverage:
        missing = dept_coverage["missing"]
        expected = dept_coverage.get("expected_count", 0)
        if expected > 0 and missing:
            miss_rate = len(missing) / expected
            if miss_rate > 0.5:
                score -= 5
            elif miss_rate > 0:
                score -= 2

    return max(0, score)


def save_quality_report(report: dict, task_dir: str) -> str:
    """将评估报告保存到 {task_dir}/quality_report.json。

    Returns:
        保存的文件路径。
    """
    dir_path = Path(task_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    filepath = dir_path / "quality_report.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info(f"质量报告已保存: {filepath}")
    return str(filepath)


def load_quality_report(task_dir: str) -> dict | None:
    """加载已有评估报告。

    Returns:
        报告字典，若文件不存在返回 None。
    """
    filepath = Path(task_dir) / "quality_report.json"
    if not filepath.exists():
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"加载质量报告失败: {e}")
        return None
