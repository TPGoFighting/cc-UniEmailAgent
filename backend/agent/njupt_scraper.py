"""
南京邮电大学教师邮箱爬虫 v3
目标：计算机学院 / 软件学院 / 网络空间安全学院（cs.njupt.edu.cn）
爬取字段：姓名、邮箱、职称、个人主页链接、个人简介

v3 改进：
- yjs.njupt.edu.cn 页面：从 "姓　　名: XXX" 格式提取姓名
- cs.njupt.edu.cn 页面：从 <title>/<h1> 提取姓名
- 严格过滤导航链接和公共邮箱
- 数据后处理清洗
"""

import asyncio
import csv
import re
import sys
import logging
from datetime import datetime
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("请先安装: pip install playwright && playwright install chromium")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

BASE_URL = "https://cs.njupt.edu.cn"
TEACHER_LIST_URL = f"{BASE_URL}/18762/list.htm"

# 职称关键词
TITLE_KW = [
    "教授", "副教授", "助理教授", "讲师", "研究员", "副研究员",
    "助理研究员", "工程师", "高级工程师", "院士", "博导", "硕导",
    "长江学者", "杰青", "优青", "博士后", "实验师",
    "青年专聘教授", "校聘副教授", "预聘副教授", "特聘教授",
    "客座教授", "名誉教授", "国家级教学名师",
]

# 公共邮箱前缀（严格排除）
PUBLIC_EMAILS = {
    "jsjsj@njupt.edu.cn",   # 书记信箱
    "jsjyz@njupt.edu.cn",   # 院长信箱
    "jsjxy@njupt.edu.cn",   # 学院公共邮箱
}

# 导航/非教师链接文本
NAV_TEXTS = {
    "首页", "学院概况", "学院简介", "机构设置", "新闻动态", "新闻中心",
    "通知公告", "学术动态", "科研动态", "人才培养", "招生信息", "招生宣传",
    "党建工作", "学生工作", "团学工作", "工会工作", "校友工作", "校友之家",
    "实验室", "联系我们", "院长信箱", "下载中心", "下载专区", "规章制度",
    "师德师风", "信息公开", "网站地图", "返回首页", "设为首页", "收藏本站",
    "计算机学院", "软件学院", "网络空间安全学院",
    "师资队伍", "师资概况", "教师名录", "专任教师", "非专任教师", "导师介绍",
    "智慧校园", "诚聘英才", "领导信箱", "现任领导",
    "党建思政", "党委概况", "党建活动", "理论学习", "廉政监督",
    "本科生教育", "研究生教育", "专业介绍", "研究生培养",
    "创新竞赛", "创新班", "教学动态", "科学研究", "学科建设",
    "科研平台", "科研方向", "学术交流", "学生活动", "学子风采",
    "学工队伍", "研究生管理", "院徽院训", "本科教学", "研究生教学",
    "科研工作", "师资建设", "党员发展",
    "南邮主页", "南京邮电", "校内链接", "四电四邮", "学术组织",
    "个人信息", "返回列表",
    "更多", "详情", "登录", "注册", "注销", "忘记密码",
    "下一页", "上一页", "尾页", "末页",
    "视窗", "菜单", "导航", "搜索", "友情链接",
}

# 不是姓名的干扰词（用于从页面文本中过滤）
NAME_BLACKLIST = NAV_TEXTS | {
    "联系方式", "电子邮箱", "导师类型", "技术职称", "学术型", "专业型",
    "博士招生", "硕士招生", "研究领域", "个人简介", "发表论文",
    "研究方向", "办公地点", "办公电话", "传真号码", "邮政编码",
    "通讯地址", "所属学院", "所属系所",
}


def is_chinese_name(text: str) -> bool:
    text = text.strip()
    if not re.fullmatch(r"[一-鿿]{2,4}", text):
        return False
    if text in NAME_BLACKLIST:
        return False
    bad_ends = set("报组室部处委会局办系院所馆站网栏目页版")
    if text[-1] in bad_ends:
        return False
    return True


def is_public_email(email: str) -> bool:
    return email.lower() in PUBLIC_EMAILS


def parse_at_sign(text: str) -> str:
    text = re.sub(r"\s*\[at\]\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(at\)\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*#@\s*", "@", text)
    text = re.sub(r"\s*\[@\]\s*", "@", text)
    text = re.sub(r"\s*\(@\)\s*", "@", text)
    text = re.sub(r"\s*\[dot\]\s*", ".", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(dot\)\s*", ".", text, flags=re.IGNORECASE)
    return text


def extract_titles(text: str) -> str:
    found = []
    for kw in TITLE_KW:
        if kw in text:
            found.append(kw)
    # 去重（有的关键词是其他关键词的子串）
    return "、".join(found[:5])


def extract_bio(text: str, max_len: int = 500) -> str:
    lines = text.strip().split("\n")
    skip_words = [
        "邮箱", "电话", "地址", "邮编", "传真", "办公",
        "版权所有", "Copyright", "导航", "首页", "返回",
        "书记信箱", "院长信箱", "欢迎访问", "南邮主页",
        "智慧校园", "诚聘英才", "领导信箱",
        "导师类型", "技术职称", "电子邮箱", "学术型",
        "专业型", "博士招生", "硕士招生", "招生学科",
        "姓　　名", "性　　別",
    ]
    bio_lines = []
    for line in lines:
        line = line.strip()
        if not line or len(line) < 6:
            continue
        if any(sp in line for sp in skip_words):
            continue
        bio_lines.append(line)
        if sum(len(l) for l in bio_lines) > max_len:
            break
    result = " ".join(bio_lines)[:max_len]
    return result.strip()


async def extract_name_from_yjs_page(page) -> str:
    """从研究生导师系统页面提取姓名（"姓　　名: XXX" 格式）。"""
    text = await page.evaluate(
        "() => document.body ? document.body.innerText : ''"
    )
    # 格式: "姓　　名:	鲍秉坤"
    m = re.search(r"姓\s*名\s*[：:]\s*([一-鿿]{2,4})", text)
    if m:
        return m.group(1)
    return ""


async def extract_name_from_cs_page(page) -> str:
    """从学院教师页面提取姓名（从 title 或 页面内容）。"""
    # 策略1：页面 title
    title = await page.evaluate("() => document.title || ''")
    # 格式: "鲍秉坤 - 南京邮电大学" 或 "教师个人信息"
    m = re.match(r"^([一-鿿]{2,4})\s*[-–—|]", title)
    if m and is_chinese_name(m.group(1)):
        return m.group(1)

    # 策略2：h1/h2/h3
    headings = await page.evaluate("""() => {
        const hs = [];
        document.querySelectorAll('h1,h2,h3').forEach(h => {
            hs.push(h.textContent.trim());
        });
        return hs;
    }""")
    for h in headings:
        m = re.match(r"^([一-鿿]{2,4})", h)
        if m and is_chinese_name(m.group(1)):
            return m.group(1)

    # 策略3：页面正文中的第一个中文姓名
    text = await page.evaluate(
        "() => document.body ? document.body.innerText.substring(0, 500) : ''"
    )
    for line in text.split("\n"):
        line = line.strip()
        if is_chinese_name(line):
            return line

    return ""


async def scrape_profile(context, link_text: str, url: str,
                          dept: str) -> dict | None:
    """访问教师详情页并提取信息。"""
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(0.8)

        # 根据域名选择姓名提取策略
        if "yjs.njupt.edu.cn" in url:
            name = await extract_name_from_yjs_page(page)
        else:
            name = await extract_name_from_cs_page(page)

        # 如果仍然提取失败，用链接文本（前提是链接文本是姓名）
        if not name and is_chinese_name(link_text):
            name = link_text
        if not name:
            name = link_text  # 最后回退

        # 提取邮箱
        html = await page.evaluate("() => document.body ? document.body.innerHTML : ''")
        html = parse_at_sign(html)
        body_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        body_text = parse_at_sign(body_text)

        # 对于 yjs 页面，也找"电子邮箱:"字段
        if "yjs.njupt.edu.cn" in url:
            email_match = re.search(r"电子邮箱\s*[：:]\s*(\S+@\S+)", body_text)
            if email_match:
                email = email_match.group(1).strip()
            else:
                all_text = body_text + " " + html
                emails = EMAIL_RE.findall(all_text)
                email = next((e for e in emails if not is_public_email(e)), "")
        else:
            all_text = body_text + " " + html
            emails = EMAIL_RE.findall(all_text)
            email = next((e for e in emails if not is_public_email(e)), "")

        # 过滤公共邮箱
        if is_public_email(email):
            email = ""

        # 提取职称
        title = extract_titles(body_text[:2000])

        # 提取个人简介
        bio = extract_bio(body_text)

        if email:
            logger.info(f"  ✅ {name} → {email} | {title[:30]}")

        return {
            "姓名": name,
            "邮箱": email,
            "学院": dept,
            "职称": title,
            "主页链接": url,
            "个人简介": bio,
        }

    except Exception as e:
        logger.debug(f"  ⚠️ {link_text} 页面异常: {str(e)[:60]}")
        return None
    finally:
        await page.close()


async def main():
    logger.info("=" * 60)
    logger.info("🎓 南京邮电大学 教师邮箱爬虫 v3")
    logger.info("   目标：计算机学院 / 软件学院 / 网络空间安全学院")
    logger.info("=" * 60)

    dept = "计算机学院/软件学院/网络空间安全学院"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # —— 阶段1：从列表页提取所有教师姓名 + 链接 ——
        logger.info(f"\n📌 阶段1：提取教师列表 ({TEACHER_LIST_URL})")

        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        )
        page = await ctx.new_page()
        await page.goto(TEACHER_LIST_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # 从页面正文提取所有教师姓名
        body_text = await page.evaluate(
            "() => document.body ? document.body.innerText : ''"
        )
        all_teacher_names = []
        for token in re.split(r"[\s\t\n]+", body_text):
            token = token.strip()
            if is_chinese_name(token) and token not in NAV_TEXTS:
                all_teacher_names.append(token)
        # 去重保序
        seen = set()
        unique_names = []
        for n in all_teacher_names:
            if n not in seen:
                seen.add(n)
                unique_names.append(n)
        logger.info(f"  从正文提取到 {len(unique_names)} 个潜在教师姓名")

        # 从链接提取教师条目（文字是中文姓名或指向个人主页的链接）
        all_links = await page.evaluate("""() => {
            const links = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const text = (a.textContent || '').trim();
                const href = a.href;
                if (!text || !href || href.startsWith('javascript:') || href === '#') return;
                if (href.includes('mailto:')) return;
                // 只保留看起来像教师信息的链接
                // 包括 yjs.njupt.edu.cn (导师系统) 和 cs.njupt.edu.cn 详情页
                if (href.includes('yjs.njupt.edu.cn') ||
                    href.includes('/page.htm') ||
                    href.includes('/szdw/') ||
                    (href.includes('cs.njupt.edu.cn') && /\\d{4}\\/\\d{4}\\/c\\d/.test(href))) {
                    links.push({text: text.substring(0, 40), url: href});
                }
            });
            return links;
        }""")

        logger.info(f"  从链接提取到 {len(all_links)} 个潜在教师链接")

        # 如果是中文姓名 → 直接使用
        # 如果是"个人信息"等 → 需要从 yjs 页面提取
        teacher_entries = []
        for link in all_links:
            link_text = link["text"]
            url = link["url"]
            if is_chinese_name(link_text) and link_text not in NAV_TEXTS:
                teacher_entries.append({"name": link_text, "url": url})
            elif "yjs.njupt.edu.cn" in url:
                # yjs 导师链接，姓名需要从页面中提取
                teacher_entries.append({"name": link_text, "url": url})

        # 去重（按 URL）
        seen_url = set()
        unique_entries = []
        for e in teacher_entries:
            if e["url"] not in seen_url:
                seen_url.add(e["url"])
                unique_entries.append(e)

        logger.info(f"  去重后: {len(unique_entries)} 个教师详情页待爬取")

        await ctx.close()

        # —— 阶段2：批量访问详情页 ——
        logger.info(f"\n📌 阶段2：访问详情页提取信息")

        all_results = []
        sem = asyncio.Semaphore(4)

        async def process(entry):
            async with sem:
                ctx = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                )
                try:
                    return await scrape_profile(ctx, entry["name"], entry["url"], dept)
                finally:
                    await ctx.close()

        batch_size = 20
        for start in range(0, len(unique_entries), batch_size):
            end = min(start + batch_size, len(unique_entries))
            batch = unique_entries[start:end]
            logger.info(f"\n  [{start+1}-{end}/{len(unique_entries)}]")
            tasks = [process(e) for e in batch]
            results = await asyncio.gather(*tasks)
            count = 0
            for r in results:
                if r:
                    all_results.append(r)
                    count += 1
            logger.info(f"    本批: {count} 条")

        # 将只在正文中出现但没有找到链接的教师姓名也加入
        # （这些可能没有个人主页，但记录名字以备后用）
        linked_names = {r["姓名"] for r in all_results}
        for name in unique_names:
            if name not in linked_names:
                all_results.append({
                    "姓名": name,
                    "邮箱": "",
                    "学院": dept,
                    "职称": "",
                    "主页链接": "",
                    "个人简介": "",
                })

        await browser.close()

    # —— 阶段3：数据清洗 ——
    logger.info(f"\n{'='*60}")
    logger.info("📊 数据清洗")

    # 去重（按姓名+邮箱）
    seen_key = set()
    clean = []
    for r in all_results:
        key = (r["姓名"], r["邮箱"])
        if key not in seen_key:
            seen_key.add(key)
            clean.append(r)

    # 过滤
    final = []
    bad_names = {"个人信息", "视窗", "登录", "菜单", "导航", "更多", "详情",
                 "首页", "返回", "上一页", "下一页", "尾页"}
    for r in clean:
        name = r["姓名"]
        if name in bad_names:
            continue
        if name in NAV_TEXTS:
            continue
        if not is_chinese_name(name):
            continue
        # 如果没邮箱也没链接，跳过
        if not r["邮箱"] and not r["主页链接"]:
            continue
        final.append(r)

    logger.info(f"  原始={len(all_results)} → 去重={len(clean)} → 过滤={len(final)}")

    with_email = [r for r in final if r["邮箱"]]
    no_email = [r for r in final if not r["邮箱"]]

    logger.info(f"\n📊 最终统计:")
    logger.info(f"   总教师数: {len(final)}")
    logger.info(f"   有邮箱: {len(with_email)}")
    logger.info(f"   无邮箱: {len(no_email)}")

    if with_email:
        logger.info(f"\n📋 有邮箱教师（前20条）:")
        for r in with_email[:20]:
            logger.info(f"   {r['姓名']} <{r['邮箱']}> {r['职称'][:25]}")

    # —— 导出 ——
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fields = ["姓名", "邮箱", "学院", "职称", "主页链接", "个人简介"]

    csv_path = OUTPUT_DIR / f"南京邮电大学_教师邮箱_{timestamp}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(final)
    logger.info(f"\n💾 主文件: {csv_path} ({len(final)} 条)")

    if no_email:
        ne_path = OUTPUT_DIR / f"南京邮电大学_无邮箱教师_{timestamp}.csv"
        with open(ne_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(no_email)
        logger.info(f"💾 无邮箱: {ne_path} ({len(no_email)} 条)")

    logger.info(f"\n✅ 完成！")
    return csv_path


if __name__ == "__main__":
    asyncio.run(main())
