"""
南京大学教师邮箱 — 最终合并清洗脚本

1. 加载现有数据（最终数据_20260601_223653.csv）
2. 清理垃圾邮箱（CSS/JS 误提取）
3. 加载增量爬取数据（南京大学_增量爬取_*.csv）
4. 智能合并：同名同学院优先保留有邮箱的版本
5. 导出 CSV + XLSX
"""

import csv
import json
import re
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"

LOOSE_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

PUBLIC_PREFIXES = [
    'webmaster', 'admin', 'office', 'info', 'master', 'root', 'postmaster',
    'wxyxz', 'xwcb', 'bgs', 'dangzheng', 'yuanban', 'dangban', 'renshi',
    'jiaowu', 'xuegong', 'tuanwei', 'yanjiusheng', 'gysj', 'gyyz', 'glxb',
    'support', 'service', 'contact', 'webadmin', 'sysadmin',
    'job', 'career', 'hr', 'recruit',
]

NAV_KEYWORDS = [
    '概况', '新闻', '通知', '公告', '招生', '联系我们', '首页', '返回', '更多',
    '书记信箱', '院长信箱', '师德师', '师资队', '现任教', '学院概', '管理架',
]

VALID_TITLES_RE = re.compile(
    r'(教授|副教授|助理教授|讲师|研究员|副研究员|助理研究员|'
    r'工程师|高级工程师|院士|博导|硕导|长江学者|杰青|优青|'
    r'院长|副院长|系主任|副主任|所长|副所长|博士后|'
    r'高级实验师|实验师|教授级高工|教授级高级工程师)'
)


def is_valid_email(email: str) -> bool:
    """严格验证邮箱，排除CSS/JS路径等误提取。"""
    if not email or not isinstance(email, str):
        return False
    email = email.strip().lower()
    if not email or '@' not in email:
        return False

    # 排除CSS/JS/图片等文件路径
    bad_extensions = r'\.(css|js|png|jpg|jpeg|gif|svg|ico|woff2?|ttf|eot|json|xml|zip|tar|gz|exe|dll|bin|map|txt)$'
    if re.search(bad_extensions, email, re.I):
        return False

    if re.search(r'(Research|Education|userAgent|text\.is|undefined|null|NaN|function|prototype)', email, re.I):
        return False

    # 标准邮箱格式验证
    m = re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._%+-]*@([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$', email)
    if not m:
        return False

    # 检查域名合理性
    domain = email.split('@')[1]
    if len(domain) < 6 or len(domain) > 60:
        return False
    # 域名不能全是数字
    if re.match(r'^\d+(\.\d+)*$', domain):
        return False

    return True


def is_public_email(email: str) -> bool:
    """检查是否为公共/行政邮箱。"""
    prefix = email.lower().split('@')[0]
    for p in PUBLIC_PREFIXES:
        if prefix == p or prefix.startswith(p):
            return True
    # 纯数字邮箱名
    if re.match(r'^\d{3,}', prefix):
        return True
    return False


def is_valid_teacher_name(name: str) -> bool:
    """验证是否为合法的教师姓名。"""
    name = name.strip()
    if not name:
        return False
    if any(kw in name for kw in NAV_KEYWORDS):
        return False
    if not re.match(r'^[一-鿿]{2,6}$', name):
        return False
    return True


def clean_existing_data(rows: list[dict]) -> list[dict]:
    """清理现有数据的垃圾邮箱和无效条目。"""
    cleaned = []
    removed_count = 0
    bad_email_count = 0

    for r in rows:
        name = r.get('姓名', '').strip()
        email = r.get('邮箱', '').strip()

        # 排除无效姓名
        if not is_valid_teacher_name(name):
            removed_count += 1
            continue

        # 验证/清理邮箱
        if email:
            if is_valid_email(email) and not is_public_email(email):
                pass  # 好邮箱
            else:
                r['邮箱'] = ''
                bad_email_count += 1

        cleaned.append(r)

    print(f"  清理: 移除 {removed_count} 个无效姓名, 清空 {bad_email_count} 个无效邮箱")
    return cleaned


def load_csv(path: Path) -> list[dict]:
    """加载 CSV 文件。"""
    if not path.exists():
        print(f"  文件不存在: {path}")
        return []
    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        return list(reader)


def merge_data(old_rows: list[dict], new_rows: list[dict]) -> list[dict]:
    """智能合并新旧数据。按 (姓名, 学院) 去重，保留信息最完整的版本。"""
    # 建立索引
    old_index = {}
    for i, r in enumerate(old_rows):
        key = (r.get('姓名', '').strip(), r.get('学院', '').strip())
        if key[0] and key[1]:
            old_index[key] = i

    new_index = {}
    for i, r in enumerate(new_rows):
        key = (r.get('姓名', '').strip(), r.get('学院', '').strip())
        if key[0] and key[1]:
            new_index[key] = i

    # 合并策略：
    # 1. 旧数据有邮箱 → 保留（除非新数据也有邮箱且不同，选新数据的邮箱）
    # 2. 旧数据无邮箱，新数据有邮箱 → 更新邮箱
    # 3. 新数据中的新教师 → 追加

    merged = list(old_rows)

    # 更新旧数据中的邮箱
    update_count = 0
    new_teacher_count = 0
    for key, ni in new_index.items():
        nr = new_rows[ni]
        new_email = nr.get('邮箱', '').strip()
        new_title = nr.get('职称', '').strip()

        if key in old_index:
            oi = old_index[key]
            or_ = merged[oi]
            old_email = or_.get('邮箱', '').strip()
            old_title = or_.get('职称', '').strip()

            # 新数据有邮箱且旧数据没有 → 更新
            if new_email and not old_email:
                or_['邮箱'] = new_email
                update_count += 1
            # 新数据有邮箱且旧数据也有，但旧邮箱无效 → 更新
            elif new_email and old_email and not is_valid_email(old_email):
                or_['邮箱'] = new_email
                update_count += 1
            # 补充职称
            if new_title and not old_title:
                or_['职称'] = new_title

        else:
            # 新教师，追加
            merged.append({
                '姓名': nr.get('姓名', ''),
                '邮箱': new_email,
                '学院': nr.get('学院', ''),
                '职称': new_title or nr.get('职称', ''),
                '主页链接': nr.get('主页链接', ''),
            })
            new_teacher_count += 1

    print(f"  合并: 更新 {update_count} 条邮箱, 新增 {new_teacher_count} 条教师")
    return merged


def print_stats(rows: list[dict], label: str = ""):
    """打印统计数据。"""
    total = len(rows)
    with_email = sum(1 for r in rows if r.get('邮箱', '').strip())
    with_title = sum(1 for r in rows if r.get('职称', '').strip())

    dept_stats = {}
    for r in rows:
        d = r.get('学院', '未知').strip()
        if d not in dept_stats:
            dept_stats[d] = {'total': 0, 'email': 0}
        dept_stats[d]['total'] += 1
        if r.get('邮箱', '').strip():
            dept_stats[d]['email'] += 1

    print(f"\n{'='*60}")
    print(f"  {label}" if label else "")
    print(f"  总计: {total} 条")
    print(f"  有邮箱: {with_email} ({100*with_email//total if total else 0}%)")
    print(f"  有职称: {with_title}")
    print(f"  院系数: {len(dept_stats)}")
    print(f"\n  {'学院':<24} {'总数':>5} {'邮箱':>5} {'%':>4}")
    print(f"  {'-'*40}")
    for d, s in sorted(dept_stats.items(), key=lambda x: -x[1]['total']):
        pct = 100 * s['email'] // s['total'] if s['total'] else 0
        flag = " ⚠️" if pct < 20 else ""
        print(f"  {d:<24} {s['total']:>5} {s['email']:>5} {pct:>3}%{flag}")


def main():
    print("=" * 60)
    print("  南京大学教师邮箱 — 最终合并清洗")
    print("=" * 60)

    # 1. 加载现有数据
    old_dir = OUTPUT_DIR / "nju_merged"
    old_files = list(old_dir.glob("南京大学_最终数据_*.csv"))
    if not old_files:
        # 回退到 outputs 根目录
        old_files = list(OUTPUT_DIR.glob("南京大学_最终数据_*.csv"))

    old_rows = []
    if old_files:
        old_path = sorted(old_files)[-1]
        print(f"\n📂 加载现有数据: {old_path.name}")
        old_rows = load_csv(old_path)
        print(f"   原始: {len(old_rows)} 条")
    else:
        print("⚠️ 未找到现有数据文件，仅使用增量爬取数据")

    # 2. 清理现有数据的垃圾
    print(f"\n🔍 清理现有数据...")
    old_cleaned = clean_existing_data(old_rows) if old_rows else []
    email_count = sum(1 for r in old_cleaned if r.get('邮箱', '').strip())
    print(f"   清理后: {len(old_cleaned)} 条, {email_count} 个有效邮箱")

    # 3. 加载增量爬取数据
    inc_files = sorted(OUTPUT_DIR.glob("南京大学_增量爬取_*.csv"))
    new_rows = []
    for f in inc_files:
        rows = load_csv(f)
        print(f"\n📂 增量数据: {f.name} → {len(rows)} 条")
        new_rows.extend(rows)

    # 去重增量数据自身
    seen = set()
    deduped_new = []
    for r in new_rows:
        key = (r.get('姓名', '').strip(), r.get('学院', '').strip())
        if key not in seen and key[0] and key[1]:
            seen.add(key)
            deduped_new.append(r)
    print(f"   增量去重后: {len(deduped_new)} 条")
    print_stats(deduped_new, "增量数据统计")

    # 4. 合并
    print(f"\n🔄 合并中...")
    all_rows = old_cleaned
    if deduped_new:
        all_rows = merge_data(old_cleaned, deduped_new)
    print_stats(all_rows, "合并后")

    # 5. 排序（按学院，然后按姓名）
    all_rows.sort(key=lambda r: (r.get('学院', ''), r.get('姓名', '')))

    # 6. 导出
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_dir = OUTPUT_DIR / f"nju_final_{ts}"
    export_dir.mkdir(parents=True, exist_ok=True)

    fieldnames = ['姓名', '邮箱', '学院', '职称', '主页链接']

    # 完整版 CSV
    full_csv = export_dir / f"南京大学_全部教师邮箱_V1.0.2.csv"
    with open(full_csv, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)
    print(f"\n✅ 完整版 CSV: {full_csv}")

    # 仅邮箱版 CSV
    with_email = [r for r in all_rows if r.get('邮箱', '').strip()]
    email_csv = export_dir / f"南京大学_仅邮箱教师_V1.0.2.csv"
    with open(email_csv, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(with_email)
    print(f"✅ 仅邮箱 CSV: {email_csv}")

    # 导出 XLSX
    xlsx_path = None
    email_xlsx_path = None
    try:
        sys.path.insert(0, str(BASE_DIR))
        from agent.exporter import export_xlsx
        task_dir_name = f"nju_final_{ts}"
        xlsx_path = export_xlsx(all_rows, f"南京大学_全部教师邮箱_V1.0.2", task_id=task_dir_name)
        print(f"✅ 完整版 XLSX: {xlsx_path}")

        if with_email:
            email_xlsx_path = export_xlsx(with_email, f"南京大学_仅邮箱教师_V1.0.2", task_id=task_dir_name)
            print(f"✅ 仅邮箱 XLSX: {email_xlsx_path}")
    except Exception as e:
        print(f"⚠️ XLSX 导出失败: {e}")

    # 打印摘要
    print(f"\n{'='*60}")
    print(f"  最终结果摘要")
    print(f"{'='*60}")
    total = len(all_rows)
    email_total = len(with_email)
    pct = 100 * email_total // total if total else 0
    print(f"  教师总数: {total}")
    print(f"  有邮箱教师: {email_total} ({pct}%)")
    print(f"  无邮箱教师: {total - email_total}")
    print(f"  院系数: {len({r.get('学院','') for r in all_rows})}")
    print(f"\n  输出目录: {export_dir}/")

    # 学院统计
    print(f"\n  各学院邮箱覆盖率:")
    dept_stats = {}
    for r in all_rows:
        d = r.get('学院', '未知').strip()
        if d not in dept_stats:
            dept_stats[d] = {'total': 0, 'email': 0}
        dept_stats[d]['total'] += 1
        if r.get('邮箱', '').strip():
            dept_stats[d]['email'] += 1
    for d, s in sorted(dept_stats.items(), key=lambda x: -x[1]['total']):
        ep = s['email']
        tp = s['total']
        p = 100 * ep // tp if tp else 0
        flag = " ⚠️ 严重不足" if p < 20 else ""
        print(f"  {d:<24}: {tp:>4}人, {ep:>4}邮箱 ({p}%){flag}")

    # 生成文件声明
    print(f"\n📋 文件声明:")
    print("[FILES]")
    print(f"{full_csv.name} | CSV 表格（南京大学全部教师邮箱，含有效和无效邮箱）")
    if xlsx_path:
        print(f"{Path(xlsx_path).name} | Excel 表格（含样式表头）")
    if email_csv:
        print(f"{email_csv.name} | CSV 表格（仅有效邮箱教师）")
    if email_xlsx_path:
        print(f"{email_xlsx_path.name} | Excel 表格（仅有效邮箱教师，含样式表头）")
    print("[/FILES]")


if __name__ == '__main__':
    main()
