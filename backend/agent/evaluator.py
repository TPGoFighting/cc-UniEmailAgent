"""质量评估模块 — 对爬取结果做完整质量评估，生成 quality_report.json。"""
import csv, json, logging, re
from pathlib import Path
from collections import Counter

logger = logging.getLogger(__name__)
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_DIRTY_NAME_KEYWORDS = ["首页", "返回", "更多", "详情", "查看", "下载", "搜索", "登录", "注册",
    "师资队伍", "教授", "副教授", "讲师", "助教", "English", "学院概况",
    "新闻", "通知", "公告", "招生", "培养", "教师名录", "教师列表",
    "书记信箱", "院长信箱", "联系我们", "关于我们", "院士", "研究员"]


def _is_valid_email(email: str) -> bool:
    return bool(email.strip() and _EMAIL_RE.match(email.strip()))

def _is_dirty_name(name: str) -> bool:
    name = name.strip()
    if not name or len(name) < 2 or len(name) > 6: return True
    if re.search(r"[0-9@#￥%&*()（）《》【】\[\]]", name): return True
    if any(kw in name for kw in _DIRTY_NAME_KEYWORDS): return True
    return not bool(re.search(r"[一-鿿]{2,}", name))

def _find_col(row: dict, candidates: list[str]) -> str:
    for c in candidates:
        if c in row: return c
    return candidates[0]

def validate_crawl_output(csv_path: str, task_id: str = "", university_config: dict | None = None) -> dict:
    path = Path(csv_path)
    report = {"task_id": task_id, "csv_file": str(path.name), "quality_score": 0, "passed": False,
              "warnings": [], "details": {"total_rows": 0, "email_coverage": {}, "completeness": {},
                                          "email_validation": {}, "department_coverage": {},
                                          "dirty_data": {}, "dedup": {}, "title_distribution": {}}}
    if not path.exists():
        report["warnings"].append(f"CSV 文件不存在: {csv_path}")
        return report
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    except Exception as e:
        report["warnings"].append(f"CSV 读取失败: {e}")
        return report

    total = len(rows)
    report["details"]["total_rows"] = total
    if total == 0:
        report["warnings"].append("CSV 文件为空")
        return report

    col_name = _find_col(rows[0], ["姓名", "name"])
    col_email = _find_col(rows[0], ["邮箱", "email"])
    col_dept = _find_col(rows[0], ["学院", "department", "dept"])
    col_title = _find_col(rows[0], ["职称", "title"])

    email_count = sum(1 for r in rows if r.get(col_email, "").strip())
    email_rate = email_count / total if total else 0
    min_rate = (university_config or {}).get("min_email_rate", 0.7)
    report["details"]["email_coverage"] = {"total_rows": total, "rows_with_email": email_count,
        "rows_without_email": total - email_count, "rate": round(email_rate, 4)}
    if email_rate < min_rate:
        report["warnings"].append(f"邮箱覆盖率 {email_rate:.1%} 低于阈值 {min_rate:.0%}（{email_count}/{total}）")

    for field, col in [("姓名", col_name), ("邮箱", col_email), ("学院", col_dept)]:
        if col:
            empty = sum(1 for r in rows if not r.get(col, "").strip())
            report["details"]["completeness"][field] = {"total": total, "empty": empty,
                "fill_rate": round(1 - empty / total, 4) if total else 0}
            if empty > total * 0.5:
                report["warnings"].append(f"字段「{field}」空值率超过 50%（{empty}/{total}）")

    valid_emails = invalid_emails = 0
    invalid_samples = []
    for r in rows:
        email = r.get(col_email, "").strip()
        if email:
            if _is_valid_email(email): valid_emails += 1
            else:
                invalid_emails += 1
                if len(invalid_samples) < 5: invalid_samples.append(email)
    report["details"]["email_validation"] = {"total_emails": email_count, "valid": valid_emails,
        "invalid": invalid_emails, "invalid_samples": invalid_samples}
    if invalid_emails > 0:
        report["warnings"].append(f"发现 {invalid_emails} 个格式异常的邮箱")

    if col_name:
        dirty_count = sum(1 for r in rows if _is_dirty_name(r.get(col_name, "")))
        dirty_samples = [r[col_name] for r in rows if _is_dirty_name(r[col_name])][:10]
        report["details"]["dirty_data"] = {"total_rows": total, "dirty_count": dirty_count,
            "dirty_rate": round(dirty_count / total, 4) if total else 0, "dirty_samples": dirty_samples}

    seen_emails, seen_names = set(), set()
    dup_email = dup_name = 0
    for r in rows:
        e = r.get(col_email, "").strip()
        n = r.get(col_name, "").strip()
        if e:
            if e in seen_emails: dup_email += 1
            else: seen_emails.add(e)
        if n:
            if n in seen_names: dup_name += 1
            else: seen_names.add(n)
    report["details"]["dedup"] = {"total_rows": total, "duplicate_emails": dup_email,
        "duplicate_names": dup_name, "unique_emails": len(seen_emails), "unique_names": len(seen_names)}

    if col_dept and university_config and "departments" in university_config:
        expected = set(university_config["departments"])
        actual = set(r.get(col_dept, "").strip() for r in rows if r.get(col_dept, "").strip())
        missing = expected - actual
        report["details"]["department_coverage"] = {
            "expected_count": len(expected),
            "actual_count": len(actual),
            "missing": sorted(missing),
            "covered": sorted(expected & actual),
        }

    if col_title:
        title_counts = Counter(r.get(col_title, "").strip() for r in rows if r.get(col_title, "").strip())
        report["details"]["title_distribution"] = dict(title_counts.most_common(20))

    score = 100
    if email_rate == 0: score -= 45
    elif email_rate < 0.3: score -= 30
    elif email_rate < 0.5: score -= 20
    elif email_rate < 0.7: score -= 10
    for fi in report["details"]["completeness"].values():
        if isinstance(fi, dict) and fi.get("fill_rate", 1) < 0.3: score -= 10
    if valid_emails > 0 and email_count > 0:
        inv_rate = invalid_emails / email_count
        if inv_rate > 0.3: score -= 15
        elif inv_rate > 0.1: score -= 8
    dirty_rate = report["details"]["dirty_data"].get("dirty_rate", 0)
    if dirty_rate > 0.3: score -= 20
    elif dirty_rate > 0.1: score -= 10
    if total > 0:
        dup_rate = dup_email / total
        if dup_rate > 0.3: score -= 5

    report["quality_score"] = max(0, score)
    report["passed"] = report["quality_score"] >= 60 and len(report["warnings"]) <= 3
    logger.info(f"质量评估: {path.name} — score={report['quality_score']}, passed={report['passed']}")
    return report

def save_quality_report(report: dict, task_dir: str) -> str:
    fp = Path(task_dir) / "quality_report.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return str(fp)
