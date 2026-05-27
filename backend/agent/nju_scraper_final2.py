"""南京大学最后一轮补抓 — 针对 JS 渲染页面和连接问题院系。"""

import asyncio, json, re, logging
from pathlib import Path

from agent.exporter import export_xlsx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "outputs"

# 最后的问题院系
FINAL_DEPTS = [
    # JS 渲染页面 — 尝试 networkidle
    ("哲学系", "https://philo.nju.edu.cn/szdw/list.htm"),
    ("艺术学院", "https://art.nju.edu.cn/szdw/list.htm"),
    ("现代工程与应用科学学院", "https://eng.nju.edu.cn/szdw/list.htm"),
    ("中美文化研究中心", "https://hnc.nju.edu.cn/szll.htm"),

    # 连接问题 — 尝试不同方式
    ("大气科学学院", "https://atmos.nju.edu.cn/szdw/list.htm"),
    ("大气科学学院_http", "http://atmos.nju.edu.cn/szdw/list.htm"),
    ("大气科学学院_root", "https://atmos.nju.edu.cn"),
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
AT_RE = re.compile(r"\s*\[at\]\s*|\s*\(at\)\s*|\s*#@\s*|\s*\[@\]\s*", re.IGNORECASE)

NOT_NAME = {
    "首页", "网站", "概况", "简介", "领导", "部门", "制度", "招聘", "通知", "公告",
    "新闻", "动态", "科研", "党建", "团建", "学生", "招生", "就业", "合作", "联系",
    "关于", "下载", "办事", "指南", "登录", "注册", "加入", "返回", "更多", "查看",
    "详情", "关闭", "确定", "取消", "中文", "英文", "教授", "副教授", "讲师",
    "博士后", "教研室", "实验室", "研究所", "中心", "学院", "大学", "师资", "队伍",
    "教师", "导师", "博士", "硕士", "研究生", "本科生",
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


def filter_teacher_links(raw_links):
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


async def collect_links_js(page):
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


async def collect_teacher_categories(page):
    return await page.evaluate("""() => {
        const links = [];
        const seen = new Set();
        const keywords = ['教授', '副教授', '讲师', '研究员', '副研究员',
                          '助理教授', '博士后', '博导', '硕导', '院士',
                          '在职', '退休', '荣休', '教师', '全部',
                          '师资', '导师', '队伍'];
        document.querySelectorAll('a').forEach(a => {
            const text = (a.textContent || '').trim();
            const href = (a.href || '').trim();
            if (!href || seen.has(href) || !text || text.length > 20) return;
            for (const kw of keywords) {
                if (text.includes(kw)) {
                    seen.add(href);
                    links.push({text, href});
                    break;
                }
            }
        });
        return links;
    }""")


async def scrape_detail(page, url, dept_name, default_name):
    result = {"name": default_name, "email": "", "department": dept_name, "title": "", "url": url}
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(0.5)
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


async def scrape_with_networkidle(browser, name, url):
    """对 JS 渲染页面使用 networkidle 策略。"""
    results = []
    context = await browser.new_context(viewport={"width": 1920, "height": 1080})
    page = await context.new_page()
    all_links = []

    try:
        logger.info(f"抓取({name}): networkidle 模式")
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
        except Exception as e:
            logger.warning(f"  {name}: networkidle 失败: {e}, 尝试 load")
            try:
                await page.goto(url, wait_until="load", timeout=30000)
            except Exception as e2:
                logger.warning(f"  {name}: load 也失败: {e2}")
                return results

        await asyncio.sleep(3)

        # 检查页面是否有足够的文字内容
        text_len = await page.evaluate("() => document.body?.innerText?.length || 0")
        logger.info(f"  {name}: 页面文字量 {text_len}")

        if text_len < 200:
            # 可能是空白页或骨架屏，尝试滚动触发懒加载
            for _ in range(5):
                await page.evaluate("() => window.scrollBy(0, 600)")
                await asyncio.sleep(1)
            text_len = await page.evaluate("() => document.body?.innerText?.length || 0")
            logger.info(f"  {name}: 滚动后文字量 {text_len}")

        raw = await collect_links_js(page)
        categories = await collect_teacher_categories(page)

        logger.info(f"  {name}: 链接 {len(raw)}, 分类 {len(categories)}")

        all_links.extend(raw)

        for cat in categories[:10]:
            try:
                await page.goto(cat["href"], wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)
                sub = await collect_links_js(page)
                logger.info(f"  {name}: 子「{cat['text']}」→ {len(sub)}")
                for l in sub:
                    if l["href"] not in {x["href"] for x in all_links}:
                        all_links.append(l)
            except Exception as e:
                logger.warning(f"  {name}: 子页面「{cat['text']}」失败: {e}")

        teacher_links = filter_teacher_links(all_links)
        logger.info(f"  {name}: 过滤后 {len(teacher_links)}")

        seen = set()
        unique = []
        for l in teacher_links:
            if l["href"] not in seen:
                seen.add(l["href"])
                unique.append(l)

        for i, link in enumerate(unique):
            nm = re.match(r"^([一-鿿]{2,4})", link["text"])
            teacher_name = nm.group(1) if nm else link["text"]
            try:
                detail = await scrape_detail(page, link["href"], name, teacher_name)
            except Exception:
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

    # 跳过大气科学学院的别名（如果主 URL 失败再用别名）
    normal_depts = [
        ("哲学系", "https://philo.nju.edu.cn/szdw/list.htm"),
        ("艺术学院", "https://art.nju.edu.cn/szdw/list.htm"),
        ("现代工程与应用科学学院", "https://eng.nju.edu.cn/szdw/list.htm"),
        ("中美文化研究中心", "https://hnc.nju.edu.cn/szll.htm"),
        ("大气科学学院", "https://atmos.nju.edu.cn/szdw/list.htm"),
    ]

    all_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        for name, url in normal_depts:
            dept_results = await scrape_with_networkidle(browser, name, url)
            all_results.extend(dept_results)
            logger.info(f"  {name}: {len(dept_results)} 人 (累计 {len(all_results)})")
            await asyncio.sleep(5)

        # 大气科学学院如果 https 失败，尝试 http
        atmos_results = [r for r in all_results if "大气" in r.get("department", "")]
        if not atmos_results:
            logger.info("尝试大气科学学院 http 协议...")
            atmos_results = await scrape_with_networkidle(
                browser, "大气科学学院", "http://atmos.nju.edu.cn/szdw/list.htm"
            )
            all_results.extend(atmos_results)
            logger.info(f"  大气科学学院(http): {len(atmos_results)} 人")

        await browser.close()

    if all_results:
        seen = set()
        deduped = []
        for r in all_results:
            key = (r["name"], r["email"], r["department"])
            if key not in seen:
                seen.add(key)
                deduped.append(r)

        path = export_xlsx(deduped, "南京大学_教师名录_最后补抓")
        emails = sum(1 for r in deduped if r["email"])
        depts = {}
        for r in deduped:
            d = r["department"]
            depts[d] = depts.get(d, 0) + 1

        logger.info(f"===== 最后补抓结果 =====")
        logger.info(f"总教师: {len(deduped)} | 邮箱: {emails} | 院系: {len(depts)}")
        for d, c in sorted(depts.items(), key=lambda x: -x[1]):
            logger.info(f"  {d}: {c}")
    else:
        logger.info("无新数据")


if __name__ == "__main__":
    asyncio.run(main())
