"""
从V2爬虫日志中提取结果并合并所有数据，生成最终版CSV
"""
import csv
import re
import os
from collections import defaultdict

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")

def parse_v2_log():
    """从V2脚本的日志中提取教师邮箱"""
    log_path = os.path.expanduser("C:/Users/17356/AppData/Local/Temp/claude/D--work-test-UniEmailAgent-backend/834fb1e4-7e65-4909-bb43-e29dfd1bc323/tasks/b0kfunzem.output")

    results = []
    current_college = ""

    # 正则匹配：✓ [序号] 姓名 → 邮箱
    result_pattern = re.compile(r'✓ \[\d+(?:/\d+)?\] (.+?) → (.+?)$')
    college_pattern = re.compile(r'爬取: (.+)$')

    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            college_match = college_pattern.search(line)
            if college_match:
                # 只在出现 "爬取:" 且不在 "完成:" 行时更新
                if '完成:' not in line:
                    current_college = college_match.group(1).strip()

            result_match = result_pattern.search(line)
            if result_match and current_college:
                name = result_match.group(1).strip()
                email = result_match.group(2).strip()

                # 排除明显不是人名的
                if len(name) > 5 or len(name) < 2:
                    continue
                if not re.search(r'[一-鿿]', name):
                    continue

                results.append({
                    "姓名": name,
                    "邮箱": email,
                    "学院": current_college,
                    "职称": "",
                    "主页链接": "",
                })

    return results


def load_existing_csv(path):
    """加载CSV文件"""
    rows = []
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)
    except:
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)
    return rows


def main():
    print("=" * 60)
    print("合并所有数据生成最终CSV")
    print("=" * 60)

    # 1. 加载原始CSV (基准数据)
    base_path = os.path.join(OUTPUT_DIR, "南京大学_教师邮箱_最终版_20260526_212956.csv")
    base_rows = load_existing_csv(base_path)
    print(f"原始数据: {len(base_rows)} 条")

    # 2. 解析V2日志
    v2_results = parse_v2_log()
    print(f"V2日志提取: {len(v2_results)} 条")

    # 按学院统计V2
    v2_colleges = defaultdict(int)
    for r in v2_results:
        v2_colleges[r["学院"]] += 1
    for c, n in sorted(v2_colleges.items()):
        print(f"  V2 - {c}: {n} 人")

    # 3. 加载V1结果
    v1_path = os.path.join(OUTPUT_DIR, "南京大学_低人数学院定向_20260526_215851.csv")
    v1_results = load_existing_csv(v1_path)
    v1_filtered = []
    for r in v1_results:
        email = r.get("邮箱", "").strip()
        if email:
            v1_filtered.append(r)
    print(f"V1结果(有邮箱): {len(v1_filtered)} 条")

    # 4. 合并策略：以姓名+学院为key去重
    # 优先级: V2 > V1 > 原始（保留原始中非低人数学院的数据）
    LOW_COLLEGES = [
        "电子科学与工程学院", "地球科学与工程学院", "化学化工学院",
        "现代工程与应用科学学院", "生命科学学院", "商学院",
        "文学院", "历史学院", "中美文化研究中心",
    ]

    # 建立 key → row 的映射
    final = {}

    # 先加载原始数据中非低人数学院的数据
    for r in base_rows:
        college = r.get("学院", "")
        email = r.get("邮箱", "").strip()
        name = r.get("姓名", "")
        key = f"{name}|{college}"

        if college not in LOW_COLLEGES:
            if email:  # 只保留有邮箱的
                final[key] = r

    # 然后覆盖低人数学院中原始有邮箱的数据
    for r in base_rows:
        college = r.get("学院", "")
        email = r.get("邮箱", "").strip()
        name = r.get("姓名", "")
        key = f"{name}|{college}"

        if college in LOW_COLLEGES and email:
            final[key] = r

    print(f"\n原始有效数据: {len(final)} 条")

    # 用V1数据覆盖（V1有更准确的邮箱）
    v1_added = 0
    for r in v1_filtered:
        key = f"{r['姓名']}|{r['学院']}"
        if key not in final or final[key].get("邮箱", "") != r["邮箱"]:
            final[key] = r
            v1_added += 1
    print(f"V1覆盖/新增: {v1_added} 条")

    # 用V2数据覆盖（V2有最准确的邮箱）
    v2_added = 0
    for r in v2_results:
        key = f"{r['姓名']}|{r['学院']}"
        final[key] = r
        v2_added += 1
    print(f"V2覆盖: {v2_added} 条")

    # 统计最终结果
    college_counts = defaultdict(int)
    college_emails = defaultdict(int)
    for r in final.values():
        college = r.get("学院", "")
        college_counts[college] += 1
        if r.get("邮箱", "").strip():
            college_emails[college] += 1

    print(f"\n=== 最终结果 ===")
    print(f"总记录: {len(final)} 条")
    print(f"有邮箱: {sum(1 for r in final.values() if r.get('邮箱', '').strip())} 条")

    # 按学院输出
    print(f"\n按学院分布:")
    for college in sorted(college_counts.keys(), key=lambda c: college_counts[c], reverse=True):
        c = college_counts[college]
        e = college_emails[college]
        mark = " ⚠" if e < 10 else ""
        print(f"  {college}: {c} 人 (有邮箱: {e}){mark}")

    # 保存
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(OUTPUT_DIR, f"南京大学_教师邮箱_合并终版_{timestamp}.csv")

    fieldnames = ["姓名", "邮箱", "学院", "职称", "主页链接"]
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in final.values():
            row = {k: r.get(k, "") for k in fieldnames}
            writer.writerow(row)

    print(f"\n已保存: {csv_path}")


if __name__ == "__main__":
    main()
