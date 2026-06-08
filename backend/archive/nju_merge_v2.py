"""南京大学数据合并与清洗脚本。

将补充爬取的新数据与现有数据合并、去重、清洗，生成最终文件。
"""

import csv, json, re, sys, os, shutil
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"
TASK_OUTPUT_DIR = OUTPUT_DIR / "nju_final_20260603_131944"  # 已有数据的目录

PUBLIC_EMAIL_PREFIXES = {
    "webmaster", "admin", "office", "info", "master", "root", "postmaster",
    "wxyxz", "xwcb", "bgs", "dangzheng", "yuanban", "dangban", "renshi",
    "jiaowu", "xuegong", "tuanwei", "yanjiusheng", "gysj", "gyyz", "glxb",
}

NAV_BLACKLIST = {
    "首页", "网站", "概况", "简介", "领导", "部门", "制度", "招聘", "通知", "公告",
    "新闻", "动态", "科研", "党建", "团建", "学生", "招生", "就业", "合作", "联系",
    "关于", "下载", "办事", "指南", "登录", "注册", "加入", "返回", "更多", "查看",
    "详情", "关闭", "确定", "取消", "中文", "英文",
    "博士后", "教研室", "实验室", "研究所", "中心",
    "科学研究", "学术", "交流", "国际", "版权所有", "友情链接",
    "人才培养", "科学研究", "社会服务", "文化传承", "国际合作",
    "校友", "基金会", "图书馆", "学报", "出版社", "医院", "附属",
    "书记信箱", "院长信箱", "联系我们", "师资队伍", "教师名录",
    "教授", "副教授", "讲师", "博士", "硕士", "本科", "教育",
    "校内", "链接", "网站地图", "管理", "教师", "师资", "队伍",
    "现任", "兼职", "客座", "讲座", "访问", "研究", "行政",
    "全部", "教授", "副教授", "讲师", "博导", "硕导", "院士",
    "长江学者", "杰青", "优青", "青年", "拔尖", "创新", "团队",
}

LEGAL_TITLES = {
    "教授", "副教授", "助理教授", "讲师", "研究员", "副研究员",
    "助理研究员", "工程师", "高级工程师", "院士", "博导", "硕导",
    "长江学者", "杰青", "优青", "院长", "副院长", "系主任",
    "副主任", "所长", "副所长", "博士后", "高级实验师", "实验师",
    "青年学者", "特聘教授", "讲座教授", "兼职教授", "客座教授",
}

# 学院名称标准化映射
DEPT_NAME_MAP = {
    "哲学系": "哲学学院",
    "哲学学院": "哲学学院",
    "化学化工学院": "化学化工学院",
    "化学学院": "化学化工学院",
    "化工学院": "化学化工学院",
    "计算机科学与技术系": "计算机学院",
    "计算机学院": "计算机学院",
    "计算机系": "计算机学院",
    "大学外语部": "大学外语部",
    "体育部": "体育部",
    "建筑与城市规划学院": "建筑与城市规划学院",
    "建筑学院": "建筑与城市规划学院",
    "政府管理学院": "政府管理学院",
    "文学院": "文学院",
    "外国语学院": "外国语学院",
    "新闻传播学院": "新闻传播学院",
    "海外教育学院": "海外教育学院",
    "人工智能学院": "人工智能学院",
    "医学院": "医学院",
    "大气科学学院": "大气科学学院",
    "地理与海洋科学学院": "地理与海洋科学学院",
    "软件学院": "软件学院",
    "智能软件与工程学院": "智能软件与工程学院",
    "教育研究院": "教育研究院·陶行知教师教育学院",
    "教育研究院·陶行知教师教育学院": "教育研究院·陶行知教师教育学院",
    "社会学院": "社会学院",
    "集成电路学院": "集成电路学院",
    "艺术学院": "艺术学院",
    "生物医学工程学院": "生物医学工程学院",
    "工程管理学院": "工程管理学院",
    "马克思主义学院": "马克思主义学院",
    "南京赫尔辛基大气与地球系统科学学院": "南京赫尔辛基大气与地球系统科学学院",
    "南赫学院": "南京赫尔辛基大气与地球系统科学学院",
    "能源与资源学院": "能源与资源学院",
    "环境学院": "环境学院",
    "信息管理学院": "信息管理学院",
    "地球科学与工程学院": "地球科学与工程学院",
    "法学院": "法学院",
    "化学化工学院": "化学化工学院",
    "历史学院": "历史学院",
    "匡亚明学院": "匡亚明学院",
    "现代工程与应用科学学院": "现代工程与应用科学学院",
    "电子科学与工程学院": "电子科学与工程学院",
    "智能科学与技术学院": "智能科学与技术学院",
    "国际关系学院": "国际关系学院",
    "数字经济与管理学院": "数字经济与管理学院",
    "机器人与自动化学院": "机器人与自动化学院",
    "数学学院": "数学学院",
    "数学系": "数学学院",
    "物理学院": "物理学院",
    "天文与空间科学学院": "天文与空间科学学院",
    "商学院": "商学院",
    "前沿科学学院": "前沿科学学院",
    "计算机学院": "计算机学院",
    "智能科学与技术学院": "智能科学与技术学院",
}


def load_csv(filepath):
    """加载CSV文件。"""
    rows = []
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({
                    "name": row.get("姓名", "").strip(),
                    "email": row.get("邮箱", "").strip(),
                    "department": row.get("学院", "").strip(),
                    "title": row.get("职称", "").strip(),
                    "url": row.get("主页链接", "").strip(),
                })
    except Exception as e:
        print(f"  加载失败 {filepath}: {e}")
    return rows


def standardize_dept(name):
    """标准化学院名称。"""
    if name in DEPT_NAME_MAP:
        return DEPT_NAME_MAP[name]
    return name


def is_valid_name(name):
    """验证姓名是否合理。"""
    if not name:
        return False
    if len(name) < 2 or len(name) > 6:
        return False
    if name in NAV_BLACKLIST:
        return False
    # 必须是中文名（或含·的少数民族名）
    if not re.match(r"^[一-鿿·]{2,6}$", name):
        return False
    # 排除导航词
    for kw in NAV_BLACKLIST:
        if kw in name:
            return False
    return True


def is_valid_email(email):
    """验证邮箱格式并排除公共邮箱。"""
    if not email:
        return False
    email = email.lower().strip()
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        return False
    prefix = email.split("@")[0]
    if prefix.lower() in PUBLIC_EMAIL_PREFIXES:
        return False
    return True


def clean_title(title):
    """从被污染的职称字段中提取合法职称。"""
    if not title:
        return ""
    for kw in ["教授", "副教授", "助理教授", "讲师", "研究员", "副研究员",
               "助理研究员", "工程师", "高级工程师", "院士", "博士后",
               "高级实验师", "实验师"]:
        if kw in title:
            return kw
    return title[:30] if len(title) < 30 else ""


def merge_and_clean(old_rows, new_rows):
    """合并旧数据和新数据，去重、清洗。"""
    combined = old_rows + new_rows

    # 标准化学院名称
    for row in combined:
        row["department"] = standardize_dept(row["department"])
        row["email"] = row["email"].lower().strip()
        row["name"] = row["name"].strip()
        row["title"] = clean_title(row["title"])

    # Step 1: 按邮箱+姓名去重（保留信息最完整的记录）
    seen = {}
    for row in combined:
        key = (row["name"], row["email"], row["department"])
        if key not in seen:
            seen[key] = row
        else:
            # 保留信息更完整的记录（优先选有邮箱的）
            existing = seen[key]
            if row["email"] and not existing["email"]:
                seen[key] = row
            elif row["title"] and not existing["title"]:
                seen[key] = row

    # Step 2: 过滤无效数据
    valid = []
    for row in seen.values():
        if not is_valid_name(row["name"]):
            continue
        if not is_valid_email(row["email"]):
            row["email"] = ""  # 无效邮箱置空而非删除记录
        valid.append(row)

    # Step 3: 按学院分组 + 姓名排序
    dept_groups = defaultdict(list)
    for row in valid:
        dept_groups[row["department"]].append(row)

    result = []
    for dept in sorted(dept_groups.keys()):
        group = sorted(dept_groups[dept], key=lambda r: r["name"])
        result.extend(group)

    return result


def export_all(data, output_dir, base_name="南京大学_全部教师邮箱"):
    """导出 CSV 和 XLSX。"""
    # CSV
    csv_path = output_dir / f"{base_name}_V2.0.0.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["序号", "姓名", "邮箱", "学院", "职称", "主页链接"])
        for i, row in enumerate(data, 1):
            writer.writerow([i, row["name"], row["email"], row["department"], row["title"], row["url"]])
    print(f"CSV 已保存: {csv_path} ({len(data)} 条)")

    # XLSX
    try:
        sys.path.insert(0, str(BASE_DIR))
        from agent.exporter import export_xlsx
        xlsx_path = export_xlsx(data, f"{base_name}_V2.0.0")
        # 复制到输出目录
        dest = output_dir / xlsx_path.name
        shutil.copy2(xlsx_path, dest)
        print(f"XLSX 已保存: {dest}")
    except Exception as e:
        print(f"XLSX 导出失败: {e}")

    return csv_path


def print_stats(data, label="统计"):
    """打印各学院的统计信息。"""
    dept_stats = defaultdict(lambda: {"total": 0, "email": 0})
    for r in data:
        d = r["department"]
        dept_stats[d]["total"] += 1
        if r["email"]:
            dept_stats[d]["email"] += 1

    print(f"\n{'='*60}")
    print(f"📊 {label}")
    print(f"总记录: {len(data)}, 有邮箱: {sum(1 for r in data if r['email'])}")
    print(f"{'学院':<32} {'总人数':>6} {'有邮箱':>6} {'邮箱率':>8}")
    print("-"*55)
    for d, s in sorted(dept_stats.items(), key=lambda x: -x[1]["total"]):
        rate = s["email"]/s["total"]*100 if s["total"]>0 else 0
        flag = " ⚠️" if rate < 30 else ""
        print(f"{d:<32} {s['total']:>6} {s['email']:>6} {rate:>7.1f}%{flag}")
    print("="*60)


def main():
    # 1. 加载现有数据
    old_file = TASK_OUTPUT_DIR / "南京大学_全部教师邮箱_V1.0.5.csv"
    print(f"加载现有数据: {old_file}")
    old_data = load_csv(old_file)
    print(f"现有数据: {len(old_data)} 条")

    # 2. 加载补充爬取的数据（查找最新）
    supp_dirs = sorted(Path(OUTPUT_DIR).glob("nju_supplement_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    supp_data = []
    for d in supp_dirs:
        for f in d.glob("南京大学_补充爬取*.csv"):
            print(f"加载补充数据: {f}")
            supp_data.extend(load_csv(f))

    # 也检查是否有之前批次的进度文件
    for f in Path(OUTPUT_DIR).glob("*补充爬取*.csv"):
        if f not in [d / f.name for d in supp_dirs]:
            print(f"加载补充数据: {f}")
            supp_data.extend(load_csv(f))

    # 也检查 task outputs
    for f in Path(OUTPUT_DIR).glob("nju_supplement_*/南京大学_补充爬取*.csv"):
        print(f"加载补充数据: {f}")
        supp_data.extend(load_csv(f))

    print(f"补充数据: {len(supp_data)} 条")

    # 3. 合并清洗
    all_data = merge_and_clean(old_data, supp_data)
    print(f"\n合并后: {len(all_data)} 条 (去重后)")

    # 4. 统计
    print_stats(all_data, "南京大学全部教师邮箱 (V2.0.0)")

    # 5. 统计补充爬取带来的新增
    old_names = {(r["name"], r["email"], r["department"]) for r in old_data}
    new_records = [r for r in all_data if (r["name"], r["email"], r["department"]) not in old_names]
    print(f"\n新增记录: {len(new_records)}")

    if new_records:
        print_stats(new_records, "新增记录统计")

    # 6. 导出
    out_dir = OUTPUT_DIR / "nju_final_v2"
    out_dir.mkdir(parents=True, exist_ok=True)

    export_all(all_data, out_dir)

    # 7. 删除旧文件目录
    old_dir = OUTPUT_DIR / "nju_final_20260603_131944"
    if old_dir.exists():
        import shutil
        shutil.rmtree(old_dir)
        print(f"\n已删除旧目录: {old_dir}")

    # 也删除所有旧补充爬取目录
    for d in sorted(OUTPUT_DIR.glob("nju_supplement_*")):
        if d.is_dir():
            import shutil
            shutil.rmtree(d)
            print(f"已删除临时目录: {d}")

    # 8. 列出 [FILES]
    print(f"\n[FILES]")
    for f in out_dir.glob("*"):
        if f.suffix in (".csv", ".xlsx"):
            desc = "CSV 表格" if f.suffix == ".csv" else "Excel 表格（含样式表头）"
            print(f"{f.name} | 南京大学全部教师邮箱 {desc}")
    print("[/FILES]")

    return all_data


if __name__ == "__main__":
    main()
