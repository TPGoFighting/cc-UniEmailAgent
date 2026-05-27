"""最终数据合并脚本。

合并来源:
1. v3 全量爬取输出 (南京大学_教师名录_20260526_160441.csv)
2. v3 进度文件中剩余的数据 (如果有)
3. 修复零产量院系输出

统一清洗后输出最终版。
"""

import csv
import json
import logging
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "outputs"

# 复用姓氏验证
_COMMON_SURNAMES = set("""
赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张
孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎
鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤
滕殷罗毕郝邬安常乐于时傅皮下齐康伍余元卜顾孟平黄
和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞
熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭
梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯咎管卢莫
经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚
程嵇邢滑裴陆荣翁荀羊於惠甄麴家封芮羿储靳汲邴糜松
井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫
宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄
印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴鬱胥能苍双
闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍卻璩桑桂濮牛寿通
边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容
向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东
欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空
曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逮盍益桓公
""".replace("\n", ""))
_COMMON_SURNAMES.update([
    "欧阳", "太史", "端木", "上官", "司马", "东方", "独孤", "南宫",
    "万俟", "闻人", "夏侯", "诸葛", "尉迟", "公羊", "赫连", "澹台",
    "皇甫", "宗政", "濮阳", "公冶", "太叔", "申屠", "公孙", "慕容",
    "仲孙", "钟离", "长孙", "宇文", "司徒", "鲜于", "司空", "闾丘",
])

_NOT_PERSON_NAMES = {
    "文艺学", "汉语言", "语言学", "比较文", "中国古", "中国现", "戏剧与",
    "师德师", "师资队", "现任教",
    "文艺", "文学", "汉语", "中文", "外语", "新闻", "传播", "广告",
    "哲学", "宗教", "历史", "考古", "社会", "人类", "经济", "金融",
    "数学", "物理", "化学", "生物", "天文", "地理", "大气", "海洋",
    "地球", "地质", "环境", "生态", "建筑", "规划", "园林", "景观",
    "计算", "软硬", "信息", "通信", "电子", "自动", "材料", "能源",
    "力学", "工程", "航空", "航天", "土木", "水利", "交通", "化工",
    "国际", "公共", "行政", "工商", "会计", "市场", "人力", "物流",
    "法学", "政治", "行政", "图书", "档案", "教育", "心理", "体育",
    "音乐", "美术", "设计", "戏剧", "电影", "舞蹈", "医学", "药学",
    "护理", "口腔", "基础", "临床", "预防", "生命", "基因",
    "学院", "学系", "研究", "方向", "专业", "学位",
    "办公", "财务", "教务", "学工", "团委", "党委",
    "综合", "保障", "后勤", "保卫", "基建",
    "技术", "安全", "服务", "开发", "运营", "维护",
    "协调", "创新", "支撑",
}

NON_PERSONAL_EMAIL_PREFIXES = [
    'webmaster', 'admin', 'info@', 'contact@', 'postmaster',
    'mailto@', 'abuse@', 'no-reply', 'noreply', 'support@',
    'office@', 'service@', 'hr@', 'jobs@', 'master@',
    'bgs@', 'dangzheng@', 'yuanban@', 'xxgk@', 'fax@',
]


def load_csv(filepath: Path) -> list[dict]:
    """加载 CSV 文件为字典列表。"""
    records = []
    if not filepath.exists():
        return records
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append({
                "name": row.get("姓名", "").strip(),
                "email": row.get("邮箱", "").strip(),
                "department": row.get("学院", "").strip(),
                "title": row.get("职称", "").strip(),
                "url": row.get("主页链接", "").strip(),
            })
    return records


def load_progress(filepath: Path) -> list[dict]:
    """加载进度 JSON 文件。"""
    if not filepath.exists():
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("all_results", [])


def merge_dedup(all_records: list[dict]) -> list[dict]:
    """按 (姓名, 院系) 去重合并。"""
    groups: dict[tuple, list[dict]] = {}
    for r in all_records:
        key = (r.get("name", "").strip(), r.get("department", "").strip())
        if not key[0] or not key[1]:
            continue
        groups.setdefault(key, []).append(r)

    merged = []
    for key, entries in groups.items():
        best = entries[0]
        best_score = (1 if best.get("email") else 0) + (1 if best.get("title") else 0) + (0.5 if best.get("url") else 0)
        for entry in entries[1:]:
            score = (1 if entry.get("email") else 0) + (1 if entry.get("title") else 0) + (0.5 if entry.get("url") else 0)
            if score > best_score:
                best = entry
                best_score = score
        merged.append(best)

    return merged


def clean(records: list[dict]) -> list[dict]:
    """全流程清洗。"""
    # 1. 姓名验证
    valid = []
    for r in records:
        name = r.get("name", "").strip()
        if not name or name in _NOT_PERSON_NAMES:
            continue
        if re.fullmatch(r"[一-鿿]{2,4}", name):
            valid.append(r)
        else:
            logger.debug(f"  移除无效姓名: [{r.get('department','')}] \"{name}\"")
    logger.info(f"姓名验证: {len(records)} → {len(valid)}")

    # 2. 邮箱域名修复
    for r in valid:
        email = r.get("email", "").lower().strip()
        if email:
            email = re.sub(r'@nju\.ed$', '@nju.edu.cn', email)
            email = re.sub(r'@nju\.edu$', '@nju.edu.cn', email)
            r["email"] = email

    # 3. 非个人邮箱过滤
    filtered = 0
    for r in valid:
        email = r.get("email", "")
        if email:
            for prefix in NON_PERSONAL_EMAIL_PREFIXES:
                if email.lower().startswith(prefix):
                    r["email"] = ""
                    filtered += 1
                    break
    logger.info(f"非个人邮箱过滤: {filtered}")

    # 4. 批量邮箱检测 — 只检测非教育邮箱
    # 中国高校常见一个院系共用一个公开邮箱，这是正常的，不应清除
    # 只清除同一非教育邮箱（如 163.com/gmail.com）出现 >=10 次的情况
    dept_email_count: dict[str, dict[str, int]] = {}
    for r in valid:
        dept = r.get("department", "未知")
        email = r.get("email", "").lower()
        if not email:
            continue
        dept_email_count.setdefault(dept, {})
        dept_email_count[dept][email] = dept_email_count[dept].get(email, 0) + 1

    bulk_cleared = 0
    for dept, counts in dept_email_count.items():
        for email, cnt in counts.items():
            # 只检测非教育邮箱且出现>=10次的
            is_edu = any(email.endswith(d) for d in ['.edu.cn', '.edu', '.edu.hk', '.edu.tw', '.ac.cn', '.ac.uk'])
            if not is_edu and cnt >= 10:
                logger.info(f"  非教育邮箱批量清除 [{dept}]: {email} x{cnt}")
                for r in valid:
                    if r.get("department") == dept and r.get("email", "").lower() == email:
                        r["email"] = ""
                        bulk_cleared += 1
    logger.info(f"批量邮箱清除 (仅非教育邮箱): {bulk_cleared}")

    # 5. 最终格式验证
    for r in valid:
        email = r.get("email", "")
        if email and not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            r["email"] = ""

    return valid


def export(records: list[dict]):
    """导出最终文件。"""
    from agent.exporter import export_csv, export_xlsx

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 按院系+姓名排序
    records.sort(key=lambda r: (r.get("department", ""), r.get("name", "")))

    # 完整版
    full_csv = export_csv(records, f"南京大学_教师名录_最终版")
    full_xlsx = export_xlsx(records, f"南京大学_教师名录_最终版")

    # 仅邮箱
    with_email = [r for r in records if r.get("email")]
    if with_email:
        export_csv(with_email, f"南京大学_教师名录_最终版_有邮箱")
        export_xlsx(with_email, f"南京大学_教师名录_最终版_有邮箱")

    return len(records), len(with_email)


def print_stats(records: list[dict], label: str):
    """打印统计信息。"""
    total = len(records)
    with_email = sum(1 for r in records if r.get("email"))
    with_title = sum(1 for r in records if r.get("title"))

    dept_counts = {}
    dept_with_email = {}
    for r in records:
        d = r.get("department", "未知")
        dept_counts[d] = dept_counts.get(d, 0) + 1
        if r.get("email"):
            dept_with_email[d] = dept_with_email.get(d, 0) + 1

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  总人数: {total}")
    print(f"  有邮箱: {with_email} ({100*with_email/total:.1f}%)" if total else "  有邮箱: 0")
    print(f"  有职称: {with_title} ({100*with_title/total:.1f}%)" if total else "  有职称: 0")
    print(f"  院系数: {len(dept_counts)}")
    print(f"\n  {'院系':<18} {'总数':>5} {'有邮箱':>5} {'覆盖率':>6}")
    print(f"  {'-'*38}")
    for dept, count in sorted(dept_counts.items()):
        email_count = dept_with_email.get(dept, 0)
        rate = f"{100*email_count/count:.0f}%" if count else "-"
        print(f"  {dept:<18} {count:>5} {email_count:>5} {rate:>6}")

    domains = Counter()
    for r in records:
        email = r.get("email", "")
        if email and "@" in email:
            domains[email.split("@")[1].lower()] += 1
    if domains:
        print(f"\n  邮箱域名分布:")
        for domain, count in domains.most_common(10):
            print(f"    {domain}: {count}")


def main():
    print("=" * 60)
    print("  南京大学教师邮箱 — 最终合并清洗")
    print("=" * 60)

    all_records = []

    # 来源 1: v3 输出 CSV
    v3_csvs = sorted(OUTPUT_DIR.glob("南京大学_教师名录_20260526_16044*.csv"))
    for f in v3_csvs:
        records = load_csv(f)
        logger.info(f"来源 v3-CSV ({f.name}): {len(records)} 条")
        all_records.extend(records)

    # 来源 2: v2 第一轮进度文件（如果还有）
    v2_progress = OUTPUT_DIR / "nju_scrape_progress.json"
    if v2_progress.exists():
        records = load_progress(v2_progress)
        logger.info(f"来源 v2-进度: {len(records)} 条")
        all_records.extend(records)

    # 来源 3: v2 第二轮进度文件
    r2_progress = OUTPUT_DIR / "nju_scrape_round2_progress.json"
    if r2_progress.exists():
        records = load_progress(r2_progress)
        logger.info(f"来源 v2-round2: {len(records)} 条")
        all_records.extend(records)

    # 来源 4: 修复零产量院系进度文件
    fix_progress = OUTPUT_DIR / "nju_fix_zero_progress.json"
    if fix_progress.exists():
        records = load_progress(fix_progress)
        logger.info(f"来源 fix-zero: {len(records)} 条")
        all_records.extend(records)

    # 来源 5: 修复输出 XLSX/CSV
    for f in sorted(OUTPUT_DIR.glob("南京大学_教师名录_补抓_fix*.xlsx")):
        # XLSX is harder to read directly, skip for now
        pass

    logger.info(f"总计加载: {len(all_records)} 条")

    if not all_records:
        logger.error("没有数据!")
        return

    # 去重
    merged = merge_dedup(all_records)
    print_stats(merged, "合并去重后")

    # 清洗
    cleaned = clean(merged)
    print_stats(cleaned, "清洗后")

    # 导出
    total, with_email = export(cleaned)
    print(f"\n✅ 最终输出: {total} 人 ({with_email} 有邮箱)")


if __name__ == "__main__":
    main()
