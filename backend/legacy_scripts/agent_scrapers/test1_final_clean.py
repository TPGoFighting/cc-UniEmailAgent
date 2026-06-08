"""最终清洗 — 移除明显非教师条目，标记有效数据"""
import csv
import re
from pathlib import Path

IN_PATH = Path(__file__).resolve().parent.parent / "outputs" / "a6be504a-8ff0-4b89-9d62-8752953ed8e9" / "南京大学_教师邮箱_clean.csv"
OUT_PATH = Path(__file__).resolve().parent.parent / "outputs" / "a6be504a-8ff0-4b89-9d62-8752953ed8e9" / "南京大学_教师邮箱_final.csv"

# 明确不是人名的姓名
BAD_NAMES_STRICT = {
    "我所开发出250", "群众团体", "院行政", "英语系",
}

with open(IN_PATH, encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

final = []
for r in rows:
    name = r.get("姓名", "").strip()
    email = r.get("邮箱", "").strip()

    # 移除明确的非人名
    if name in BAD_NAMES_STRICT:
        continue

    # 无邮箱标记
    if not email:
        r["邮箱"] = "无邮箱"

    final.append(r)

# 统计
total = len(final)
has_email = sum(1 for r in final if r["邮箱"] != "无邮箱")
unknown = sum(1 for r in final if r["姓名"] == "未知")

print(f"最终数据: {total} 条")
print(f"有邮箱: {has_email} 条")
print(f"未知姓名: {unknown} 条")

# 按学院统计
from collections import Counter
dept_count = Counter(r["学院"] for r in final)
print(f"\n学院分布:")
for dept, cnt in dept_count.most_common():
    with_email = sum(1 for r in final if r["学院"] == dept and r["邮箱"] != "无邮箱")
    print(f"  {dept}: {cnt}人, 有邮箱{with_email}人")

# 保存
with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=["姓名", "邮箱", "学院", "职称", "主页链接"])
    writer.writeheader()
    writer.writerows(final)

print(f"\n💾 已保存: {OUT_PATH}")
