#!/usr/bin/env python3
"""
南航数据最终处理 - 清洗 + 多格式导出
"""
import csv, os, sys, re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent import cleaner, exporter

TASK_ID = "055e6cac-682b-49be-8614-100434a8c27c"
OUTPUT_DIR = f"D:/Work/test/UniEmailAgent/backend/outputs/{TASK_ID}"

# 读取 v4 CSV
v4_csv = os.path.join(OUTPUT_DIR, "南京航空航天大学_教师邮箱_20260601_201500.csv")
with open(v4_csv, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    raw_reader_records = list(reader)

print(f"📂 原始数据: {len(raw_reader_records)} 条")

# 将 CSV 字段映射到 cleaner 期望的字段名
raw_records = []
for r in raw_reader_records:
    raw_records.append({
        'name': r.get('姓名', ''),
        'email': r.get('邮箱', ''),
        'department': r.get('学院', ''),
        'title': r.get('职称', ''),
        'url': r.get('主页链接', ''),
    })

print(f"📂 原始数据: {len(raw_records)} 条")

# 清洗
cleaned = cleaner.clean_records(raw_records)
print(f"🧹 清洗后: {len(cleaned)} 条")

# 统计邮箱
with_email = sum(1 for r in cleaned if r.get('email') and r['email'] not in ['', '无邮箱'])
print(f"📧 有邮箱: {with_email} 人")

# 按学院统计
dept_stats = {}
for r in cleaned:
    d = r.get('department', '未知') or '未知'
    if d not in dept_stats:
        dept_stats[d] = {'total': 0, 'with_email': 0}
    dept_stats[d]['total'] += 1
    if r.get('email') and r['email'] not in ['', '无邮箱']:
        dept_stats[d]['with_email'] += 1

print(f"\n📋 各学院:")
for d, s in sorted(dept_stats.items(), key=lambda x: -x[1]['total']):
    print(f"  {d}: {s['total']}人 (有邮箱: {s['with_email']}人)")

# 导出清洗后 CSV
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
clean_csv = os.path.join(OUTPUT_DIR, f"南京航空航天大学_教师邮箱_清洗_{timestamp}.csv")
with open(clean_csv, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(['姓名', '邮箱', '学院', '职称', '主页链接'])
    for r in cleaned:
        writer.writerow([
            r.get('name', ''),
            r.get('email', '') or '无邮箱',
            r.get('department', ''),
            r.get('title', '') or '未知',
            r.get('homepage', '') or r.get('url', ''),
        ])
print(f"\n✅ 清洗CSV: {clean_csv}")

# 多格式导出
print(f"\n📦 多格式导出...")
# 将清洗数据转换为 exporter 格式
header_map = {'姓名': 'name', '邮箱': 'email', '学院': 'department', '职称': 'title', '主页链接': 'homepage'}
records_for_export = []
for r in cleaned:
    records_for_export.append({
        'name': r.get('name', ''),
        'email': r.get('email', '') or '无邮箱',
        'department': r.get('department', ''),
        'title': r.get('title', '') or '未知',
        'homepage': r.get('homepage', '') or r.get('url', ''),
    })

for ext in ['xlsx', 'md', 'html', 'pdf', 'docx']:
    try:
        out = exporter.get_task_dir(TASK_ID) / f"南京航空航天大学_教师邮箱.{ext}"
        # 使用 exporter 的适当方法
        if ext == 'xlsx':
            exporter.export_xlsx(records_for_export, str(out))
        elif ext == 'md':
            exporter.export_markdown(records_for_export, str(out))
        elif ext == 'html':
            exporter.export_html(records_for_export, str(out))
        elif ext == 'pdf':
            exporter.export_pdf(records_for_export, str(out))
        elif ext == 'docx':
            exporter.export_docx(records_for_export, str(out))
        print(f"  ✅ {ext.upper()} 导出成功")
    except Exception as e:
        print(f"  ❌ {ext.upper()} 导出失败: {e}")

print(f"\n📂 所有文件在: {OUTPUT_DIR}/")
