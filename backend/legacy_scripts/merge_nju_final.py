"""Merge all NJU data - light cleaning, no domain whitelist."""
import csv, os, sys
from collections import defaultdict, Counter

sys.path.insert(0, r"D:\Work\test\UniEmailAgent\backend")

out_dir = r"D:\Work\test\UniEmailAgent\backend\outputs\d73dcbad-a0ca-4034-9c67-d4e6c0966cbf"

# Load V1.0.0 base
with open(os.path.join(out_dir, "南京大学_全校教师邮箱_V1.0.0.csv"), encoding="utf-8-sig") as f:
    base_raw = list(csv.DictReader(f))

# Map to English keys
def map_record(r):
    return {
        "name": r.get("姓名", "").strip() or r.get("name", "").strip(),
        "email": r.get("邮箱", "").strip().lower() or r.get("email", "").strip().lower(),
        "department": r.get("学院", "").strip() or r.get("department", "").strip(),
        "title": r.get("职称", "").strip() or r.get("title", "").strip(),
        "url": r.get("主页链接", "").strip() or r.get("url", "").strip(),
    }

base = [map_record(r) for r in base_raw]
base_emails = {r["email"] for r in base if r["email"]}
base_name_dept = {(r["name"], r["department"]) for r in base if r["name"]}
print(f"Base V1.0.0: {len(base)} records, {len(base_emails)} emails")

# Load legacy V1.0.5 (has 1668/870, better than V1.0.0's 1441/813)
legacy_path = r"D:\Work\test\UniEmailAgent\backend\outputs\_legacy\nju_final_20260603_131944\南京大学_全部教师邮箱_V1.0.5.csv"
if os.path.exists(legacy_path):
    with open(legacy_path, encoding="utf-8-sig") as f:
        legacy_raw = list(csv.DictReader(f))
    legacy = []
    for r in legacy_raw:
        m = map_record(r)
        if m["name"] and m["email"] and m["email"] not in base_emails:
            legacy.append(m)
            base_emails.add(m["email"])
            if (m["name"], m["department"]) not in base_name_dept:
                base_name_dept.add((m["name"], m["department"]))
    print(f"Added from legacy V1.0.5: {len(legacy)} new records")
    base.extend(legacy)

# Load supplement files
sup_files = [
    "南京大学_增量补充_V1.0.0.csv",
    "南京大学_增量补充_20260603_171148.csv",
    "南京大学_增量补充_20260603_170743.csv",
]
faf_dir = r"D:\Work\test\UniEmailAgent\backend\outputs\faf34c69-7934-450c-ad2b-7120706fc8c6"
sup_added = 0
for sf in sup_files:
    sp = os.path.join(out_dir, sf)
    if os.path.exists(sp):
        with open(sp, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                base.append(map_record(r))

if os.path.exists(faf_dir):
    for f in os.listdir(faf_dir):
        if f.endswith(".csv") and "南京大学" in f:
            with open(os.path.join(faf_dir, f), encoding="utf-8-sig") as fh:
                for r in csv.DictReader(fh):
                    base.append(map_record(r))

print(f"After merge (before cleaning): {len(base)} records")

# --- Light cleaning (no domain whitelist) ---

# Filter 1: must have a valid name (2-4 Chinese chars or minority name)
import re
def is_valid_name(name):
    if not name:
        return False
    if re.match(r"^[\u4e00-\u9fff]{2,4}$", name):
        return True
    if re.match(r"^[\u4e00-\u9fff·]{2,6}$", name) and "·" in name:
        return True
    return False

before = len(base)
base = [r for r in base if is_valid_name(r["name"])]
print(f"After name filter: {len(base)} (removed {before-len(base)})")

# Filter 2: valid email format (or empty)
def valid_email(e):
    if not e:
        return True
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", e))

before = len(base)
base = [r for r in base if valid_email(r["email"])]
print(f"After email format: {len(base)} (removed {before-len(base)})")

# Filter 3: exclude admin emails
admin_prefixes = ["webmaster", "admin", "office", "info", "master", "root",
                  "postmaster", "wxyxz", "xwcb", "bgs", "dangzheng", "yuanban"]
def is_admin(e):
    if not e:
        return False
    local = e.split("@")[0].lower()
    return local in admin_prefixes or any(local.startswith(p) for p in admin_prefixes)

before = len(base)
base = [r for r in base if not is_admin(r["email"])]
print(f"After admin filter: {len(base)} (removed {before-len(base)})")

# Filter 4: nav list URL with no email -> skip
def is_nav_url(url):
    if not url:
        return False
    low = url.lower()
    nav_patterns = ["/list.htm", "/index.htm", "/index.html", "/main.htm", "javascript:", "#"]
    for p in nav_patterns:
        if p in low:
            return True
    return False

before = len(base)
base = [r for r in base if r["email"] or not is_nav_url(r["url"])]
print(f"After nav URL filter: {len(base)} (removed {before-len(base)})")

# Filter 5: dedup by email (keep most complete)
deduped = []
seen_emails = set()
no_email = []
for r in base:
    if r["email"]:
        if r["email"] not in seen_emails:
            seen_emails.add(r["email"])
            deduped.append(r)
    else:
        no_email.append(r)
# Dedup no-email by name+dept
seen_nd = set()
for r in no_email:
    k = (r["name"], r["department"])
    if k not in seen_nd:
        seen_nd.add(k)
        deduped.append(r)
base = deduped

we = sum(1 for r in base if r["email"])
print(f"After dedup: {len(base)} records, {we} emails")

# Output
output = []
for i, r in enumerate(base, 1):
    output.append({
        "序号": str(i),
        "姓名": r["name"],
        "邮箱": r["email"],
        "学院": r["department"],
        "职称": r["title"],
        "主页链接": r["url"],
    })

out_path = r"D:\Work\test\UniEmailAgent\backend\outputs\南京大学_教师邮箱_最终版.csv"
headers = ["序号", "姓名", "邮箱", "学院", "职称", "主页链接"]
with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=headers)
    w.writeheader()
    w.writerows(output)

print(f"\n{'='*60}")
print(f"FINAL: {len(output)} people, {we} emails ({we*100//len(output)}%)")
print(f"{'='*60}")
print(f"\nWritten to: {out_path} ({os.path.getsize(out_path)//1024}KB)")

# College breakdown
colleges = Counter(r["学院"] for r in output)
print(f"\n{'College':32s} {'People':>5s} {'Emails':>5s} {'Rate':>5s}")
print("-"*52)
for c, n in sorted(colleges.items(), key=lambda x:-x[1]):
    e = sum(1 for r in output if r["学院"]==c and r["邮箱"])
    print(f"{c:32s} | {n:>4d} | {e:>4d} | {e*100//n:>3d}%")
