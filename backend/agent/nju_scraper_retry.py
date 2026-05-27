"""南京大学定向补抓 — 重试被限流的院系。

核心改进：
1. 每个院系使用独立浏览器上下文
2. 请求间隔更长
3. 等待网络空闲再收集链接
4. 自动重试
"""

import asyncio, json, re, logging
from pathlib import Path

from agent.exporter import export_xlsx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
PROGRESS_FILE = OUTPUT_DIR / "nju_retry_progress.json"

# 需要重试的院系
RETRY_DEPTS = [
    # 0 链接的
    ("马克思主义学院", "https://marxism.nju.edu.cn/szdw/list.htm"),
    ("信息管理学院", "https://im.nju.edu.cn/szdw/list.htm"),

    # 连接被限的
    ("哲学系", "https://philo.nju.edu.cn/szdw/list.htm"),
    ("商学院", "https://nubs.nju.edu.cn/8878/list.htm"),
    ("社会学院", "https://sociology.nju.edu.cn/szdw/list.htm"),
    ("艺术学院", "https://art.nju.edu.cn/szdw/list.htm"),
    ("软件学院", "https://software.nju.edu.cn/szll/szdw/index.html"),
    ("现代工程与应用科学学院", "https://eng.nju.edu.cn/szdw/list.htm"),
    ("数字经济与管理学院", "https://sdem.nju.edu.cn/59579/list.htm"),
    ("环境学院", "https://hjxy.nju.edu.cn/szdw/index.html"),
    ("体育部", "https://tyb.nju.edu.cn/jbgk/szdw/index.html"),
    ("生命科学学院", "https://life.nju.edu.cn/szdw/list.htm"),
    ("匡亚明学院", "https://dii.nju.edu.cn/lsjs/list.htm"),

    # 连接关闭的（尝试 http 协议或不带路径）
    ("大气科学学院", "https://atmos.nju.edu.cn/szdw/list.htm"),

    # 第一次只拿到 24 人但可能是我们漏了（子页面已抓了）
    # 新闻传播学院 已抓取，跳过
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
AT_RE = re.compile(r"\s*\[at\]\s*|\s*\(at\)\s*|\s*#@\s*|\s*\[@\]\s*", re.IGNORECASE)

NOT_NAME = {
    "首页", "网站", "概况", "简介", "领导", "部门", "制度", "招聘", "通知", "公告",
    "新闻", "动态", "科研", "党建", "团建", "学生", "招生", "就业", "合作", "联系",
    "关于", "下载", "办事", "指南", "登录", "注册", "加入", "返回", "更多", "查看",
    "详情", "关闭", "确定", "取消", "中文", "英文", "教授", "副教授", "讲师",
    "博士后", "教研室", "实验室", "研究所", "中心", "学院", "大学", "师资", "队伍",
    "教师", "导师", "博士", "硕士", "研究生", "本科生", "教育", "教学", "培养",
    "科学研究", "学术", "交流", "合作", "国际", "版权所有", "友情链接", "校内链接",
    "人才培养", "社会服务", "文化传承", "国际合作", "校园文化",
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


def filter_teacher_links(raw_links: list[dict]) -> list[dict]:
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
        nav_segments = ["xygk", "rcpy", "zsjy", "xsyd", "dqjs", "xsgz", "hzjl",
                        "xyyfz", "login", "registe", "xswork", "djgz"]
        if any(s in href.lower() for s in nav_segments):
            continue
        if not looks_like_teacher_name(text):
            continue
        if len(text) > 50:
            continue
        seen.add(href)
        result.append(link)
    return result


async def wait_for_content(page, timeout=15):
    """等待页面有实际内容加载。"""
    try:
        await page.wait_for_function(
            "() => document.body && document.body.innerText && document.body.innerText.length > 100",
            timeout=timeout * 1000
        )
        return True
    except Exception:
        return False


async def collect_links_js(page) -> list[dict]:
    """使用 JS 收集所有链接。"""
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


async def collect_teacher_categories(page) -> list[dict]:
    """收集教师分类子页面链接。"""
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


async def scrape_detail(page, url: str, dept_name: str, default_name: str) -> dict:
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


async def scrape_dept(browser, name: str, url: str) -> list[dict]:
    """抓取单个院系，使用独立的 context。"""
    results = []
    context = await browser.new_context(viewport={"width": 1920, "height": 1080})
    page = await context.new_page()
    all_links = []

    try:
        logger.info(f"抓取: {name}")

        # 尝试访问，带重试
        for attempt in range(3):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                break
            except Exception as e:
                logger.warning(f"  {name}: 第{attempt+1}次访问失败: {e}")
                if attempt < 2:
                    await asyncio.sleep(5)
                else:
                    raise

        # 等待页面内容加载
        await asyncio.sleep(3)
        has_content = await wait_for_content(page, timeout=10)
        if not has_content:
            logger.warning(f"  {name}: 页面内容为空，可能需 JS 渲染")
        await asyncio.sleep(2)

        # 收集链接
        raw = await collect_links_js(page)
        logger.info(f"  {name}: 全量链接 → {len(raw)}")

        # 如果链接少，尝试滚动触发懒加载
        if len(raw) < 20:
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            raw = await collect_links_js(page)
            logger.info(f"  {name}: 滚动后链接 → {len(raw)}")

        # 收集子分类
        categories = await collect_teacher_categories(page)
        logger.info(f"  {name}: 分类页 → {len(categories)}")

        all_links.extend(raw)

        # 访问子分类页面
        for cat in categories[:10]:  # 限制最多10个子页面
            try:
                await page.goto(cat["href"], wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)
                sub_raw = await collect_links_js(page)
                logger.info(f"  {name}: 子「{cat['text']}」→ {len(sub_raw)}")
                for l in sub_raw:
                    if l["href"] not in {x["href"] for x in all_links}:
                        all_links.append(l)
            except Exception as e:
                logger.warning(f"  {name}: 子页面「{cat['text']}」失败: {e}")

        # 过滤
        teacher_links = filter_teacher_links(all_links)
        logger.info(f"  {name}: 过滤后 → {len(teacher_links)}")

        # 去重
        seen = {}
        unique_links = []
        for l in teacher_links:
            if l["href"] not in seen:
                seen[l["href"]] = l
                unique_links.append(l)
        teacher_links = unique_links

        # 逐个抓取详情
        for i, link in enumerate(teacher_links):
            nm = re.match(r"^([一-鿿]{2,4})", link["text"])
            teacher_name = nm.group(1) if nm else link["text"]

            try:
                detail = await scrape_detail(page, link["href"], name, teacher_name)
            except Exception:
                detail = {"name": teacher_name, "email": "", "department": name, "title": "", "url": link["href"]}

            if not detail["name"]:
                detail["name"] = teacher_name
            results.append(detail)

            if (i + 1) % 20 == 0:
                logger.info(f"  {name}: [{i+1}/{len(teacher_links)}]")

    except Exception as e:
        logger.error(f"  {name}: 整体失败: {e}")
    finally:
        await page.close()
        await context.close()

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
    pending = [(n, u) for n, u in RETRY_DEPTS if n not in completed]

    logger.info(f"重试: {len(RETRY_DEPTS)} 个院系, 已完成 {len(completed)}, 待处理 {len(pending)}")

    if not pending:
        logger.info("全部完成!")
        if all_results:
            _finish(all_results)
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        try:
            for i, (name, url) in enumerate(pending):
                logger.info(f"[{i+1}/{len(pending)}] {name}")
                dept_results = await scrape_dept(browser, name, url)
                all_results.extend(dept_results)
                completed.add(name)

                with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                    json.dump({
                        "completed": list(completed),
                        "all_results": all_results
                    }, f, ensure_ascii=False)

                logger.info(f"  {name}: {len(dept_results)} 人 (累计 {len(all_results)})")
                # 关键：每个院系之间等待 8-12 秒，避免被限流
                delay = 8 + (i % 5) * 2
                logger.info(f"  等待 {delay}s ...")
                await asyncio.sleep(delay)
        finally:
            await browser.close()

    if all_results:
        _finish(all_results)
    PROGRESS_FILE.unlink(missing_ok=True)


def _finish(results: list[dict]):
    seen = set()
    deduped = []
    for r in results:
        key = (r["name"], r["email"], r["department"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    path = export_xlsx(deduped, "南京大学_教师名录_重试补抓")
    emails = sum(1 for r in deduped if r["email"])
    titles = sum(1 for r in deduped if r["title"])
    depts = {}
    for r in deduped:
        d = r["department"]
        depts[d] = depts.get(d, 0) + 1

    logger.info(f"===== 重试结果 =====")
    logger.info(f"总教师: {len(deduped)} | 邮箱: {emails} | 职称: {titles} | 院系: {len(depts)}")
    for d, c in sorted(depts.items(), key=lambda x: -x[1]):
        logger.info(f"  {d}: {c}")
    return path


if __name__ == "__main__":
    asyncio.run(main())
