"""第三遍补抓 — 修复域名错误的院系。"""

import asyncio, json, logging, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.exporter import export_xlsx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
PROGRESS_FILE = OUTPUT_DIR / "nju_scrape_round3_progress.json"

ROUND3_DEPTS = [
    {
        "name": "新闻传播学院",
        "url": "https://jc.nju.edu.cn",
        "faculty_url": "https://jc.nju.edu.cn/jzyg/zzjs.htm",
    },
    {
        "name": "体育部",
        "url": "https://tyb.nju.edu.cn",
        "faculty_url": "https://tyb.nju.edu.cn/jbgk/szdw/index.html",
    },
    {
        "name": "地理与海洋科学学院",
        "url": "https://sgos.nju.edu.cn",
        "faculty_url": "https://sgos.nju.edu.cn/62681/list.htm",
    },
    {
        "name": "大气科学学院",
        "url": "http://atmos.nju.edu.cn",
        "faculty_url": "http://atmos.nju.edu.cn/szdw/list.htm",
    },
    {
        "name": "环境学院",
        "url": "https://hjxy.nju.edu.cn",
        "faculty_url": "https://hjxy.nju.edu.cn/szdw/index.html",
    },
]

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
AT_PATTERN = re.compile(r"\s*\[at\]\s*|\s*\(at\)\s*|\s*#@\s*|\s*\[@\]\s*", re.IGNORECASE)


def extract_emails(text: str) -> list[str]:
    return list(set(EMAIL_PATTERN.findall(AT_PATTERN.sub("@", text))))


async def find_all_detail_links(page) -> list[dict]:
    """从页面找到教师详情页链接。"""
    result = await page.evaluate("""() => {
        const links = [];
        const seen = new Set();
        const navSet = new Set([
            '首页','概况','简介','领导','部门','制度','招聘','通知','公告','新闻',
            '动态','学术','科研','党建','团建','学生','招生','就业','合作','联系',
            '下载','办事','指南','登录','注册','中文','EN','加入','返回','更多',
            '查看','详情','关闭','确定','取消','MORE','more','首页','网站'
        ]);

        document.querySelectorAll('a').forEach(a => {
            const text = (a.textContent || '').trim();
            const href = (a.href || '').trim();
            if (!href || seen.has(href) || !text) return;
            if (href.startsWith('javascript:') || href.startsWith('#') || href.startsWith('mailto:')) return;
            if (/\\\\.(jpg|png|gif|pdf|doc|xls|ppt|rar|zip)$/i.test(href)) return;
            if (navSet.has(text)) return;

            if (/[\\u4e00-\\u9fff]/.test(text) && text.length <= 30) {
                seen.add(href);
                links.push({text, href});
            }
        });
        return links;
    }""")
    return result


async def scrape_detail(page, url: str, dept_name: str, default_name: str = "") -> dict:
    """抓取单个教师详情页。"""
    result = {"name": default_name, "email": "", "department": dept_name, "title": "", "url": url}

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(0.6)

        page_text = await page.evaluate("() => document.body?.innerText || ''")
        if not page_text:
            return result

        # 邮箱
        emails = extract_emails(page_text)
        if emails:
            nju = [e for e in emails if "nju.edu.cn" in e]
            result["email"] = nju[0] if nju else emails[0]

        # 姓名
        name = await page.evaluate("""() => {
            for (const sel of ['h1','h2','h3','.name','.title','[class*="name"]']) {
                const el = document.querySelector(sel);
                if (el) {
                    const t = el.textContent.trim();
                    const m = t.match(/[\\u4e00-\\u9fff]{2,4}/);
                    if (m && t.length <= 30) return t.split(/\\s|-|–|—|\\||｜/)[0].trim();
                }
            }
            const title = document.title || '';
            const parts = title.split(/[-–—|｜_\\s]+/);
            for (const p of parts) {
                if (/^[\\u4e00-\\u9fff]{2,3}$/.test(p.trim())) return p.trim();
            }
            return '';
        }""")
        if name and not result["name"]:
            result["name"] = name.strip()

        # 职称
        for line in page_text.split("\n"):
            line = line.strip()
            if len(line) > 50: continue
            for kw in ["教授","副教授","讲师","助理教授","研究员","副研究员","院士","博导","硕导","青年学者","特聘"]:
                if kw in line:
                    result["title"] = line
                    break
            if result["title"]: break

    except Exception:
        pass

    return result


async def scrape_dept(context, dept: dict) -> list[dict]:
    dept_name = dept["name"]
    faculty_url = dept["faculty_url"]
    results = []
    page = await context.new_page()

    try:
        logger.info(f"补抓: {dept_name} ({faculty_url})")

        await page.goto(faculty_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

        all_links = await find_all_detail_links(page)
        logger.info(f"{dept_name}: {len(all_links)} 个候选链接")

        # 筛选教师详情链接
        detail_links = []
        for link in all_links:
            href = link["href"]
            text = link["text"]
            # 教师详情页URL特征
            if re.search(r"/i\d+\.htm|/page\.htm|/c\d+.*\.htm|/\d{4,6}/\d{2}/c\d+", href):
                detail_links.append(link)
            elif re.match(r"^[一-鿿]{2,3}", text):
                detail_links.append(link)

        # 如果太少，不过滤
        if len(detail_links) < 5:
            detail_links = all_links

        logger.info(f"{dept_name}: {len(detail_links)} 个详情链接")
        seen_urls = set()
        for link in detail_links:
            href = link["href"]
            if href in seen_urls: continue
            seen_urls.add(href)

            text = link["text"]
            name = re.match(r"^([一-鿿]{2,3})", text)
            teacher_name = name.group(1) if name else text

            detail = await scrape_detail(page, href, dept_name, teacher_name)
            if not detail["name"]:
                detail["name"] = teacher_name
            results.append(detail)

    except Exception as e:
        logger.error(f"{dept_name}: {e}")
    finally:
        await page.close()

    return results


async def main():
    from playwright.async_api import async_playwright

    OUTPUT_DIR.mkdir(exist_ok=True)

    progress = {"completed": [], "all_results": []}
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            progress = json.load(f)

    completed = set(progress["completed"])
    all_results = progress["all_results"]
    pending = [d for d in ROUND3_DEPTS if d["name"] not in completed]

    logger.info(f"第三轮: {len(ROUND3_DEPTS)} 个院系, 待处理 {len(pending)}")

    if not pending:
        logger.info("全部完成!")
        return all_results

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        try:
            for dept in pending:
                dept_results = await scrape_dept(context, dept)
                all_results.extend(dept_results)
                completed.add(dept["name"])
                with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                    json.dump({"completed": list(completed), "all_results": all_results}, f, ensure_ascii=False, indent=2)
                logger.info(f"{dept['name']}: {len(dept_results)} 人 (累计 {len(all_results)})")
        finally:
            await browser.close()

    return all_results


if __name__ == "__main__":
    results = asyncio.run(main())
    if results:
        path = OUTPUT_DIR / "南京大学_教师名录_round3.xlsx"
        export_xlsx(results, "南京大学_教师名录_round3")
        logger.info(f"第三轮结果: {path}")
        logger.info(f"共 {len(results)} 条")
    else:
        logger.info("无新数据")
