"""南京大学计算机学院 — 教师邮箱专用爬虫 v2。

NJU CS 网站结构：
- 列表页：教师名在 <span class="Article_Title"> 内，被 <a> 包裹
- 文本格式："姓名 (职称/博导等)"
- 详情页 URL 格式：https://cs.nju.edu.cn/58/2a/c2639a153642/page.htm
"""

import asyncio
import logging
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("请先安装 playwright: pip install playwright && playwright install chromium")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"
TASK_ID = "bbda6fb3-ebad-49a5-a56d-d887b93ce0ef"
TASK_DIR = OUTPUT_DIR / TASK_ID

BASE_URL = "https://cs.nju.edu.cn"
DEPT_NAME = "计算机科学与技术系"

# NJU CS 所有教师分类页面
CATEGORY_URLS = [
    ("教授", "https://cs.nju.edu.cn/2639/list.htm"),
    ("副教授", "https://cs.nju.edu.cn/2640/list.htm"),
    ("准长聘", "https://cs.nju.edu.cn/zzp/list.htm"),
    ("跨学科博导", "https://cs.nju.edu.cn/kxkbd/list.htm"),
    ("讲师、专职科研、博士后", "https://cs.nju.edu.cn/2641/list.htm"),
    ("高级工程师", "https://cs.nju.edu.cn/2642/list.htm"),
    ("专业技术人员", "https://cs.nju.edu.cn/2643/list.htm"),
    ("离退休人员", "https://cs.nju.edu.cn/2645/list.htm"),
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
AT_RE = re.compile(r"\s*\[at\]\s*|\s*\(at\)\s*|\s*#@\s*|\s*\[@\]\s*", re.IGNORECASE)


def extract_emails(text: str) -> list[str]:
    return list(set(EMAIL_RE.findall(AT_RE.sub("@", text))))


def extract_name_and_title(text: str) -> tuple[str, str]:
    """从「姓名 (职称)」→ (姓名, 职称)"""
    text = text.strip()
    # 匹配：中文名 + 空格/括号 + 内容
    m = re.match(r"^([一-鿿]{2,4})\s*[（(]([^)）]+)[）)]", text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # 纯姓名（无括号）
    m = re.match(r"^([一-鿿]{2,4})\s*$", text)
    if m:
        return m.group(1).strip(), ""
    # 姓名+空格+职称（无括号）
    m = re.match(r"^([一-鿿]{2,4})\s+(.+)$", text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", ""


async def collect_teacher_links(page) -> list[dict]:
    """从列表页收集教师姓名链接。NJU CS 特定格式。"""
    return await page.evaluate("""() => {
        const results = [];
        const seen = new Set();

        // Article_Title span 内的 <a> 为教师详情链接
        document.querySelectorAll('.Article_Title').forEach(span => {
            const a = span.querySelector('a') || span.closest('a');
            if (!a || !a.href) return;

            const text = span.textContent.trim();
            const href = a.href;

            if (!text || !href || seen.has(href)) return;
            if (href.startsWith('javascript:') || href.startsWith('mailto:')) return;
            if (!/^[\\u4e00-\\u9fff]{2,4}/.test(text)) return;

            seen.add(href);
            results.push({text: text, href: href});
        });

        return results;
    }""")


async def scrape_detail(page, url: str, dept: str, default_name: str, cat_title: str) -> dict:
    """抓取单个教师详情页。"""
    result = {
        "name": default_name,
        "email": "",
        "department": dept,
        "title": cat_title,  # 默认使用分类页上的职称
        "url": url,
    }

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(0.3)
        page_text = await page.evaluate("() => document.body?.innerText || ''")
        if not page_text:
            return result

        # 提取邮箱
        emails = extract_emails(page_text)
        if emails:
            nju = [e for e in emails if "nju.edu.cn" in e.lower()]
            public_pfx = ["webmaster", "admin", "info@", "office@", "cs@nju",
                          "js@", "szdw@", "jsh@", "zx@", "xy@", "bgs@"]
            clean = [e for e in nju if not any(p in e.lower() for p in public_pfx)]
            result["email"] = clean[0] if clean else (nju[0] if nju else emails[0])

        # 从页面提取姓名
        name = await page.evaluate("""() => {
            for (const sel of ['h1', 'h2', 'h3', '.name', '.title',
                '[class*="name"]', '[class*="title"]', '.Article_Title']) {
                const el = document.querySelector(sel);
                if (el) {
                    const t = el.textContent.trim();
                    // "吕建 (院士、博导)" → "吕建"
                    const m = t.match(/^([\\u4e00-\\u9fff]{2,4})/);
                    if (m && t.length <= 40) {
                        return m[1];
                    }
                }
            }
            const parts = (document.title || '').split(/[-–—|｜_\\s]+/);
            for (const p of parts) {
                if (/^[\\u4e00-\\u9fff]{2,3}$/.test(p.trim())) return p.trim();
            }
            return '';
        }""")
        if name:
            result["name"] = name.strip()

        # 从详情页提取职称（覆盖分类页的职称）
        title_keywords = [
            "教授", "副教授", "助理教授", "讲师",
            "研究员", "副研究员", "高级工程师", "工程师",
            "院士", "博导", "硕导", "长江学者",
            "杰出青年", "优秀青年", "青年学者", "特聘",
            "千人计划", "万人计划",
            "系主任", "副系主任", "副院长", "院长",
            "IEEE Fellow", "ACM Fellow", "CCF Fellow",
            "博士生导师", "硕士生导师",
        ]
        for line in page_text.split("\n"):
            line = line.strip()
            if len(line) > 80:
                continue
            for kw in title_keywords:
                if kw in line:
                    # 合并职称信息
                    if result["title"] and result["title"] != cat_title:
                        if kw not in result["title"]:
                            result["title"] = result["title"] + "、" + line
                    else:
                        result["title"] = line
                    break

        # 清理职称
        if result["title"]:
            result["title"] = result["title"].replace("\n", " ").strip()[:60]

    except Exception as e:
        logger.debug(f"详情页失败 {url[-60:]}: {e}")

    return result


async def scrape_category(page, cat_name: str, cat_url: str) -> list[dict]:
    """抓取一个分类页面下的所有教师。"""
    results = []
    logger.info(f"  [{cat_name}] 访问 {cat_url}")

    try:
        await page.goto(cat_url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(1.5)

        # 滚动触发懒加载
        for _ in range(3):
            await page.evaluate("() => window.scrollBy(0, 800)")
            await asyncio.sleep(0.3)

        # 收集教师链接
        links = await collect_teacher_links(page)
        logger.info(f"  [{cat_name}] 找到 {len(links)} 位教师")

        for i, link in enumerate(links):
            # 从链接文本中提取姓名和职称
            name, title_from_list = extract_name_and_title(link["text"])
            if not name:
                name = link["text"][:4]

            # 职称优先用分类页中提取的
            title = title_from_list if title_from_list else cat_name

            # 访问详情页
            detail = await scrape_detail(page, link["href"], DEPT_NAME, name, title)
            if not detail["name"]:
                detail["name"] = name
            if not detail.get("title") or detail["title"] == cat_name:
                detail["title"] = title if title else cat_name

            results.append(detail)

            if (i + 1) % 20 == 0:
                has_email = sum(1 for r in results if r["email"])
                logger.info(f"  [{cat_name}] 进度 {i+1}/{len(links)}, 邮箱 {has_email}")

    except Exception as e:
        logger.error(f"  [{cat_name}] 分类页失败: {e}")

    return results


async def main():
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"输出目录: {TASK_DIR}")
    logger.info(f"目标: {DEPT_NAME}")
    logger.info(f"分类页面: {len(CATEGORY_URLS)} 个")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            ignore_https_errors=True,
        )
        page = await context.new_page()

        all_results = []

        for cat_name, cat_url in CATEGORY_URLS:
            cat_results = await scrape_category(page, cat_name, cat_url)
            all_results.extend(cat_results)
            has_email = sum(1 for r in cat_results if r["email"])
            logger.info(f"  [{cat_name}] 完成: {len(cat_results)} 人, {has_email} 有邮箱 (累计 {len(all_results)})")
            await asyncio.sleep(1)

        await browser.close()

    # ============================================================
    # 后处理
    # ============================================================
    logger.info(f"\n===== 数据清洗 =====")
    logger.info(f"原始记录: {len(all_results)}")

    # 去重（按姓名+详情页URL）
    seen = set()
    deduped = []
    for r in all_results:
        key = (r["name"], r["url"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    # 排除无效姓名
    clean = []
    not_names = {"首页", "师资队伍", "教授", "副教授", "讲师", "研究员",
                  "学院概况", "通知公告", "新闻动态", "科研工作", "人才培养"}
    for r in deduped:
        name = r.get("name", "").strip()
        if len(name) < 2 or name in not_names:
            continue
        if not re.match(r"^[一-鿿]{2,4}$", name):
            # 包含英文名或特殊字符的不算，但保留有邮箱的
            if not r.get("email"):
                continue
        # 过滤公共邮箱
        email = r.get("email", "").lower()
        public_emails = ["webmaster", "admin@cs", "info@cs", "office@cs",
                         "js@cs", "szdw@cs", "cs@nju", "bgs@"]
        if email and any(p in email for p in public_emails):
            r["email"] = ""
        clean.append(r)

    # 按姓名排序
    clean.sort(key=lambda x: x.get("name", ""))

    # 统计
    has_email = sum(1 for r in clean if r["email"])
    has_title = sum(1 for r in clean if r["title"])

    logger.info(f"去重清洗后: {len(clean)}")
    logger.info(f"有邮箱: {has_email}")
    logger.info(f"有职称: {has_title}")

    # 展示部分结果
    for r in clean[:15]:
        logger.info(f"  {r['name']:6s} | {r['email'] or '无邮箱':30s} | {r['title'][:40] if r['title'] else '无职称'}")

    # 导出 CSV
    if clean:
        import csv
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = TASK_DIR / f"南京大学_计算机学院_教师邮箱_{timestamp}.csv"

        all_fields = ["name", "department", "title", "email", "url"]
        field_names_cn = ["姓名", "学院", "职称", "邮箱", "主页链接"]

        # 有邮箱的排在前面
        with_email_list = [r for r in clean if r["email"]]
        no_email_list = [r for r in clean if not r["email"]]
        final_sorted = with_email_list + no_email_list

        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=all_fields, extrasaction="ignore")
            # 写入中文表头
            f.write(",".join(field_names_cn) + "\n")
            for r in final_sorted:
                writer.writerow(r)

        logger.info(f"\nCSV 已导出: {csv_path}")

        # 无邮箱名单
        if no_email_list:
            ne_path = TASK_DIR / f"南京大学_计算机学院_无邮箱_{timestamp}.csv"
            with open(ne_path, "w", newline="", encoding="utf-8-sig") as f:
                ne_writer = csv.DictWriter(f, fieldnames=all_fields, extrasaction="ignore")
                f.write(",".join(field_names_cn) + "\n")
                for r in no_email_list:
                    ne_writer.writerow(r)
            logger.info(f"无邮箱名单: {ne_path}")

        print(f"\n[FILES]")
        print(f"{csv_path.name} | 南京大学计算机学院教师邮箱 (共{len(clean)}条, {has_email}个邮箱)")
        print(f"[/FILES]")
    else:
        logger.error("未获取到任何有效数据！")


if __name__ == "__main__":
    asyncio.run(main())
