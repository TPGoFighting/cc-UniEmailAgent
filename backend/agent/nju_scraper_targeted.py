"""南京大学定向补抓 — 针对低覆盖/缺失院系。

策略：对每个院系使用多种链接发现策略，Python 层面过滤，逐个访问详情页。
"""

import asyncio, json, re, logging
from pathlib import Path

from agent.exporter import export_xlsx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
PROGRESS_FILE = OUTPUT_DIR / "nju_targeted_progress.json"

# 需要补抓的院系（低覆盖 + 缺失）
TARGET_DEPTS = [
    # === 缺失 (6) ===
    ("法学院", "https://law.nju.edu.cn/szdw/zzjs1/js.htm"),
    ("新闻传播学院", "https://jc.nju.edu.cn/jzyg/zzjs.htm"),
    ("马克思主义学院", "https://marxism.nju.edu.cn/szdw/list.htm"),
    ("信息管理学院", "https://im.nju.edu.cn/szdw/list.htm"),
    ("大气科学学院", "https://atmos.nju.edu.cn/szdw/list.htm"),
    ("工程管理学院", "https://sme.nju.edu.cn/2003/list.htm"),

    # === 低覆盖 (12) ===
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
    ("海外教育学院", "https://hwxy.nju.edu.cn/szdw/list.htm"),
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
AT_RE = re.compile(r"\s*\[at\]\s*|\s*\(at\)\s*|\s*#@\s*|\s*\[@\]\s*", re.IGNORECASE)

# 不是教师名的中文词
NOT_NAME = {
    "首页", "网站", "概况", "简介", "领导", "部门", "制度", "招聘", "通知", "公告",
    "新闻", "动态", "科研", "党建", "团建", "学生", "招生", "就业", "合作", "联系",
    "关于", "下载", "办事", "指南", "登录", "注册", "加入", "返回", "更多", "查看",
    "详情", "关闭", "确定", "取消", "中文", "英文", "教授", "副教授", "讲师",
    "博士后", "教研室", "实验室", "研究所", "中心", "学院", "大学", "师资", "队伍",
    "教师", "导师", "博士", "硕士", "研究生", "本科生", "教育", "教学", "培养",
    "科学研究", "学术", "交流", "合作", "国际", "版权所有", "友情链接", "校内链接",
    "人才培养", "科学研究", "社会服务", "文化传承", "国际合作", "校园文化",
    "校友", "基金会", "图书馆", "学报", "出版社", "医院", "附属", "珠海",
    "深圳", "苏州", "浦口", "鼓楼", "仙林",
}


def extract_emails(text):
    return list(set(EMAIL_RE.findall(AT_RE.sub("@", text))))


def looks_like_teacher_name(text):
    """判断文本是否以中文教师名开头。"""
    text = text.strip()
    if not text:
        return False
    # 中文名 2-4字开头（含 · 分隔的少数民族名）
    m = re.match(r"^([一-鿿]{2,4})", text)
    if not m:
        return False
    name_part = m.group(1)
    if name_part in NOT_NAME:
        return False
    # 排除纯导航短语
    if text in NOT_NAME:
        return False
    return True


def filter_teacher_links(raw_links: list[dict]) -> list[dict]:
    """Python 层面过滤教师链接。"""
    result = []
    seen = set()
    for link in raw_links:
        href = link.get("href", "").strip()
        text = link.get("text", "").strip()
        if not href or not text:
            continue
        if href in seen:
            continue
        # 排除非网页链接
        if any(href.startswith(p) for p in ("javascript:", "#", "mailto:", "tel:")):
            continue
        # 排除文件
        if re.search(r"\.(jpg|png|gif|pdf|doc|xls|ppt|rar|zip|mp4|avi)$", href, re.I):
            continue
        # 排除纯导航URL
        nav_segments = ["xygk", "rcpy", "zsjy", "xsyd", "dqjs", "xsgz", "hzjl",
                        "xyyfz", "login", "registe", "xswork", "djgz"]
        if any(s in href.lower() for s in nav_segments):
            continue
        # 文本需像人名
        if not looks_like_teacher_name(text):
            continue
        # 文本不能太长
        if len(text) > 50:
            continue
        seen.add(href)
        result.append(link)
    return result


async def collect_all_links(page) -> list[dict]:
    """策略1：从页面收集所有可能的教师链接。"""
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


async def collect_links_by_name_pattern(page) -> list[dict]:
    """策略2：只收集文本以中文名(2-3字)开头的链接。"""
    return await page.evaluate("""() => {
        const links = [];
        const seen = new Set();
        document.querySelectorAll('a').forEach(a => {
            const text = (a.textContent || '').trim();
            const href = (a.href || '').trim();
            if (!href || seen.has(href) || !text || text.length > 40) return;
            if (/^[\\u4e00-\\u9fff]{2,3}(\\s|\\d|[A-Z]|$)/.test(text)) {
                seen.add(href);
                links.push({text, href});
            }
        });
        return links;
    }""")


async def collect_links_by_url_pattern(page) -> list[dict]:
    """策略3：收集URL看起来像教师详情页的链接。"""
    return await page.evaluate("""() => {
        const links = [];
        const seen = new Set();
        document.querySelectorAll('a').forEach(a => {
            const text = (a.textContent || '').trim();
            const href = (a.href || '').trim();
            if (!href || seen.has(href) || !text) return;
            // 教师详情URL特征
            if (/\\/info\\/\\d+\\/\\d+\\.htm/i.test(href) ||
                /\\/i\\d+\\.htm/i.test(href) ||
                /\\/page\\.htm/i.test(href) ||
                /\\/c\\d+.*\\.htm/i.test(href)) {
                seen.add(href);
                links.push({text, href});
            }
        });
        return links;
    }""")


async def collect_teacher_list_links(page) -> list[dict]:
    """策略4：查找指向教师子分类页面的链接（如 教授/副教授/讲师 列表页）。"""
    return await page.evaluate("""() => {
        const links = [];
        const seen = new Set();
        const keywords = ['教授', '副教授', '讲师', '研究员', '副研究员',
                          '助理教授', '博士后', '博导', '硕导', '院士',
                          '在职', '退休', '荣休', '教师', '全部'];
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


async def find_iframe_src(page) -> list[str]:
    """策略5：查找页面中的 iframe，有些院系用 iframe 嵌入教师列表。"""
    return await page.evaluate("""() => {
        const srcs = [];
        document.querySelectorAll('iframe').forEach(f => {
            const src = (f.src || '').trim();
            if (src) srcs.push(src);
        });
        return srcs;
    }""")


async def scrape_detail(page, url: str, dept_name: str, default_name: str) -> dict:
    """访问教师详情页，提取姓名、邮箱、职称。"""
    result = {"name": default_name, "email": "", "department": dept_name, "title": "", "url": url}

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(0.5)

        page_text = await page.evaluate("() => document.body?.innerText || ''")
        if not page_text:
            return result

        # 邮箱
        emails = extract_emails(page_text)
        if emails:
            nju = [e for e in emails if "nju.edu.cn" in e]
            result["email"] = nju[0] if nju else emails[0]

        # 姓名（从页面标题/标题元素获取）
        name_from_page = await page.evaluate("""() => {
            for (const sel of ['h1','h2','h3','.name','.title','[class*="name"]','[class*="title"]']) {
                const el = document.querySelector(sel);
                if (el) {
                    const t = el.textContent.trim();
                    const m = t.match(/[\\u4e00-\\u9fff]{2,4}/);
                    if (m && t.length <= 40) return t.split(/\\s|-|–|—|\\||｜|：|:/)[0].trim();
                }
            }
            // 尝试从 document.title 提取
            const parts = (document.title || '').split(/[-–—|｜_\\s]+/);
            for (const p of parts) {
                if (/^[\\u4e00-\\u9fff]{2,3}$/.test(p.trim())) return p.trim();
            }
            return '';
        }""")
        if name_from_page:
            result["name"] = name_from_page.strip()

        # 职称
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


async def scrape_dept(context, name: str, url: str) -> list[dict]:
    """抓取单个院系（多策略）。"""
    results = []
    page = await context.new_page()
    all_links = []

    try:
        logger.info(f"抓取: {name}")

        # 访问师资页面
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"  {name}: 主页访问失败: {e}")
            await page.close()
            return results

        # 策略1：收集所有链接，Python层过滤
        raw_links = await collect_all_links(page)
        logger.info(f"  {name}: 策略1(全量) → {len(raw_links)} 个链接")

        # 策略2：中文名开头链接
        name_links = await collect_links_by_name_pattern(page)
        logger.info(f"  {name}: 策略2(中文名) → {len(name_links)} 个链接")

        # 策略3：URL模式匹配
        url_links = await collect_links_by_url_pattern(page)
        logger.info(f"  {name}: 策略3(URL模式) → {len(url_links)} 个链接")

        # 策略4：教师分类子页面
        category_links = await collect_teacher_list_links(page)
        logger.info(f"  {name}: 策略4(分类页) → {len(category_links)} 个链接")

        # 策略5：iframe
        iframes = await find_iframe_src(page)
        logger.info(f"  {name}: 策略5(iframe) → {len(iframes)} 个")

        # 合并策略1和2（策略3的URL模式太宽泛，先不用）
        combined = {l["href"]: l for l in (raw_links + name_links) if l["href"]}.values()
        all_links = list(combined)

        # 访问子分类页面获取更多教师链接
        for cat_link in category_links:
            try:
                await page.goto(cat_link["href"], wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(1.5)
                sub_raw = await collect_all_links(page)
                sub_name = await collect_links_by_name_pattern(page)
                logger.info(f"  {name}: 子页面「{cat_link['text']}」→ {len(sub_raw)} 原始, {len(sub_name)} 中文名")
                for l in sub_raw + sub_name:
                    if l["href"] and l["href"] not in {x["href"] for x in all_links}:
                        all_links.append(l)
            except Exception as e:
                logger.warning(f"  {name}: 子页面 {cat_link['text']} 访问失败: {e}")

        # 访问 iframe 中的页面
        for src in iframes:
            try:
                await page.goto(src, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(1.5)
                sub_raw = await collect_all_links(page)
                sub_name = await collect_links_by_name_pattern(page)
                logger.info(f"  {name}: iframe → {len(sub_raw)} 原始, {len(sub_name)} 中文名")
                for l in sub_raw + sub_name:
                    if l["href"] and l["href"] not in {x["href"] for x in all_links}:
                        all_links.append(l)
            except Exception as e:
                logger.warning(f"  {name}: iframe {src} 访问失败: {e}")

        # Python 层面过滤
        teacher_links = filter_teacher_links(all_links)
        logger.info(f"  {name}: 过滤后 → {len(teacher_links)} 个教师链接")

        # 逐个访问教师详情页
        seen_urls = set()
        for i, link in enumerate(teacher_links):
            href = link["href"]
            if href in seen_urls:
                continue
            seen_urls.add(href)

            text = link["text"]
            nm = re.match(r"^([一-鿿]{2,4})", text)
            teacher_name = nm.group(1) if nm else text

            logger.debug(f"  {name}: [{i+1}/{len(teacher_links)}] {teacher_name}")
            detail = await scrape_detail(page, href, name, teacher_name)
            if not detail["name"]:
                detail["name"] = teacher_name
            results.append(detail)

    except Exception as e:
        logger.error(f"  {name}: 抓取出错: {e}")
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
    pending = [(n, u) for n, u in TARGET_DEPTS if n not in completed]

    logger.info(f"定向补抓: {len(TARGET_DEPTS)} 个院系, 已完成 {len(completed)}, 待处理 {len(pending)}")

    if not pending:
        logger.info("全部完成!")
        if all_results:
            _export_results(all_results)
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})

        try:
            for i, (name, url) in enumerate(pending):
                logger.info(f"[{i+1}/{len(pending)}] {name}")
                dept_results = await scrape_dept(context, name, url)
                all_results.extend(dept_results)
                completed.add(name)

                with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                    json.dump({
                        "completed": list(completed),
                        "all_results": all_results
                    }, f, ensure_ascii=False)

                logger.info(f"  {name}: {len(dept_results)} 人 (累计 {len(all_results)})")
                await asyncio.sleep(0.5)
        finally:
            await browser.close()

    if all_results:
        _export_results(all_results)
    PROGRESS_FILE.unlink(missing_ok=True)


def _export_results(results: list[dict]):
    seen = set()
    deduped = []
    for r in results:
        key = (r["name"], r["email"], r["department"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    path = export_xlsx(deduped, "南京大学_教师名录_定向补抓")
    emails = sum(1 for r in deduped if r["email"])
    titles = sum(1 for r in deduped if r["title"])
    depts = {}
    for r in deduped:
        d = r["department"]
        depts[d] = depts.get(d, 0) + 1

    logger.info(f"===== 定向补抓结果 =====")
    logger.info(f"总教师: {len(deduped)} | 邮箱: {emails} | 职称: {titles} | 院系: {len(depts)}")
    for d, c in sorted(depts.items(), key=lambda x: -x[1]):
        logger.info(f"  {d}: {c}")
    return path


if __name__ == "__main__":
    asyncio.run(main())
