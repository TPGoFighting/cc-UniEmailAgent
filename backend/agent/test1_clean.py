"""清洗测试1的爬取数据 — 移除导航文本姓名、公共邮箱等"""
import csv
import re
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent.parent / "outputs" / "a6be504a-8ff0-4b89-9d62-8752953ed8e9" / "南京大学_教师邮箱_raw.csv"
OUT_PATH = Path(__file__).resolve().parent.parent / "outputs" / "a6be504a-8ff0-4b89-9d62-8752953ed8e9" / "南京大学_教师邮箱_clean.csv"

# 非人名的姓名模式
NOT_PERSON_NAMES = {
    "", "导航", "首页", "返回", "更多", "查看", "党委", "行政", "教师", "教授",
    "副教授", "讲师", "组织机构", "组织架构", "机构设置", "师资队伍", "师资",
    "诚聘英才", "报名方式", "双学位", "硕士生导师", "博士生导师", "党群工作",
    "学工园地", "学院介绍", "按专业", "最新更新", "医学伦理分委会",
    "师德师风监督举报邮箱", "院长信箱", "捐赠", "英语系",
    "教授", "副教授", "讲师", "助理教授", "研究员", "副研究员",
}

# 公共邮箱特征
PUBLIC_PATTERNS = [
    r"^english@", r"^history@", r"^arch@", r"^ssbs@", r"^rcb@",
    r"^hydw@", r"^yingfeng@", r"^njugcglxy@", r"^irb@",
    r"^webmaster@", r"^admin@", r"^office@", r"^info@", r"^master@",
    r"^root@", r"^postmaster@", r"^wxyxz@", r"^sxydw@",
]

def is_public_email(email: str) -> bool:
    if not email:
        return False
    email_lower = email.lower()
    for pat in PUBLIC_PATTERNS:
        if re.match(pat, email_lower):
            return True
    # 检查是否形如 xx@xxx 但没有中文姓名匹配（公共邮箱常见）
    return False

def is_valid_person_name(name: str) -> bool:
    if not name or name in NOT_PERSON_NAMES:
        return False
    # 必须是中文姓名（2-4字）开头
    m = re.match(r"^([一-鿿]{2,4})", name.strip())
    if not m:
        return False
    # 排除明显的非姓名
    bad_chars = "报组室部处委会局办系院所馆站网栏目页版"
    if name.strip()[-1] in bad_chars:
        return False
    return True

# 读取
with open(CSV_PATH, encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print(f"原始数据: {len(rows)} 条")

# 清洗
cleaned = []
for r in rows:
    name = r.get("姓名", "").strip()
    email = r.get("邮箱", "").strip()

    # 1. 过滤公共邮箱
    if email and is_public_email(email):
        r["邮箱"] = ""  # 清空公共邮箱
        email = ""

    # 2. 处理姓名
    if not is_valid_person_name(name):
        # 尝试从URL提取姓名
        url = r.get("主页链接", "")
        url_name = ""
        if url:
            parts = url.rstrip("/").split("/")
            for p in reversed(parts):
                p = p.replace(".htm", "").replace(".html", "").replace(".jsp", "")
                if re.match(r"^[一-鿿]{2,4}$", p):
                    url_name = p
                    break
        if url_name and is_valid_person_name(url_name):
            r["姓名"] = url_name
        elif email and not is_public_email(email):
            # 有邮箱但无法识别姓名 → 标记为"未知"
            r["姓名"] = "未知"
        else:
            # 既没有有效姓名也没有邮箱 → 跳过
            continue

    # 3. 保留
    cleaned.append(r)

print(f"清洗后: {len(cleaned)} 条")
print(f"有邮箱: {sum(1 for r in cleaned if r['邮箱'])} 条")
print(f"有姓名但无邮箱: {sum(1 for r in cleaned if not r['邮箱'])} 条")

# 保存
with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=["姓名", "邮箱", "学院", "职称", "主页链接"])
    writer.writeheader()
    writer.writerows(cleaned)

print(f"\n💾 已保存: {OUT_PATH}")

# 按学院统计
from collections import Counter
dept_count = Counter(r["学院"] for r in cleaned)
for dept, cnt in dept_count.most_common():
    with_email = sum(1 for r in cleaned if r["学院"] == dept and r["邮箱"])
    print(f"  {dept}: {cnt}人, 有邮箱{with_email}人")
