"""Normalize college names and finalize NJU data."""
import csv, os, re
from collections import Counter, defaultdict

src = r"D:\Work\test\UniEmailAgent\backend\outputs\南京大学_教师邮箱_最终版.csv"
out = r"D:\Work\test\UniEmailAgent\backend\outputs\南京大学_教师邮箱_最终版.csv"

# Load
with open(src, encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

# College name normalization mapping
# Fragmented names -> unified name
NORMALIZE_MAP = {
    "文学院(现任教师)": "文学院",
    "文学院": "文学院",
    "商学院(经济学院)": "商学院",
    "商学院": "商学院",
    "法学院(在职教师)": "法学院",
    "法学院": "法学院",
    "海外教育学院(语言教师)": "海外教育学院",
    "海外教育学院": "海外教育学院",
    "马克思主义学院(教授)": "马克思主义学院",
    "马克思主义学院(副教授)": "马克思主义学院",
    "马克思主义学院": "马克思主义学院",
    "地理与海洋科学学院": "地理与海洋科学学院",
    "地理与海洋(海岸海洋科学系)": "地理与海洋科学学院",
    "地理与海洋(自然地理学系)": "地理与海洋科学学院",
    "地理与海洋(地理信息科学系)": "地理与海洋科学学院",
    "地理与海洋(国土旅游学系)": "地理与海洋科学学院",
    "环境学院(环境科学系)": "环境学院",
    "环境学院(环境工程系)": "环境学院",
    "环境学院": "环境学院",
    "电子科学与工程学院": "电子科学与工程学院",
    "电子科学与工程(电子工程系)": "电子科学与工程学院",
    "电子科学与工程(通信工程系)": "电子科学与工程学院",
    "电子科学与工程(信息电子学系)": "电子科学与工程学院",
    "计算机学院": "计算机科学与技术系",
    "南京赫尔辛基大气学院": "南京赫尔辛基大气与地球系统科学学院",
    "南京赫尔辛基大气与地球系统科学学院": "南京赫尔辛基大气与地球系统科学学院",
    "大学外语部": "大学外语部",
    "教育研究院·陶行知教师教育学院": "教育研究院",
    "教育研究院": "教育研究院",
    "化学化工学院": "化学化工学院",
    "化学学院": "化学化工学院",
}

# Apply normalization
applied = defaultdict(list)
for r in rows:
    old = r["学院"]
    new = NORMALIZE_MAP.get(old, old)
    if old != new:
        applied[old].append(new)
    r["学院"] = new

# Report merges
for old, targets in sorted(applied.items()):
    print(f"  {old} -> {targets[0]} ({len(targets)} records)")

# Renumber
for i, r in enumerate(rows, 1):
    r["序号"] = str(i)

# Stats
we = sum(1 for r in rows if r.get("邮箱","").strip())
colleges = Counter(r["学院"] for r in rows)

print(f"\n{'='*60}")
print(f"FINAL: {len(rows)} people, {we} emails ({we*100//len(rows)}%), {len(colleges)} colleges")
print(f"{'='*60}")

# Write
headers = ["序号", "姓名", "邮箱", "学院", "职称", "主页链接"]
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=headers)
    w.writeheader()
    w.writerows(rows)

print(f"\nWritten: {out} ({os.path.getsize(out)//1024}KB)")

# College breakdown
print(f"\n{'College':30s} {'People':>5s} {'Emails':>5s} {'Rate':>5s}")
print("-"*50)
for c, n in sorted(colleges.items(), key=lambda x:-x[1]):
    e = sum(1 for r in rows if r["学院"]==c and r["邮箱"])
    bar = "#"*(e*20//n) if n else ""
    print(f"{c:30s} | {n:>4d} | {e:>4d} | {e*100//n:>3d}%")
