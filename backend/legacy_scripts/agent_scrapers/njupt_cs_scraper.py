"""
南京邮电大学计算机学院教师邮箱爬虫
目标：https://cs.njupt.edu.cn → 教师名录 → 详情页 → 邮箱
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

TASK_ID = "ea301d37-6212-4f73-8dd8-6ff95e0dcd6a"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / TASK_ID
COLLEGE_NAME = "计算机学院/软件学院/网络空间安全学院"
CS_URL = "https://cs.njupt.edu.cn"

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

TITLE_KW = [
    "教授", "副教授", "助理教授", "讲师", "研究员", "副研究员",
    "助理研究员", "工程师", "高级工程师", "院士", "博导", "硕导",
    "长江学者", "杰青", "优青", "博士后", "实验师", "高级实验师",
    "青年专聘教授", "校聘副教授", "预聘副教授", "特聘教授",
    "客座教授", "名誉教授", "国家级教学名师", "青年教授",
]

PUBLIC_LOCAL = {"webmaster", "admin", "info", "office", "master", "president",
                "xb", "xxgk", "jwc", "yjsc", "rsc", "gjc", "tw", "xsc",
                "jsjsj", "jsjyz", "jsjxy", "sxydw", "cs"}

# 导航关键词（需要排除的）
NAV_KW = {
    "首页", "学院概况", "学院简介", "机构设置", "新闻动态", "新闻中心",
    "通知公告", "学术动态", "科研动态", "人才培养", "招生信息", "招生宣传",
    "党建工作", "学生工作", "团学工作", "工会工作", "校友工作", "校友之家",
    "实验室", "联系我们", "院长信箱", "下载中心", "下载专区", "规章制度",
    "师德师风", "信息公开", "网站地图", "返回首页", "设为首页", "收藏本站",
    "师资队伍", "师资概况", "教师名录", "专任教师", "非专任教师", "导师介绍",
    "智慧校园", "诚聘英才", "领导信箱", "现任领导",
    "党建思政", "党委概况", "党建活动", "理论学习", "廉政监督",
    "本科生教育", "研究生教育", "专业介绍", "研究生培养",
    "创新竞赛", "创新班", "教学动态", "科学研究", "学科建设",
    "科研平台", "科研方向", "学术交流", "学生活动", "学子风采",
    "学工队伍", "研究生管理", "院徽院训", "本科教学", "研究生教学",
    "科研工作", "师资建设", "党员发展",
    "南邮主页", "南京邮电", "校内链接", "四电四邮", "学术组织",
    "个人信息", "返回列表", "教师介绍", "教师详细信息",
    "更多", "详情", "登录", "注册", "注销", "忘记密码",
    "下一页", "上一页", "尾页", "末页",
    "视窗", "菜单", "导航", "搜索", "友情链接",
}


def is_chinese_name(text: str) -> bool:
    text = text.strip()
    if not re.fullmatch(r"[一-鿿]{2,4}", text):
        return False
    if text in NAV_KW:
        return False
    if text[-1] in "报组室部处委会局办系院所馆站网栏目页版":
        return False
    if any(text.endswith(s) for s in ["学院", "大学", "中心", "研究所", "实验室"]):
        return False
    return True


def is_public_email(email: str) -> bool:
    if not email:
        return True
    local = email.lower().split("@")[0]
    if local in PUBLIC_LOCAL:
        return True
    # 检查是否是 cs.njupt.edu.cn 域名的公共邮箱（如 cs@njupt.edu.cn）
    if local in ("cs", "csxy", "csbgs", "cs_xy"):
        return True
    return any(kw in local for kw in PUBLIC_LOCAL)


def parse_at_sign(text: str) -> str:
    text = re.sub(r"\s*\[at\]\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(at\)\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*#@\s*", "@", text)
    text = re.sub(r"\s*\[@\]\s*", "@", text)
    text = re.sub(r"\s*\[dot\]\s*", ".", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(dot\)\s*", ".", text, flags=re.IGNORECASE)
    return text


def extract_titles(text: str) -> str:
    found = []
    for kw in TITLE_KW:
        if kw in text:
            found.append(kw)
    # 去重（短词可能被包含在长词中）
    result = []
    for t in found:
        if not any(t != o and t in o for o in found):
            result.append(t)
    return "、".join(result[:5])


async def discover_teacher_list_pages(context) -> list[str]:
    """从CS学院首页发现教师列表页入口"""
    page = await context.new_page()
    list_urls = []

    try:
        await page.goto(CS_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)

        links = await page.evaluate("""() => {
            const ls = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const t = (a.textContent || '').trim();
                const h = a.href;
                if (!t || !h || h.startsWith('javascript:') || h === '#' || h.includes('mailto:')) return;
                ls.push({t: t.substring(0, 60), h: h});
            });
            return ls;
        }""")

        # 找教师名录入口
        teacher_entry_kw = ["师资队伍", "师资概况", "教师名录", "专任教师",
                           "导师介绍", "教师队伍", "导师队伍", "队伍建设", "师资"]

        for link in links:
            text = link["t"]
            href = link["h"]
            if any(kw in text for kw in teacher_entry_kw):
                if len(text) < 15 and "cs.njupt.edu.cn" in href:
                    list_urls.append(href)
                    logger.info(f"  发现入口: {text} → {href}")

        # 如果没找到，尝试常见路径
        if not list_urls:
            common = [
                f"{CS_URL}/18762/list.htm",
                f"{CS_URL}/szdw/list.htm",
                f"{CS_URL}/szdw.htm",
                f"{CS_URL}/18762/list.htm",
            ]
            logger.info("  未找到标准入口，使用常见路径探测")
            for url in common:
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=10000)
                    if resp and resp.status == 200:
                        body = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 300) : ''")
                        if any(kw in body for kw in ["教师", "教授", "博士", "导师"]):
                            list_urls.append(url)
                            logger.info(f"  探测有效: {url}")
                except Exception:
                    pass
    finally:
        await page.close()

    return list_urls


async def collect_teacher_entries(context, list_url: str) -> list[dict]:
    """从教师列表页收集教师详情链接"""
    page = await context.new_page()
    entries = []
    seen = set()

    try:
        resp = await page.goto(list_url, wait_until="domcontentloaded", timeout=20000)
        if resp and resp.status >= 400:
            return entries
        await asyncio.sleep(3)

        # 检查是否有分页
        all_links = await page.evaluate("""() => {
            const ls = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const t = (a.textContent || '').trim();
                const h = a.href;
                if (!t || !h || h.startsWith('javascript:') || h === '#' || h.includes('mailto:')) return;
                ls.push({t: t.substring(0, 80), h: h});
            });
            return ls;
        }""")

        # 查找分页链接（同时也在当前页面搜索）
        page_urls = set()
        for link in all_links:
            text = link["t"]
            href = link["h"]

            # 中文姓名链接 → 直接加入
            if is_chinese_name(text):
                if href not in seen:
                    seen.add(href)
                    entries.append({"name": text, "url": href, "college": COLLEGE_NAME})
                continue

            # yjs 导师系统详情页
            if "yjs.njupt.edu.cn" in href and "dsfcxq" in href:
                if href not in seen:
                    seen.add(href)
                    entries.append({"name": text, "url": href, "college": COLLEGE_NAME})
                continue

            # "page.htm" 模式（CS学院详情页）
            if "/page.htm" in href and "cs.njupt.edu.cn" in href:
                if href not in seen:
                    seen.add(href)
                    entries.append({"name": text, "url": href, "college": COLLEGE_NAME})
                continue

            # 收集可能的分页链接
            if any(p in text or p in href.lower() for p in ["下一页", "下页", "尾页"]):
                if "cs.njupt.edu.cn" in href:
                    page_urls.add(href)

            # 分页数字链接
            if text.strip().isdigit():
                if "cs.njupt.edu.cn" in href and href not in seen:
                    page_urls.add(href)

        logger.info(f"  {list_url}: {len(entries)} 个教师条目, {len(page_urls)} 个分页")

        # 遍历分页
        for p_url in sorted(page_urls)[:30]:  # 最多翻30页
            if p_url in seen:
                continue
            seen.add(p_url)
            try:
                await page.goto(p_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)

                p_links = await page.evaluate("""() => {
                    const ls = [];
                    document.querySelectorAll('a[href]').forEach(a => {
                        const t = (a.textContent || '').trim();
                        const h = a.href;
                        if (!t || !h || h.startsWith('javascript:') || h === '#' || h.includes('mailto:')) return;
                        ls.push({t: t.substring(0, 80), h: h});
                    });
                    return ls;
                }""")

                count_before = len(entries)
                for link in p_links:
                    text = link["t"]
                    href = link["h"]
                    if is_chinese_name(text) and href not in seen:
                        seen.add(href)
                        entries.append({"name": text, "url": href, "college": COLLEGE_NAME})
                    elif "/page.htm" in href and "cs.njupt.edu.cn" in href and href not in seen:
                        seen.add(href)
                        entries.append({"name": text, "url": href, "college": COLLEGE_NAME})
                    elif "yjs.njupt.edu.cn" in href and "dsfcxq" in href and href not in seen:
                        seen.add(href)
                        entries.append({"name": text, "url": href, "college": COLLEGE_NAME})

                new_count = len(entries) - count_before
                if new_count > 0:
                    logger.info(f"    分页 {p_url}: +{new_count} 人")
            except Exception:
                pass

    except Exception as e:
        logger.warning(f"  列表页失败: {str(e)[:80]}")
    finally:
        await page.close()

    return entries


async def scrape_teacher_profile(context, entry: dict) -> dict | None:
    """访问教师详情页，提取完整信息"""
    page = await context.new_page()
    try:
        url = entry["url"]
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(1)

        # 提取姓名
        name = entry["name"]
        if not is_chinese_name(name):
            title_text = await page.evaluate("() => document.title || ''")
            # 从标题提取姓名，如 "张三-南京邮电大学计算机学院"
            m = re.match(r"^([一-鿿]{2,4})\s*[-–—|]", title_text)
            if m and is_chinese_name(m.group(1)):
                name = m.group(1)
            else:
                # 从页面文本提取
                body = await page.evaluate("() => document.body ? document.body.innerText : ''")
                m2 = re.search(r"姓\s*名\s*[：:]\s*([一-鿿]{2,4})", body)
                if m2:
                    name = m2.group(1)
                else:
                    # 尝试从标题 tag 提取
                    headings = await page.evaluate("""() => {
                        const hs = [];
                        document.querySelectorAll('h1,h2,h3,.name,.teacher-name,[class*="name"]').forEach(h => {
                            hs.push(h.textContent.trim());
                        });
                        return hs;
                    }""")
                    for h in headings:
                        m3 = re.match(r"^([一-鿿]{2,4})", h)
                        if m3 and is_chinese_name(m3.group(1)):
                            name = m3.group(1)
                            break
                    else:
                        if not body:
                            body = await page.evaluate("() => document.body ? document.body.innerText : ''")
                        for line in body.split("\n")[:10]:
                            line = line.strip()
                            if is_chinese_name(line):
                                name = line
                                break

        if not is_chinese_name(name):
            return None

        # 提取邮箱
        body = await page.evaluate("() => document.body ? document.body.innerText : ''")
        body = parse_at_sign(body)
        html = await page.evaluate("() => document.body ? document.body.innerHTML : ''")
        html = parse_at_sign(html)

        email = ""
        # 优先从 "电子邮箱" 或 "E-mail" 等标签后提取
        em = re.search(r"(?:电子邮箱|邮箱|E-?mail)\s*[：:]\s*(\S+@\S+)", body, re.IGNORECASE)
        if em:
            email = em.group(1).strip().rstrip("。,，;；")
        else:
            # 从全文提取第一个非公开邮箱
            all_text = body + " " + html
            emails = EMAIL_RE.findall(all_text)
            # 过滤掉包含HTML实体的假邮箱
            valid_emails = [e for e in emails if not re.search(r'&[a-z]+;', e)]
            email = next((e for e in valid_emails if not is_public_email(e)), "")

        if is_public_email(email):
            email = ""

        # 提取职称
        title = extract_titles(body[:3000])

        # 提取学院（可能详情页有更精确的信息）
        college = COLLEGE_NAME

        if email:
            logger.info(f"  ✅ {name} → {email} [{title[:30]}]")

        return {
            "姓名": name,
            "邮箱": email,
            "学院": college,
            "职称": title,
            "主页链接": url,
        }

    except Exception as e:
        return None
    finally:
        await page.close()


async def main():
    logger.info("=" * 60)
    logger.info("🎓 南京邮电大学计算机学院 教师邮箱爬虫")
    logger.info(f"   目标: {CS_URL}")
    logger.info(f"   输出: {OUTPUT_DIR}")
    logger.info("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"

        # 阶段1：发现教师列表页
        logger.info("\n📌 阶段1：发现教师列表页")
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=ua)
        list_urls = await discover_teacher_list_pages(ctx)
        await ctx.close()

        if not list_urls:
            # 回退到已知URL
            logger.info("  使用已知教师名录URL")
            list_urls = ["https://cs.njupt.edu.cn/18762/list.htm"]

        logger.info(f"  教师列表页: {list_urls}")

        # 阶段2：从列表页收集教师详情链接
        logger.info("\n📌 阶段2：收集教师详情页链接")
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=ua)
        all_entries = []
        seen_urls = set()

        for list_url in list_urls:
            entries = await collect_teacher_entries(ctx, list_url)
            for e in entries:
                if e["url"] not in seen_urls:
                    seen_urls.add(e["url"])
                    all_entries.append(e)

        await ctx.close()

        logger.info(f"\n  📊 收集到 {len(all_entries)} 个教师详情页")
        if all_entries:
            # 打印前20条示例
            for e in all_entries[:20]:
                logger.info(f"    {e['name']} → {e['url'][:80]}")

        # 阶段3：批量爬取详情页
        logger.info(f"\n📌 阶段3：批量爬取 {len(all_entries)} 个详情页")
        sem = asyncio.Semaphore(5)
        all_results = []

        async def process(entry):
            async with sem:
                ctx = await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=ua)
                try:
                    return await scrape_teacher_profile(ctx, entry)
                finally:
                    await ctx.close()

        batch_size = 15
        for start in range(0, len(all_entries), batch_size):
            end = min(start + batch_size, len(all_entries))
            batch = all_entries[start:end]
            logger.info(f"  [{start+1}-{end}/{len(all_entries)}]")
            tasks = [process(e) for e in batch]
            results = await asyncio.gather(*tasks)
            valid = [r for r in results if r]
            all_results.extend(valid)
            logger.info(f"    本批成功: {len(valid)}, 累计: {len(all_results)}")

        await browser.close()

    # === 数据清洗 ===
    logger.info(f"\n{'='*60}")
    logger.info("📊 数据清洗")
    logger.info(f"  原始结果: {len(all_results)}")

    # 去重
    seen_key = set()
    dedup = []
    for r in all_results:
        key = (r["姓名"], r["邮箱"])
        if key not in seen_key:
            seen_key.add(key)
            dedup.append(r)

    # 过滤无效结果
    bad_names = {"个人信息", "视窗", "登录", "菜单", "导航", "更多", "详情",
                 "首页", "返回", "上一页", "下一页", "尾页", "教师介绍"}
    final = []
    for r in dedup:
        name = r["姓名"]
        if name in bad_names or name in NAV_KW:
            continue
        if not is_chinese_name(name):
            continue
        final.append(r)

    with_email = [r for r in final if r["邮箱"]]
    no_email = [r for r in final if not r["邮箱"]]
    logger.info(f"  去重: {len(dedup)} → 过滤后: {len(final)}")
    logger.info(f"  有邮箱: {len(with_email)}, 无邮箱: {len(no_email)}")

    if with_email:
        logger.info(f"\n📋 有邮箱教师 (前20条):")
        for r in with_email[:20]:
            logger.info(f"   {r['姓名']} <{r['邮箱']}> {r['职称'][:25]}")

    # === 导出 CSV ===
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"南京邮电大学_计算机学院_教师邮箱_{timestamp}.csv"

    all_fields = ["姓名", "邮箱", "学院", "职称", "主页链接"]
    # 有邮箱的排在前面
    final_sorted = with_email + no_email

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=all_fields)
        writer.writeheader()
        writer.writerows(final_sorted)

    logger.info(f"\n💾 CSV 已保存: {csv_path}")

    # 无邮箱
    if no_email:
        ne_path = OUTPUT_DIR / f"南京邮电大学_计算机学院_无邮箱_{timestamp}.csv"
        with open(ne_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=all_fields)
            writer.writeheader()
            writer.writerows(no_email)
        logger.info(f"💾 无邮箱名单: {ne_path}")

    logger.info(f"\n✅ 完成! {len(final)} 人, {len(with_email)} 个邮箱")
    logger.info(f"📁 {csv_path}")

    print(f"\n[FILES]")
    print(f"{csv_path.name} | 南京邮电大学计算机学院教师邮箱 (共{len(final)}条, {len(with_email)}个邮箱)")
    print(f"[/FILES]")


if __name__ == "__main__":
    asyncio.run(main())
