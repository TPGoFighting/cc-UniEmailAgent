#!/usr/bin/env python3
"""分析东南大学已有数据的质量"""
import csv
from collections import defaultdict
import re

with open(r'D:\Work\test\UniEmailAgent\backend\outputs\seu_all\东南大学_全部教师_20260601_165009.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

total = len(rows)
has_email = sum(1 for r in rows if r.get('邮箱', '').strip())
no_email = total - has_email
url_pattern = re.compile(r'^https?://')
hp_url = sum(1 for r in rows if url_pattern.match(r.get('主页链接', '').strip()))

print(f'总教师数: {total}')
print(f'有邮箱: {has_email} ({has_email/total*100:.1f}%)')
print(f'无邮箱: {no_email} ({no_email/total*100:.1f}%)')
print(f'主页链接是URL格式: {hp_url}')
print()

college_stats = defaultdict(lambda: {'total': 0, 'with_email': 0, 'with_url': 0})
for r in rows:
    c = r.get('学院', '').strip()
    if not c:
        c = '(未标注学院)'
    college_stats[c]['total'] += 1
    if r.get('邮箱', '').strip():
        college_stats[c]['with_email'] += 1
    if r.get('主页链接', '').strip():
        college_stats[c]['with_url'] += 1

print('=== 各学院数据概况 ===')
for c, s in sorted(college_stats.items(), key=lambda x: x[1]['total']):
    email_rate = s['with_email']/s['total']*100 if s['total'] > 0 else 0
    flag = ' ⚠️' if (s['total'] < 50 or email_rate < 80) else ''
    print(f'  {c}: {s["total"]}人, 邮箱{s["with_email"]}/{s["total"]} ({email_rate:.0f}%){flag}')

print()
print('=== 需补充爬取的学院（<50人或邮箱率<80%）===')
targets = []
for c, s in sorted(college_stats.items(), key=lambda x: x[1]['total']):
    email_rate = s['with_email']/s['total']*100 if s['total'] > 0 else 0
    issues = []
    if s['total'] < 50:
        issues.append(f'仅{s["total"]}人')
    if email_rate < 80:
        issues.append(f'邮箱率{email_rate:.0f}%')
    if issues:
        print(f'  {c}: {s["total"]}人, {" | ".join(issues)}')
        targets.append(c)

print(f'\n共 {len(targets)} 个学院需要补充爬取')
