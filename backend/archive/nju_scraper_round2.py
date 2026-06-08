"""第二遍补抓 — 修复第一遍中抓取不足的院系。"""

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.nju_scraper import (
    OUTPUT_DIR, parse_at_sign, extract_emails,
    scrape_detail_page, export_results,
)
from agent.exporter import export_xlsx
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

PROGRESS_FILE = OUTPUT_DIR / "nju_scrape_round2_progress.json"

# 第二轮：修复后的院系 URL
ROUND2_DEPTS = [
    {
        "name": "软件学院",
        "faculty_url": "https://software.nju.edu.cn/szll/szdw/index.html",
    },
    {
        "name": "数学学院",
        "faculty_url": "https://math.nju.edu.cn/jzyg/apypl/index.html",
        "sub_urls": [
            "https://math.nju.edu.cn/jzyg/js/list.htm",
            "https://math.nju.edu.cn/jzyg/fjs/list.htm",
            "https://math.nju.edu.cn/jzyg/jj/list.htm",
        ],
    },
    {
        "name": "历史学院",
        "faculty_url": "https://history.nju.edu.cn/28475/list.htm",
    },
    {
        "name": "教育研究院",
        "faculty_url": "https://edu.nju.edu.cn/8746/list.htm",
        "sub_urls": ["https://edu.nju.edu.cn/ds/list.htm"],
    },
    {
        "name": "数字经济与管理学院",
        "faculty_url": "https://sdem.nju.edu.cn/59579/list.htm",
    },
    {
        "name": "现代工程与应用科学学院",
        "faculty_url": "https://eng.nju.edu.cn/szdw/list.htm",
    },
]


async def find_all_detail_links(page) -> list[dict]:
    """更宽松的查找：从页面找到所有看起来像教师详情页的链接。"""
    return await page.evaluate("""() => {
        const links = [];
        const seen = new Set();

        document.querySelectorAll('a').forEach(a => {
            const text = (a.textContent || '').trim();
            const href = (a.href || '').trim();
            if (!href || seen.has(href) || !text) return;
            if (href.startsWith('javascript:') || href.startsWith('#') || href.startsWith('mailto:')) return;
            if (/\\.(jpg|png|gif|pdf|doc|xls|ppt|rar|zip)$/i.test(href)) return;

            // 跳过明显的导航链接
            const navPatterns = /^(首页|概况|简介|领导|部门|制度|招聘|通知|公告|新闻|动态|学术|科研|党建|团建|学生|招生|就业|合作|联系|下载|办事|指南|登录|注册|English|校友|本科|研究生|留学|博士|博士后|培训|暑期|海外|校庆|院庆|百年|历史|渊源|专业|设置|规章|诚聘|英才|培养|行政|管理|退休|网站|中文|EN|加入|返回|更多|查看|详情|关闭|确定|取消)$/;
            if (navPatterns.test(text)) return;

            // 包含中文字符，且文本不太长
            if (/[\\u4e00-\\u9fff]/.test(text) && text.length <= 30) {
                seen.add(href);
                links.push({text, href});
            }
        });

        return links;
    }""")


async def scrape_dept(context, dept: dict) -> list[dict]:
    """抓取单个院系（第二轮）。"""
    dept_name = dept["name"]
    results = []
    page = await context.new_page()
    seen_urls = set()
    teacher_links = []

    try:
        logger.info(f"补抓: {dept_name}")

        # 访问主师资页面
        faculty_url = dept["faculty_url"]
        try:
            await page.goto(faculty_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"{dept_name}: 师资页面访问失败: {e}")
            return results

        # 找所有可能的教师链接
        all_links = await find_all_detail_links(page)
        logger.info(f"{dept_name}: 找到 {len(all_links)} 个候选链接")

        for link in all_links:
            href = link["href"]
            if href not in seen_urls:
                seen_urls.add(href)
                teacher_links.append(link)

        # 访问子页面
        for sub_url in dept.get("sub_urls", []):
            try:
                await page.goto(sub_url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(1.5)
                sub_links = await find_all_detail_links(page)
                logger.info(f"{dept_name}: 子页面找到 {len(sub_links)} 个候选链接")
                for link in sub_links:
                    if link["href"] not in seen_urls:
                        seen_urls.add(link["href"])
                        teacher_links.append(link)
            except Exception as e:
                logger.warning(f"{dept_name}: 子页面访问失败: {e}")

        # 过滤：只保留看起来像教师详情页的链接
        # NJU 常见的教师详情 URL 模式: /iXXXXX.htm, /page.htm, /XX/XX/cXXXXX, /XX/list.htm
        detail_links = []
        for link in teacher_links:
            href = link["href"]
            text = link["text"]
            # 教师详情页特征
            is_detail = (
                "/i" in href and href.endswith(".htm")
                or "/page.htm" in href
                or "/c" in href and href.endswith(".htm")
                or re.search(r"/\d{4,6}/\d{2}/c\d+", href)
            )
            if is_detail:
                detail_links.append(link)

        # 如果通过 URL 模式筛到的太少，用文本模式
        if len(detail_links) < 5:
            detail_links = [l for l in teacher_links if re.match(r"^[一-鿿]{2,3}", l["text"])]

        logger.info(f"{dept_name}: 筛选后 {len(detail_links)} 个教师详情链接")

        # 逐个访问
        for i, link in enumerate(detail_links):
            text = link["text"]
            href = link["href"]

            name_match = re.match(r"^([一-鿿]{2,3})", text)
            name = name_match.group(1) if name_match else text

            logger.debug(f"{dept_name}: [{i+1}/{len(detail_links)}] {name}")
            detail = await scrape_detail_page(page, href, dept_name, name)
            if not detail["name"]:
                detail["name"] = name
            results.append(detail)

    except Exception as e:
        logger.error(f"{dept_name}: 抓取出错: {e}")
    finally:
        await page.close()

    return results


async def main():
    from playwright.async_api import async_playwright

    OUTPUT_DIR.mkdir(exist_ok=True)

    # 加载第一轮结果
    round1_file = sorted(OUTPUT_DIR.glob("南京大学_教师名录_clean.xlsx"))
    if round1_file:
        logger.info(f"第一轮清洁版文件: {round1_file[0]}")

    # 加载进度
    progress = {"completed": [], "all_results": []}
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            progress = json.load(f)

    completed = set(progress["completed"])
    all_results = progress["all_results"]
    pending = [d for d in ROUND2_DEPTS if d["name"] not in completed]

    logger.info(f"第二轮: {len(ROUND2_DEPTS)} 个院系, 已完成 {len(completed)}, 待处理 {len(pending)}")

    if not pending:
        logger.info("全部完成!")
        return all_results

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
        )

        try:
            for dept in pending:
                dept_results = await scrape_dept(context, dept)
                all_results.extend(dept_results)
                completed.add(dept["name"])

                with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                    json.dump({"completed": list(completed), "all_results": all_results}, f, ensure_ascii=False, indent=2)

                logger.info(f"{dept['name']}: {len(dept_results)} 人 (累计 {len(all_results)})")
                await asyncio.sleep(1)
        finally:
            await browser.close()

    return all_results


if __name__ == "__main__":
    results = asyncio.run(main())
    if results:
        # 合并到已有的干净结果中
        path = OUTPUT_DIR / "南京大学_教师名录_round2.xlsx"
        export_xlsx(results, "南京大学_教师名录_补抓")
        logger.info(f"第二轮结果保存到: {path}")
        logger.info(f"共 {len(results)} 条")
    else:
        logger.info("无新数据")
