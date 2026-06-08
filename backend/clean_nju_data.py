import csv
import re

INPUT = r'D:\Work\test\UniEmailAgent\backend\outputs\d73dcbad-a0ca-4034-9c67-d4e6c0966cbf\南京大学_全校教师邮箱_V1.0.1.csv'
OUTPUT = r'D:\Work\test\UniEmailAgent\backend\outputs\d73dcbad-a0ca-4034-9c67-d4e6c0966cbf\南京大学_全校教师邮箱_V1.1.0.csv'

FAKE_NAMES = {
    '软件研发', '集成电路', '智能经济', '前沿科学', '医学院', '研究院',
    '学院概况', '学生工作', '规章制度', '科学研究', '师资队伍',
    '联系方式', 'XYZX', 'EMSE', '学院简介', '人才培养',
    '学术研究', '校友之窗', '办事指南', '全程培养',
    '国际合作', '科研项目', '学术活动',
    '本科生', '研究生', '留学生', '继续教育',
    '党建', '首页', '更多', '链接', '专题', '系统',
    '学报', '图书馆', '档案馆', '大型仪器', '博士后',
    '长江学者', '杰出青年', '优秀青年', '创新团队',
    '校外访问', '教师主页', '教师登录',
    # 从首页误抓的假阳性
    '前沿青年', '卓越工程', '寻古园廉', '山河同游', '树立践行',
    '环境与健', '走进前沿', '智汇紫金', '学术之秋', '南雍山下',
    '南雍', '机器人', '自动化', '生物医学', '数字经济',
    '学术型', '专业型', '研究生导师', '国际交流',
    '教工之家', '学习园地', '相关链接', '院内办公',
    '金钟课题', '问渠那得', '上海药物', '四季匠心',
}

ACADEMIC_TITLES = {
    '教授', '副教授', '助理教授', '讲师',
    '研究员', '副研究员', '助理研究员',
    '工程师', '高级工程师', '实验师', '高级实验师',
    '院士', '博导', '硕导',
    '长江学者', '杰青', '优青',
    '博士后',
    '准聘副教授', '准聘助理教授', '长聘教授', '长聘副教授',
    '助理教授', '助理研究员',
}

rows = []
with open(INPUT, encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for r in reader:
        rows.append(r)

print(f'加载: {len(rows)} 条')

filtered = []
fake_found = []
for r in rows:
    name = r['姓名'].strip()
    if name in FAKE_NAMES:
        fake_found.append(name)
        continue
    if not re.match(r'^[一-鿿\·]{2,4}$', name):
        fake_found.append(name)
        continue
    filtered.append(r)

print(f'过滤假阳性: {len(fake_found)} 个')
print(f'剩余: {len(filtered)} 条')

for r in filtered:
    if r['职称']:
        titles = [t.strip() for t in r['职称'].split('、') if t.strip() in ACADEMIC_TITLES]
        seen = set()
        unique_titles = []
        for t in titles:
            if t not in seen:
                seen.add(t)
                unique_titles.append(t)
        r['职称'] = '、'.join(unique_titles)

seen = set()
deduped = []
for r in filtered:
    key = (r['姓名'], r['学院'])
    if key not in seen:
        seen.add(key)
        deduped.append(r)

by_dept = {}
for r in deduped:
    dept = r['学院']
    if dept not in by_dept:
        by_dept[dept] = {}
    name = r['姓名']
    if name not in by_dept[dept]:
        by_dept[dept][name] = r
    else:
        existing = by_dept[dept][name]
        if not existing['邮箱'] and r['邮箱']:
            by_dept[dept][name] = r

final = []
for dept in sorted(by_dept.keys()):
    for name in sorted(by_dept[dept].keys()):
        final.append(by_dept[dept][name])

with_email = sum(1 for r in final if r['邮箱'])
no_email = sum(1 for r in final if not r['邮箱'])
print(f'\n清洗后: {len(final)} 条 (含邮箱 {with_email}, 无邮箱 {no_email})')

with open(OUTPUT, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['序号', '姓名', '邮箱', '学院', '职称', '主页链接'])
    w.writeheader()
    for i, r in enumerate(final, 1):
        w.writerow({
            '序号': i, '姓名': r['姓名'], '邮箱': r['邮箱'],
            '学院': r['学院'], '职称': r['职称'], '主页链接': r['主页链接'],
        })

print(f'\n输出: {OUTPUT}')
print('\n学院统计:')
stats = {}
for r in final:
    d = r['学院']
    if d not in stats:
        stats[d] = {'t': 0, 'e': 0}
    stats[d]['t'] += 1
    if r['邮箱']:
        stats[d]['e'] += 1
for d, s in sorted(stats.items()):
    pct = s['e'] / s['t'] * 100 if s['t'] > 0 else 0
    print(f'  {d:25s}: {s["t"]:4d} 条, {s["e"]:4d} 邮箱 ({pct:5.1f}%)')

print(f'\n总计: {len(final)} 条, {with_email} 邮箱')
