"""南京大学最终补抓 — 使用正确的院系 URL。"""

import asyncio, re, logging
from pathlib import Path

from agent.exporter import export_xlsx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "outputs"

# 使用正确 URL 的院系配置
DEPT_CONFIGS = [
    {
        "name": "哲学系",
        "urls": [
            "https://philo.nju.edu.cn/4712/list.htm",  # 在职教师
            "https://philo.nju.edu.cn/4713/list.htm",  # 离退休教师
            "https://philo.nju.edu.cn/gxkjs/list.htm",  # 各学科教师
        ],
    },
    {
        "name": "艺术学院",
        "urls": [
            "https://art.nju.edu.cn/zzjs/list.htm",  # 在职教师
            "https://art.nju.edu.cn/jzjs/list.htm",  # 兼职教师
            "https://art.nju.edu.cn/rxry/list.htm",  # 荣休人员
        ],
    },
    {
        "name": "现代工程与应用科学学院",
        "urls": [
            "https://eng.nju.edu.cn/zrjswyjxlwhbshwzp/list.htm",  # 专任教师
            "https://eng.nju.edu.cn/yjxlwhbshw/list.htm",  # 研究系列
            "https://eng.nju.edu.cn/cxtd/list.htm",  # 创新团队
            "https://eng.nju.edu.cn/43271/list.htm",  # 荣休教师
            "https://eng.nju.edu.cn/yjsds/list.htm",  # 研究生导师
        ],
    },
    # 大气科学学院 — 尝试找正确URL
    {
        "name": "大气科学学院",
        "urls": [
            "https://atmos.nju.edu.cn",
        ],
    },
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
AT_RE = re.compile(r"\s*\[at\]\s*|\s*\(at\)\s*|\s*#@\s*|\s*\[@\]\s*", re.IGNORECASE)

NOT_NAME = {
    "首页", "网站", "概况", "简介", "领导", "部门", "制度", "招聘", "通知", "公告",
    "新闻", "动态", "科研", "党建", "团建", "学生", "招生", "就业", "合作", "联系",
    "关于", "下载", "办事", "指南", "登录", "注册", "加入", "返回", "更多", "查看",
    "详情", "关闭", "确定", "取消", "中文", "英文",
    "博士后", "教研室", "实验室", "研究所", "中心", "学院", "大学",
    "科学研究", "学术", "交流", "国际", "版权所有", "友情链接",
    "人才培养", "科学研究", "社会服务", "文化传承", "国际合作",
    "校友", "基金会", "图书馆", "学报", "出版社", "医院", "附属",
}


def extract_emails(text):
    return list(set(EMAIL_RE.findall(AT_RE.sub("@", text))))


def looks_like_teacher_name(text):
    text = text.strip()
    if not text:
        return False
    m = re.match(r"^([一-鿿]{2,4})", text)
    if not m:
        return False
    if m.group(1) in NOT_NAME:
        return False
    if text in NOT_NAME:
        return False
    return True


def filter_links(raw_links):
    result = []
    seen = set()
    for link in raw_links:
        href = link.get("href", "").strip()
        text = link.get("text", "").strip()
        if not href or not text:
            continue
        if href in seen:
            continue
        if any(href.startswith(p) for p in ("javascript:", "#", "mailto:", "tel:")):
            continue
        if re.search(r"\.(jpg|png|gif|pdf|doc|xls|ppt|rar|zip|mp4|avi)$", href, re.I):
            continue
        if not looks_like_teacher_name(text):
            continue
        if len(text) > 50:
            continue
        seen.add(href)
        result.append(link)
    return result


async def collect_all(page):
    return await page.evaluate("""() => {
        const links = [];
        const seen = new Set();
        document.querySelectorAll('a').forEach(a => {
            const text = (a.textContent || '').trim();
            const href = (a.href || '').trim();
            if (!href || seen.has(href) || !text) return;
            seen.add(href);
            links.push({text, href});
        });
        return links;
    }""")


async def scrape_detail(page, url, dept_name, default_name):
    result = {"name": default_name, "email": "", "department": dept_name, "title": "", "url": url}
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(0.4)
        page_text = await page.evaluate("() => document.body?.innerText || ''")
        if not page_text:
            return result

        emails = extract_emails(page_text)
        if emails:
            nju = [e for e in emails if "nju.edu.cn" in e]
            result["email"] = nju[0] if nju else emails[0]

        name_from_page = await page.evaluate("""() => {
            for (const sel of ['h1','h2','h3','.name','.title','[class*="name"]','[class*="title"]']) {
                const el = document.querySelector(sel);
                if (el) {
                    const t = el.textContent.trim();
                    const m = t.match(/[\\u4e00-\\u9fff]{2,4}/);
                    if (m && t.length <= 40) return t.split(/\\s|-|–|—|\\||｜|：|:/)[0].trim();
                }
            }
            const parts = (document.title || '').split(/[-–—|｜_\\s]+/);
            for (const p of parts) {
                if (/^[\\u4e00-\\u9fff]{2,3}$/.test(p.trim())) return p.trim();
            }
            return '';
        }""")
        if name_from_page:
            result["name"] = name_from_page.strip()

        for line in page_text.split("\n"):
            line = line.strip()
            if len(line) > 60:
                continue
            for kw in ["教授", "副教授", "讲师", "助理教授", "研究员", "副研究员",
                        "院士", "博导", "青年学者", "特聘", "高级工程师", "工程师"]:
                if kw in line:
                    result["title"] = line
                    break
            if result["title"]:
                break
    except Exception:
        pass
    return result


async def scrape_dept(browser, config):
    name = config["name"]
    urls = config["urls"]
    results = []
    all_links = []
    seen_hrefs = set()

    context = await browser.new_context(viewport={"width": 1920, "height": 1080})
    page = await context.new_page()

    try:
        logger.info(f"抓取: {name} ({len(urls)} 个页面)")

        for url in urls:
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
            except:
                try:
                    await page.goto(url, wait_until="load", timeout=30000)
                except Exception as e:
                    logger.warning(f"  {name}: {url} 访问失败: {e}")
                    continue

            await asyncio.sleep(2)

            # 滚动触发懒加载
            for _ in range(3):
                await page.evaluate("() => window.scrollBy(0, 800)")
                await asyncio.sleep(0.5)

            raw = await collect_all(page)
            logger.info(f"  {name}: {url} → {len(raw)} 链接")

            for l in raw:
                if l["href"] not in seen_hrefs:
                    seen_hrefs.add(l["href"])
                    all_links.append(l)

        # 过滤
        teacher_links = filter_links(all_links)
        logger.info(f"  {name}: 过滤后 → {len(teacher_links)}")

        # 对于大气科学学院，如果主页连不上，先尝试找正确URL
        if name == "大气科学学院" and len(teacher_links) == 0:
            logger.warning(f"  {name}: 无法访问，跳过")
            return results

        # 去重
        seen = {}
        unique = []
        for l in teacher_links:
            if l["href"] not in seen:
                seen[l["href"]] = l
                unique.append(l)

        for i, link in enumerate(unique):
            nm = re.match(r"^([一-鿿]{2,4})", link["text"])
            teacher_name = nm.group(1) if nm else link["text"]
            try:
                detail = await scrape_detail(page, link["href"], name, teacher_name)
            except:
                detail = {"name": teacher_name, "email": "", "department": name, "title": "", "url": link["href"]}
            if not detail["name"]:
                detail["name"] = teacher_name
            results.append(detail)

            if (i + 1) % 30 == 0:
                logger.info(f"  {name}: [{i+1}/{len(unique)}]")

    except Exception as e:
        logger.error(f"  {name}: 整体失败: {e}")
    finally:
        await page.close()
        await context.close()

    return results


async def main():
    from playwright.async_api import async_playwright

    OUTPUT_DIR.mkdir(exist_ok=True)
    all_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        for config in DEPT_CONFIGS:
            dept_results = await scrape_dept(browser, config)
            all_results.extend(dept_results)
            logger.info(f"  {config['name']}: {len(dept_results)} 人 (累计 {len(all_results)})")
            await asyncio.sleep(5)

        await browser.close()

    if all_results:
        seen = set()
        deduped = []
        for r in all_results:
            key = (r["name"], r["email"], r["department"])
            if key not in seen:
                seen.add(key)
                deduped.append(r)

        path = export_xlsx(deduped, "南京大学_教师名录_最终补抓3")
        emails = sum(1 for r in deduped if r["email"])
        titles = sum(1 for r in deduped if r["title"])
        depts = {}
        for r in deduped:
            d = r["department"]
            depts[d] = depts.get(d, 0) + 1

        logger.info(f"===== 最终补抓3结果 =====")
        logger.info(f"总教师: {len(deduped)} | 邮箱: {emails} | 职称: {titles} | 院系: {len(depts)}")
        for d, c in sorted(depts.items(), key=lambda x: -x[1]):
            logger.info(f"  {d}: {c}")
    else:
        logger.info("无新数据")


if __name__ == "__main__":
    asyncio.run(main())
