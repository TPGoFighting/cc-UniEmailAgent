"""
南大最终数据合并、清洗与导出
合并来源：
  1. 原始数据 (nju_final/南京大学_全部教师邮箱_V1.0.0.csv) - 5679教师
  2. 第一次补充 (nju_email_deep/南大_新邮箱_20260601_221727.csv) - 238个邮箱
  3. 第二次补充 (nju_email_deep/南大_补充邮箱_20260601_223407.csv) - 903个邮箱
"""
import csv, os, re, sys
from datetime import datetime
from collections import defaultdict

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")

# 读取原始数据
original_path = os.path.join(BASE_DIR, "nju_final", "南京大学_全部教师邮箱_V1.0.0.csv")
records = []
with open(original_path, encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        records.append({
            "name": row.get("姓名", "").strip(),
            "email": row.get("邮箱", "").strip(),
            "department": row.get("学院", "").strip(),
            "title": row.get("职称", "").strip(),
            "url": row.get("主页链接", "").strip()
        })

print(f"原始数据: {len(records)} 条, 原始有邮箱: {sum(1 for r in records if r['email'])}")

# 读取第一次补充（新邮箱CSV）
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
new_emails = {}  # name -> email

supplement1 = os.path.join(BASE_DIR, "nju_email_deep", "南京大学_邮箱补充_20260601_221727.csv")
if os.path.exists(supplement1):
    with open(supplement1, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = row.get("姓名", "").strip()
            email = row.get("邮箱", "").strip()
            if name and email and EMAIL_RE.match(email):
                new_emails[name] = email

print(f"第一次补充: {len(new_emails)} 个邮箱")

# 读取第二次补充
supplement2 = os.path.join(BASE_DIR, "nju_email_deep", "南大_补充邮箱_20260601_223407.csv")
if os.path.exists(supplement2):
    with open(supplement2, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = row.get("姓名", "").strip()
            email = row.get("邮箱", "").strip()
            if name and email and EMAIL_RE.match(email):
                new_emails[name] = email

print(f"第二次补充: {sum(1 for _ in open(supplement2, encoding='utf-8-sig')) - 1} 个邮箱")

print(f"合并补充邮箱: {len(new_emails)} 个唯一邮箱")

# 垃圾邮箱过滤关键字
GARBAGE_PREFIXES = ['webmaster', 'admin', 'office', 'info', 'master', 'root',
    'postmaster', 'bgs', 'dangzheng', 'yuanban', 'wxyxz', 'xwcb', 'd', 'navig',
    'epicker', '.md-calendar', '.mint']
GARBAGE_DOMAINS = ['epicker.css', 'e.min.css', 'or-text.is', 'est.min.js',
    'nju.ed', 'nju.edu', '163.com', 'sina.com', '126.com', 'qq.com']

def is_valid_email(email):
    if not email or not EMAIL_RE.match(email):
        return False
    prefix = email.split('@')[0].lower()
    domain = email.split('@')[1].lower()
    # 排除垃圾
    if any(p in prefix for p in GARBAGE_PREFIXES):
        return False
    if any(d == domain for d in GARBAGE_DOMAINS):
        return False
    # 邮箱必须有 nju.edu.cn
    if 'nju.edu.cn' not in domain:
        return False
    return True

# 合并邮箱
updated = 0
for rec in records:
    name = rec["name"]
    if name in new_emails:
        new_email = new_emails[name]
        if is_valid_email(new_email):
            if not rec["email"] or not is_valid_email(rec["email"]):
                rec["email"] = new_email
                updated += 1

total_with_email = sum(1 for r in records if is_valid_email(r['email']))
print(f"\n补充了 {updated} 个新邮箱")
print(f"最终有邮箱: {total_with_email}")

# 统计
from collections import Counter
dept_stats = Counter()
dept_email = Counter()
for r in records:
    dept_stats[r['department']] += 1
    if is_valid_email(r['email']):
        dept_email[r['department']] += 1

print(f"\n{'='*55}")
print(f"📊 各学院最终邮箱统计")
print(f"{'='*55}")
print(f"{'学院':<26} {'教师':<6} {'有邮箱':<6} {'覆盖率':<8}")
print('-' * 45)
for dept in sorted(dept_stats.keys(), key=lambda d: -dept_stats[d]):
    t = dept_stats[dept]
    e = dept_email[dept]
    pct = e/t*100 if t > 0 else 0
    bar = '█' * int(pct/5) + '░' * (20 - int(pct/5))
    print(f'{dept:<24} {t:<5} {e:<5} {pct:>5.1f}%  {bar}')

print('-' * 45)
total_t = sum(dept_stats.values())
total_e = sum(dept_email.values())
print(f'总计: {total_t} 教师, {total_e} 有邮箱 ({total_e/total_t*100:.1f}%)')

# 保存CSV
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
out_dir = os.path.join(BASE_DIR, "nju_merged")
os.makedirs(out_dir, exist_ok=True)

csv_path = os.path.join(out_dir, f"南京大学_最终数据_{ts}.csv")
with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(["姓名", "邮箱", "学院", "职称", "主页链接"])
    for r in records:
        w.writerow([r["name"], r["email"], r["department"], r["title"], r["url"]])
print(f"\nCSV: {csv_path}")

# 筛选有邮箱的记录
email_csv = os.path.join(out_dir, f"南京大学_有邮箱_{ts}.csv")
with open(email_csv, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(["姓名", "邮箱", "学院", "职称"])
    for r in records:
        if is_valid_email(r['email']):
            w.writerow([r["name"], r["email"], r["department"], r["title"]])
print(f"有邮箱CSV: {email_csv} ({sum(1 for r in records if is_valid_email(r['email']))} 条)")
