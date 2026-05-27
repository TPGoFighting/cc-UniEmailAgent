"""针对性修复 v3 零产量院系。

策略：不用预配置 URL，改为从首页直接搜索"师资队伍"链接。
v3 失败原因是 probe 发现 URL 可达就直接用了，但页面结构不适合检测。
这里改为：首页找链接 → 跟随 → 多种策略提取 → 详情页补充。
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
FIX_PROGRESS_FILE = OUTPUT_DIR / "nju_fix_zero_progress.json"

# 需要修复的院系（v3 零产量）
FIX_DEPARTMENTS = [
    # 文科 — v3 零产量
    {"name": "哲学系", "url": "https://philo.nju.edu.cn"},
    {"name": "商学院", "url": "https://nubs.nju.edu.cn"},
    {"name": "社会学院", "url": "https://sociology.nju.edu.cn"},
    {"name": "艺术学院", "url": "https://art.nju.edu.cn"},
    {"name": "匡亚明学院", "url": "https://dii.nju.edu.cn"},
    {"name": "中华文化研究院", "url": "https://zhwh.nju.edu.cn"},
    {"name": "体育部", "url": "https://sports.nju.edu.cn"},

    # 理科
    {"name": "化学化工学院", "url": "https://chem.nju.edu.cn"},
    {"name": "大气科学学院", "url": "https://atmos.nju.edu.cn"},
    {"name": "地理与海洋科学学院", "url": "https://geo.nju.edu.cn"},
    {"name": "生命科学学院", "url": "https://life.nju.edu.cn"},

    # 工科
    {"name": "计算机科学与技术系", "url": "https://cs.nju.edu.cn"},
    {"name": "现代工程与应用科学学院", "url": "https://eng.nju.edu.cn"},
    {"name": "环境学院", "url": "https://environment.nju.edu.cn"},

    # 医科/交叉
    {"name": "南京赫尔辛基大气与地球系统科学学院", "url": "https://nju-atmosphere-helsinki.nju.edu.cn"},
]

# 手动验证过的师资页面 URL（对于自动发现失败的院系，从这里补充）
MANUAL_FACULTY_URLS = {
    "化学化工学院": [
        "https://chem.nju.edu.cn/szdw1/szdw.htm",
        "https://chem.nju.edu.cn/szdw1/js.htm",
        "https://chem.nju.edu.cn/szdw/list.htm",
    ],
    "计算机科学与技术系": [
        "https://cs.nju.edu.cn/szdw/jsxx.htm",
        "https://cs.nju.edu.cn/szdw/list.htm",
    ],
    "生命科学学院": [
        "https://life.nju.edu.cn/szdw1/list.htm",
        "https://life.nju.edu.cn/szdw/list1.htm",
        "https://life.nju.edu.cn/szdw/js.htm",
    ],
    "现代工程与应用科学学院": [
        "https://eng.nju.edu.cn/szdw1/list.htm",
        "https://eng.nju.edu.cn/szdw/list1.htm",
    ],
    "环境学院": [
        "https://environment.nju.edu.cn/szdw1/list.htm",
        "https://environment.nju.edu.cn/szdw/list1.htm",
    ],
    "大气科学学院": [
        "https://atmos.nju.edu.cn/szdw1/list.htm",
        "https://atmos.nju.edu.cn/jsdw/list.htm",
    ],
    "地理与海洋科学学院": [
        "https://geo.nju.edu.cn/szdw1/list.htm",
        "https://geo.nju.edu.cn/jsdw/list.htm",
    ],
    "体育部": [
        "https://sports.nju.edu.cn/szdw1/list.htm",
        "https://sports.nju.edu.cn/jsdw/list.htm",
    ],
    "匡亚明学院": [
        "https://dii.nju.edu.cn/szll/szdw/list.htm",
        "https://dii.nju.edu.cn/szll/list.htm",
    ],
    "中华文化研究院": [
        "https://zhwh.nju.edu.cn/szdw1/list.htm",
        "https://zhwh.nju.edu.cn/szdw/list1.htm",
    ],
    "社会学院": [
        "https://sociology.nju.edu.cn/szdw1/js.htm",
        "https://sociology.nju.edu.cn/szdw/list.htm",
    ],
}

# 复用核心函数（从 v3 导入稳定的部分）
from agent.nju_scraper_v3 import (
    scrape_teacher_list_page, scrape_detail_page,
    find_teacher_links, find_detail_links_by_url_pattern,
    find_next_page_url, extract_emails, parse_at_sign,
    is_valid_chinese_name, _COMMON_SURNAMES,
)

FACULTY_KEYWORDS = [
    "师资队伍", "师资力量", "教师名录", "教师队伍", "人才队伍",
    "教职员工", "专任教师", "现任教师",
    "faculty", "teacher", "people", "staff",
]


async def find_faculty_link_on_homepage(page, base_url: str) -> str | None:
    """在首页寻找师资页面的链接（更激进的搜索）。"""
    base_domain = urlparse(base_url).netloc

    for attempt in range(2):
        try:
            await page.goto(base_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1.5)  # 更长的等待时间
            break
        except Exception:
            if attempt < 1:
                await asyncio.sleep(1)

    # JS 提取所有可能的师资链接
    result = await page.evaluate("""(keywords) => {
        const results = [];
        const seen = new Set();
        document.querySelectorAll('a').forEach(a => {
            const text = (a.textContent || '').trim();
            const href = (a.href || '').trim();
            if (!href || seen.has(href) || !text) return;
            if (href.startsWith('javascript:') || href.startsWith('#')) return;
            seen.add(href);

            let score = 0;
            const lower = (text + ' ' + href).toLowerCase();
            for (let i = 0; i < keywords.length; i++) {
                if (lower.includes(keywords[i].toLowerCase())) {
                    score = keywords.length - i;  // 前面的关键词权重更高
                    break;
                }
            }
            if (score > 0 && text.length <= 50) {
                results.push({text, href, score});
            }
        });
        results.sort((a, b) => b.score - a.score);
        return results.slice(0, 15);
    }""", FACULTY_KEYWORDS)

    # 验证链接可达性
    for link in result:
        for attempt in range(2):
            try:
                resp = await page.request.get(link["href"])
                if resp and resp.ok:
                    logger.info(f"  首页找到师资链接: {link['text'][:30]} → {link['href'][:80]}")
                    return link["href"]
            except Exception:
                if attempt < 1:
                    await asyncio.sleep(0.5)

    return None


async def try_manual_urls(page, dept_name: str) -> str | None:
    """尝试手动配置的备选 URL。"""
    urls = MANUAL_FACULTY_URLS.get(dept_name, [])
    for url in urls:
        for attempt in range(2):
            try:
                resp = await page.request.get(url)
                if resp and resp.ok:
                    logger.info(f"  手动 URL 可达: {url}")
                    return url
            except Exception:
                if attempt < 1:
                    await asyncio.sleep(0.5)
    return None


async def scrape_department_fixed(context, dept: dict) -> list[dict]:
    """修复版院系爬取 — 从首页搜索师资链接。"""
    dept_name = dept["name"]
    base_url = dept["url"]
    results = []
    page = await context.new_page()

    try:
        logger.info(f"修复抓取: {dept_name} ({base_url})")
        base_domain = urlparse(base_url).netloc

        # Step 1: 找师资页面
        faculty_url = await find_faculty_link_on_homepage(page, base_url)

        # Step 2: 如果首页没找到，尝试手动配置的备选 URL
        if not faculty_url:
            faculty_url = await try_manual_urls(page, dept_name)

        if not faculty_url:
            logger.warning(f"{dept_name}: 无法找到师资页面（已尝试首页搜索+手动URL）")
            return results

        logger.info(f"{dept_name}: 师资页面 → {faculty_url}")

        # Step 3: 访问师资页面
        try:
            await page.goto(faculty_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1.5)  # 更长等待
        except Exception as e:
            logger.warning(f"{dept_name}: 师资页面访问失败: {e}")
            return results

        # Step 4: 收集子页面
        urls_to_visit = [faculty_url]

        # 找子分类页面
        sub_pages = await page.evaluate("""(baseDomain) => {
            const keywords = ['现任教师', '教师名录', '专任教师', '教师列表',
                            '教授', '副教授', '讲师', '助理教授', '研究人员',
                            '博士生导师', '硕士生导师'];
            const urls = [];
            const seen = new Set();
            document.querySelectorAll('a').forEach(a => {
                const text = (a.textContent || '').trim();
                const href = a.href || '';
                if (!href || seen.has(href)) return;
                try { if (!new URL(href).hostname.endsWith(baseDomain)) return; } catch(e) { return; }
                for (const kw of keywords) {
                    if (text.includes(kw) && text.length <= 15) {
                        seen.add(href);
                        urls.push(href);
                        break;
                    }
                }
            });
            return urls.slice(0, 15);
        }""", base_domain)
        urls_to_visit.extend(sub_pages)

        # 分页
        for _ in range(5):  # 最多翻5页
            next_url = await find_next_page_url(page)
            if next_url and next_url not in urls_to_visit and len(urls_to_visit) < 30:
                urls_to_visit.append(next_url)
                try:
                    await page.goto(next_url, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(1.0)
                except Exception:
                    break
            else:
                break

        # 去重
        seen_temp = set()
        clean_urls = []
        for u in urls_to_visit:
            base = u.split("#")[0]
            if base not in seen_temp:
                seen_temp.add(base)
                clean_urls.append(base)
        urls_to_visit = clean_urls
        logger.info(f"{dept_name}: 共 {len(urls_to_visit)} 个页面")

        # Step 5: 扫描所有子页面
        all_teacher_links = []
        seen_card_names = set()
        pending_cards = []

        for url in urls_to_visit:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(1.0)  # 更长等待
            except Exception:
                continue

            # 策略 A: 列表页批量提取
            cards = await scrape_teacher_list_page(page, dept_name)
            for card in cards:
                if card["name"] not in seen_card_names:
                    seen_card_names.add(card["name"])
                    if card["url"] and (not card["email"] or not card["title"]):
                        pending_cards.append(card)
                    else:
                        results.append(card)

            # 策略 B: 教师链接识别
            teacher_links, subcat_links = await find_teacher_links(page, base_domain)
            all_teacher_links.extend(teacher_links)
            for subcat in subcat_links[:5]:
                try:
                    await page.goto(subcat["href"], wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(0.5)
                    sub_teachers, _ = await find_teacher_links(page, base_domain)
                    all_teacher_links.extend(sub_teachers)
                except Exception:
                    pass

            # 策略 C: URL 模式兜底
            detail_urls = await find_detail_links_by_url_pattern(page, base_domain)
            all_teacher_links.extend(detail_urls)

        # 去重教师链接
        seen_urls = set(r["url"] for r in results if r["url"])
        seen_names = set(r["name"] for r in results)
        unique_links = []
        for link in all_teacher_links:
            if link["href"] not in seen_urls:
                seen_urls.add(link["href"])
                name = link["text"].strip()
                name_match = re.match(r"([一-鿿]{2,3})", name)
                teacher_name = name_match.group(1) if name_match else name
                if teacher_name not in seen_names:
                    seen_names.add(teacher_name)
                    unique_links.append(link)

        # Step 6: 详情页补充
        for card in pending_cards:
            if card["url"]:
                detail = await scrape_detail_page(page, card["url"], dept_name, card["name"])
                if detail["email"] and not card["email"]:
                    card["email"] = detail["email"]
                if detail["title"] and not card["title"]:
                    card["title"] = detail["title"]
            results.append(card)

        for link in unique_links:
            name = link["text"].strip()
            name_match = re.match(r"([一-鿿]{2,3})", name)
            teacher_name = name_match.group(1) if name_match else name
            detail = await scrape_detail_page(page, link["href"], dept_name, teacher_name)
            if not detail["name"]:
                detail["name"] = teacher_name
            results.append(detail)

    except Exception as e:
        logger.error(f"{dept_name}: 修复抓取出错: {e}")
    finally:
        await page.close()

    return results


async def main():
    from playwright.async_api import async_playwright

    OUTPUT_DIR.mkdir(exist_ok=True)

    # 断点续传
    progress = {"completed": [], "all_results": []}
    if FIX_PROGRESS_FILE.exists():
        with open(FIX_PROGRESS_FILE, "r", encoding="utf-8") as f:
            progress = json.load(f)
        logger.info(f"已加载进度，已完成 {len(progress['completed'])} 个院系")

    completed = set(progress["completed"])
    all_results = progress["all_results"]
    pending = [d for d in FIX_DEPARTMENTS if d["name"] not in completed]

    logger.info(f"需修复: {len(FIX_DEPARTMENTS)} 个院系，已完成 {len(completed)}，待处理 {len(pending)}")

    if not pending:
        logger.info("全部完成!")
        return all_results

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            ignore_https_errors=True,
        )

        try:
            for i, dept in enumerate(pending):
                logger.info(f"[{i+1}/{len(pending)}] {dept['name']}")
                dept_results = await scrape_department_fixed(context, dept)
                all_results.extend(dept_results)
                completed.add(dept["name"])

                with open(FIX_PROGRESS_FILE, "w", encoding="utf-8") as f:
                    json.dump({"completed": list(completed), "all_results": all_results}, f, ensure_ascii=False, indent=2)

                logger.info(f"{dept['name']}: {len(dept_results)} 人 (累计 {len(all_results)})")
                await asyncio.sleep(1)
        finally:
            await browser.close()

    return all_results


if __name__ == "__main__":
    results = asyncio.run(main())
    logger.info(f"\n修复完成: {len(results)} 条记录")

    # 保存
    from agent.exporter import export_xlsx
    if results:
        path = export_xlsx(results, f"南京大学_教师名录_补抓_fix")
        logger.info(f"已保存: {path}")
