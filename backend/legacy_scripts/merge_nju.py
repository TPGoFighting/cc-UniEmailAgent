"""Properly merge NJU V1.0.0 + supplement data."""
import csv
from collections import Counter
from pathlib import Path

out_dir = Path(r"D:\Work\test\UniEmailAgent\backend\outputs\d73dcbad-a0ca-4034-9c67-d4e6c0966cbf")

# Load V1.0.0 (original best data)
with open(out_dir / "南京大学_全校教师邮箱_V1.0.0.csv", encoding="utf-8-sig") as f:
    v100 = list(csv.DictReader(f))

# Load supplement data
with open(out_dir / "南京大学_增量补充_V1.0.0.csv", encoding="utf-8-sig") as f:
    sup = list(csv.DictReader(f))

# Also load newer supplement files
sup2_path = out_dir / "南京大学_增量补充_20260603_170743.csv"
if sup2_path.exists():
    with open(sup2_path, encoding="utf-8-sig") as f:
        sup2 = list(csv.DictReader(f))
        sup.extend(sup2)

sup3_path = out_dir / "南京大学_增量补充_20260603_171148.csv"
if sup3_path.exists():
    with open(sup3_path, encoding="utf-8-sig") as f:
        sup3 = list(csv.DictReader(f))
        sup.extend(sup3)

# Build index of existing emails from V1.0.0
existing_emails = set()
for r in v100:
    e = r.get("邮箱", "").strip()
    if e:
        existing_emails.add(e)

# Also index name+dept combos
existing_name_dept = set()
for r in v100:
    name = r.get("姓名", "").strip()
    dept = r.get("学院", "").strip()
    if name:
        existing_name_dept.add((name, dept))

print(f"V1.0.0 base: {len(v100)} people, {len(existing_emails)} emails, {len(existing_name_dept)} name+dept combos")
print(f"Supplement raw: {len(sup)} records")

# Filter supplement: only add records that are genuinely new
added = 0
skipped_existing_email = 0
skipped_existing_name = 0
for r in sup:
    name = r.get("姓名", "").strip()
    email = r.get("邮箱", "").strip()
    dept = r.get("学院", "").strip()

    # Skip if email already exists in V1.0.0
    if email and email in existing_emails:
        skipped_existing_email += 1
        continue

    # Skip if same name+dept already exists (avoid duplicates without email)
    if name and (name, dept) in existing_name_dept:
        skipped_existing_name += 1
        continue

    # Add this new record
    v100.append({
        "序号": r.get("序号", ""),
        "姓名": name,
        "邮箱": email,
        "学院": dept,
        "职称": r.get("职称", ""),
        "主页链接": r.get("主页链接", ""),
    })
    existing_name_dept.add((name, dept))
    if email:
        existing_emails.add(email)
    added += 1

# Renumber
for i, r in enumerate(v100, 1):
    r["序号"] = str(i)

# Stats
we = sum(1 for r in v100 if r.get("邮箱","").strip())
colleges = Counter(r.get("学院","") for r in v100)

print(f"\nSkipped (email dup): {skipped_existing_email}")
print(f"Skipped (name+dept dup): {skipped_existing_name}")
print(f"Added new: {added}")
print(f"\nFinal: {len(v100)} people, {we} emails ({we*100//len(v100)}%), {len(colleges)} colleges")

# Write V2.0.1 (correctly merged)
headers = ["序号", "姓名", "邮箱", "学院", "职称", "主页链接"]
with open(out_dir / "南京大学_全校教师邮箱_V2.0.1.csv", "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    for r in v100:
        writer.writerow({h: r.get(h, "") for h in headers})

print(f"\nWritten: 南京大学_全校教师邮箱_V2.0.1.csv")

# College breakdown
print(f"\n{'College':25s} | {'People':>5s} | {'Emails':>5s} | {'Rate':>5s}")
print("-"*45)
for c, n in sorted(colleges.items(), key=lambda x:-x[1]):
    e = sum(1 for r in v100 if r.get("学院","")==c and r.get("邮箱","").strip())
    print(f"{c:25s} | {n:>5d} | {e:>5d} | {e*100//n:>3d}%")
