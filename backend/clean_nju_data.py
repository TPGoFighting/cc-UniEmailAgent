"""南京大学教师邮箱数据 — 合并清洗脚本。

功能:
1. 合并多轮爬取数据（v2 第一轮 + v2 第二轮 + v3 全量）
2. 智能去重（同部门同姓名，保留有邮箱的版本）
3. 邮箱域名修复（nju.ed → nju.edu.cn）
4. 非个人邮箱过滤
5. 批量/公用邮箱检测
6. 姓名验证
7. 输出完整版 + 仅邮箱版 CSV/XLSX
"""

import json
import logging
import re
from collections import Counter
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "outputs"

# 复用 v3 的姓氏表
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


def is_valid_chinese_name(text: str) -> bool:
    text = text.strip()
    if not text or text in _NOT_PERSON_NAMES:
        return False
    m = re.fullmatch(r"([一-鿿]{1,2})([一-鿿]{1,2})", text)
    if m:
        return m.group(1) in _COMMON_SURNAMES
    m = re.fullmatch(r"([一-鿿]{2,4})\s*(教授|副教授|讲师|助理教授|研究员|副研究员|院士|博导|硕导)", text)
    if m:
        return m.group(1)[0] in _COMMON_SURNAMES
    return False


def fix_email_domain(email: str) -> str:
    """修复常见的邮箱域名错误。"""
    email = email.lower().strip()
    # nju.ed → nju.edu.cn (OCR/解析错误)
    email = re.sub(r'@nju\.ed$', '@nju.edu.cn', email)
    # nju.edu → nju.edu.cn (截断)
    email = re.sub(r'@nju\.edu$', '@nju.edu.cn', email)
    # 去掉邮箱前后的特殊字符
    email = re.sub(r'^[^a-zA-Z0-9]+', '', email)
    email = re.sub(r'[^a-zA-Z0-9.]+$', '', email)
    return email


def is_non_personal_email(email: str) -> bool:
    """检测是否为非个人邮箱（公用邮箱、部门邮箱等）。"""
    email_lower = email.lower()
    for prefix in NON_PERSONAL_EMAIL_PREFIXES:
        if email_lower.startswith(prefix):
            return True
    # 检测纯数字开头的（通常是公用号）
    if re.match(r'^\d{2,}', email_lower.split('@')[0] if '@' in email_lower else ''):
        return True
    return False


def load_all_sources() -> list[dict]:
    """加载所有来源的数据。"""
    all_records = []

    # 来源1: v2 第一轮进度文件
    v1_progress = OUTPUT_DIR / "nju_scrape_progress.json"
    if v1_progress.exists():
        with open(v1_progress, "r", encoding="utf-8") as f:
            data = json.load(f)
        records = data.get("all_results", [])
        logger.info(f"来源1 (v2第一轮): {len(records)} 条")
        all_records.extend(records)

    # 来源2: v2 第二轮进度文件
    r2_progress = OUTPUT_DIR / "nju_scrape_round2_progress.json"
    if r2_progress.exists():
        with open(r2_progress, "r", encoding="utf-8") as f:
            data = json.load(f)
        records = data.get("all_results", [])
        logger.info(f"来源2 (v2第二轮): {len(records)} 条")
        all_records.extend(records)

    # 来源3: v3 全量爬取进度文件
    v3_progress = OUTPUT_DIR / "nju_scrape_v3_progress.json"
    if v3_progress.exists():
        with open(v3_progress, "r", encoding="utf-8") as f:
            data = json.load(f)
        records = data.get("all_results", [])
        logger.info(f"来源3 (v3全量): {len(records)} 条")
        all_records.extend(records)

    logger.info(f"总计加载: {len(all_records)} 条")
    return all_records


def merge_and_deduplicate(records: list[dict]) -> list[dict]:
    """按 (姓名, 院系) 去重，保留信息最完整的那条。"""
    groups: dict[tuple, list[dict]] = {}
    for r in records:
        key = (r.get("name", "").strip(), r.get("department", "").strip())
        if not key[0] or not key[1]:
            continue
        groups.setdefault(key, []).append(r)

    merged = []
    for key, entries in groups.items():
        # 选择规则：优先保留有邮箱的，然后保留有职称的，然后保留有 URL 的
        best = entries[0]
        best_score = (1 if best.get("email") else 0) + (1 if best.get("title") else 0) + (0.5 if best.get("url") else 0)

        for entry in entries[1:]:
            score = (1 if entry.get("email") else 0) + (1 if entry.get("title") else 0) + (0.5 if entry.get("url") else 0)
            if score > best_score:
                best = entry
                best_score = score

        merged.append(best)

    logger.info(f"去重: {len(records)} → {len(merged)} 条 (合并了 {len(records) - len(merged)} 条重复)")
    return merged


def clean(records: list[dict]) -> list[dict]:
    """执行全部清洗步骤。"""

    # Step 1: 姓名验证
    valid = []
    removed_names = []
    for r in records:
        name = r.get("name", "").strip()
        if not name:
            removed_names.append(("空名", r))
            continue
        if name in _NOT_PERSON_NAMES:
            removed_names.append((name, r))
            continue
        if is_valid_chinese_name(name):
            valid.append(r)
        elif re.fullmatch(r"[一-鿿]{2,4}", name):
            # 宽松处理非姓氏但纯中文 2-4 字
            valid.append(r)
        else:
            removed_names.append((name, r))
    logger.info(f"姓名验证: 保留 {len(valid)}, 移除 {len(removed_names)}")
    if removed_names:
        for name, r in removed_names[:10]:
            logger.debug(f"  移除: [{r.get('department','')}] \"{name}\"")

    # Step 2: 邮箱域名修复 + 格式验证
    for r in valid:
        email = r.get("email", "")
        if email:
            r["email"] = fix_email_domain(email)

    # Step 3: 非个人邮箱过滤
    filtered_count = 0
    for r in valid:
        email = r.get("email", "")
        if email and is_non_personal_email(email):
            logger.debug(f"  非个人邮箱: [{r.get('department','')}] {r.get('name','')} → {email}")
            r["email"] = ""
            filtered_count += 1
    logger.info(f"非个人邮箱过滤: {filtered_count} 条")

    # Step 4: 批量/部门公用邮箱检测
    dept_email_count: dict[str, dict[str, int]] = {}
    for r in valid:
        dept = r.get("department", "未知")
        email = r.get("email", "").lower()
        if not email:
            continue
        dept_email_count.setdefault(dept, {})
        dept_email_count[dept][email] = dept_email_count[dept].get(email, 0) + 1

    dept_total: dict[str, int] = {}
    for r in valid:
        dept = r.get("department", "未知")
        dept_total[dept] = dept_total.get(dept, 0) + 1

    bulk_cleared = 0
    for dept, counts in dept_email_count.items():
        threshold = max(4, int(dept_total.get(dept, 1) * 0.3))
        bulk = {email for email, cnt in counts.items() if cnt >= threshold}
        if bulk:
            logger.info(f"  批量邮箱 [{dept}]: {bulk} (阈值≥{threshold})")
            for r in valid:
                if r.get("department") == dept and r.get("email", "").lower() in bulk:
                    r["email"] = ""
                    bulk_cleared += 1
    logger.info(f"批量邮箱清除: {bulk_cleared} 条")

    # Step 5: 邮箱格式最终验证
    format_fixed = 0
    for r in valid:
        email = r.get("email", "")
        if email:
            if "@" not in email:
                r["email"] = ""
                format_fixed += 1
            elif not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
                # 尝试修复
                cleaned_email = re.sub(r'[^a-zA-Z0-9@._%+-]', '', email)
                if re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", cleaned_email):
                    r["email"] = cleaned_email
                else:
                    r["email"] = ""
                    format_fixed += 1
    logger.info(f"邮箱格式修复: {format_fixed} 条")

    return valid


def print_statistics(records: list[dict], label: str = ""):
    """打印统计信息。"""
    total = len(records)
    with_email = sum(1 for r in records if r.get("email"))
    with_title = sum(1 for r in records if r.get("title"))
    with_url = sum(1 for r in records if r.get("url"))

    dept_counts = {}
    for r in records:
        d = r.get("department", "未知")
        dept_counts[d] = dept_counts.get(d, 0) + 1

    dept_with_email = {}
    for r in records:
        d = r.get("department", "未知")
        if r.get("email"):
            dept_with_email[d] = dept_with_email.get(d, 0) + 1

    print(f"\n{'='*60}")
    print(f"  {label}" if label else "")
    print(f"  总人数: {total}")
    print(f"  有邮箱: {with_email} ({100*with_email/total:.1f}%)" if total else "  有邮箱: 0")
    print(f"  有职称: {with_title} ({100*with_title/total:.1f}%)" if total else "  有职称: 0")
    print(f"  有主页: {with_url}")
    print(f"  院系数: {len(dept_counts)}")
    print(f"\n  {'院系':<16} {'总数':>5} {'有邮箱':>5} {'覆盖率':>6}")
    print(f"  {'-'*35}")
    for dept, count in sorted(dept_counts.items(), key=lambda x: -x[1]):
        email_count = dept_with_email.get(dept, 0)
        rate = f"{100*email_count/count:.0f}%" if count else "-"
        print(f"  {dept:<16} {count:>5} {email_count:>5} {rate:>6}")

    # 邮箱域名分布
    domains = Counter()
    for r in records:
        email = r.get("email", "")
        if email and "@" in email:
            domain = email.split("@")[1].lower()
            domains[domain] += 1

    print(f"\n  邮箱域名分布:")
    for domain, count in domains.most_common(10):
        print(f"    {domain}: {count}")


def export_final(records: list[dict]):
    """导出最终文件。"""
    from agent.exporter import export_csv, export_xlsx

    # 完整版（含无邮箱的记录）
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    full_csv = export_csv(records, f"南京大学_教师名录_完整版_{ts}")
    full_xlsx = export_xlsx(records, f"南京大学_教师名录_完整版_{ts}")

    # 仅邮箱版（只有有邮箱的）
    with_email = [r for r in records if r.get("email")]
    email_csv = None
    email_xlsx = None
    if with_email:
        email_csv = export_csv(with_email, f"南京大学_教师名录_仅邮箱_{ts}")
        email_xlsx = export_xlsx(with_email, f"南京大学_教师名录_仅邮箱_{ts}")

    return {
        "full": {"csv": full_csv, "xlsx": full_xlsx},
        "email_only": {"csv": email_csv, "xlsx": email_xlsx},
    }


def main():
    print("=" * 60)
    print("  南京大学教师邮箱数据 — 合并清洗")
    print("=" * 60)

    # 1. 加载所有数据
    all_records = load_all_sources()
    if not all_records:
        logger.error("未找到任何数据源！请先运行爬虫。")
        return

    # 2. 去重合并
    merged = merge_and_deduplicate(all_records)
    print_statistics(merged, "合并去重后")

    # 3. 清洗
    cleaned = clean(merged)
    print_statistics(cleaned, "清洗后")

    # 4. 导出
    files = export_final(cleaned)
    print(f"\n✅ 导出完成:")
    print(f"   完整版 CSV: {files['full']['csv']}")
    print(f"   完整版 XLSX: {files['full']['xlsx']}")
    if files['email_only']['csv']:
        print(f"   仅邮箱 CSV: {files['email_only']['csv']}")
        print(f"   仅邮箱 XLSX: {files['email_only']['xlsx']}")


if __name__ == "__main__":
    main()
