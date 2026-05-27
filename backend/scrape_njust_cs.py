"""南京理工大学计算机学院教师邮箱爬取脚本。

爬取策略：
  1. 直接访问计算机学院官网
  2. 找到「师资队伍」入口
  3. 按系所/教研室遍历教师列表
  4. 逐个进入教师详情页提取邮箱
"""

import asyncio
import re
import csv
import sys
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# —— 配置 ——
PAGE_TIMEOUT = 30000  # ms
PROFILE_TIMEOUT = 15000  # ms
MAX_TEACHERS_PER_GROUP = 50
OUTPUT_DIR = Path(__file__).parent / "outputs" / "njust_cs"

# 南理工计算机学院相关入口
ENTRY_URLS = [
    "https://cs.njust.edu.cn",
    "https://cs.njust.edu.cn/szdw.htm",  # 师资队伍
    "https://cs.njust.edu.cn/szdw1/js.htm",  # 教授
    "https://cs.njust.edu.cn/szdw1/fjs.htm",  # 副教授
    "https://cs.njust.edu.cn/szdw1/js1.htm",  # 讲师
]

# 学院公共邮箱特征
ADMIN_EMAIL_PREFIXES = [
    "webmaster", "admin", "office", "info", "master",
    "root", "postmaster", "bgs", "dangzheng", "yuanban",
    "wxyxz", "xwcb",
]

NAV_KEYWORDS = [
    "概况", "简介", "新闻", "通知", "公告", "招生", "培养", "就业",
    "学位", "学科", "科研", "学术", "党建", "工会", "校友", "捐赠",
    "图书馆", "校园", "地图", "网站", "登录", "邮箱", "联系我们",
    "欢迎", "首页", "返回", "更多", "详情", "查看", "下载",
]

HEADERS = ["序号", "姓名", "邮箱", "学院", "职称", "主页链接"]


# —— 工具函数 ——

def _extract_emails(text: str) -> list[str]:
    """从文本提取邮箱地址。"""
    pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    return list(set(re.findall(pattern, text)))


def _parse_at_sign(text: str) -> str:
    """恢复反爬邮箱格式。"""
    text = re.sub(r"\s*\[at\]\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(at\)\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*#@\s*", "@", text)
    text = re.sub(r"\s*\[@\]\s*", "@", text)
    text = re.sub(r"\s*\(@\)\s*", "@", text)
    return text


def _is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email))


def _is_admin_email(email: str) -> bool:
    email_lower = email.lower()
    for prefix in ADMIN_EMAIL_PREFIXES:
        if email_lower.startswith(prefix + "@"):
            return True
    return False


def _is_teacher_name(text: str) -> bool:
    """检查是否为合理的中文姓名（2-4个汉字）。"""
    text = text.strip()
    if not re.match(r"^[一-鿿]{2,4}$", text):
        return False
    for kw in NAV_KEYWORDS:
        if kw in text:
            return False
    return True


def _extract_title(text: str) -> str:
    """从文本中提取职称。"""
    titles = [
        "教授", "副教授", "助理教授", "讲师", "研究员", "副研究员",
        "助理研究员", "工程师", "高级工程师", "院士", "博导", "硕导",
        "长江学者", "杰青", "优青", "千人计划", "青年教授",
    ]
    # 按优先级返回最长匹配
    found = []
    for t in titles:
        if t in text:
            found.append(t)
    if found:
        # 返回最长的（更具体的）
        return max(found, key=len)
    return ""


def _is_nav_link(text: str) -> bool:
    """判断链接是否为导航链接。"""
    text = text.strip()
    if len(text) < 2 or len(text) > 15:
        return True
    for kw in NAV_KEYWORDS:
        if kw in text:
            return True
    return False


# —— 核心爬取逻辑 ——


async def scrape_njust_cs():
    """主爬取函数。"""
    from playwright.async_api import async_playwright

    all_teachers = []
    seen_urls = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        # —— 步骤1：打开计算机学院首页 ——
        start_url = "https://cs.njust.edu.cn"
        logger.info(f"打开 {start_url}")
        try:
            await page.goto(start_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        except Exception as e:
            logger.error(f"无法加载首页: {e}")
            await context.close()
            await browser.close()
            return all_teachers

        await asyncio.sleep(3)

        # —— 步骤2：查找师资队伍入口 ——
        faculty_links = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href || '';
                if ((text.includes('师资') || text.includes('教师') ||
                     text.includes('队伍') || text.includes('人员') ||
                     text.includes('教授') || text.includes('faculty') ||
                     text.includes('staff') ||
                     href.includes('szdw') || href.includes('jsxx') ||
                     href.includes('faculty') || href.includes('teacher') ||
                     href.includes('jzyg') || href.includes('szll') ||
                     href.includes('jslist')) &&
                    text.length <= 15) {
                    results.push({text: text, href: href});
                }
            });
            return results;
        }""")

        logger.info(f"找到 {len(faculty_links)} 个师资相关链接")
        for fl in faculty_links:
            logger.info(f"  → [{fl['text']}] {fl['href']}")

        # 如果有师资队伍页面，进入
        if faculty_links:
            faculty_url = faculty_links[0]["href"]
            logger.info(f"进入师资队伍页: {faculty_url}")
            try:
                await page.goto(faculty_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                await asyncio.sleep(3)
            except Exception as e:
                logger.warning(f"师资队伍页加载失败: {e}")

        # —— 步骤3：在师资页面查找所有可能的子页面 ——
        # 包括教授/副教授/讲师等子分类
        sub_pages = await page.evaluate("""() => {
            const results = [];
            const keywords = ['教授', '副教授', '讲师', '教师', '师资', '博导', '硕导', '名录'];
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href || '';
                if (keywords.some(k => text.includes(k)) && text.length <= 10 &&
                    !href.startsWith('javascript:') && !href.startsWith('#')) {
                    results.push({text: text, href: href});
                }
            });
            return results;
        }""")

        logger.info(f"找到 {len(sub_pages)} 个子页面")
        for sp in sub_pages:
            logger.info(f"  → [{sp['text']}] {sp['href']}")

        # 如果没有显式子页面，尝试查找可能的教师列表页
        if not sub_pages:
            # 尝试一些常见URL模式
            base = "https://cs.njust.edu.cn"
            candidates = [
                f"{base}/szdw.htm",
                f"{base}/szdw1/js.htm",
                f"{base}/szdw1/fjs.htm",
                f"{base}/szdw1/js1.htm",
                f"{base}/szdw/js.htm",
                f"{base}/szdw/fjs.htm",
                f"{base}/js.htm",
                f"{base}/fjs.htm",
            ]
            # 检查当前页面有哪些链接
            all_links = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a')).map(a => ({
                    text: a.textContent.trim().slice(0, 30),
                    href: a.href
                }));
            }""")
            for link in all_links:
                if any(kw in link["href"] for kw in ["szdw", "jslist", "teacher", "faculty", "js.htm", "fjs.htm"]):
                    logger.info(f"  候选: [{link['text']}] {link['href']}")

        # —— 步骤4：遍历每个子页面，提取教师列表 ——
        pages_to_scrape = sub_pages if sub_pages else [{"text": "当前页面", "href": page.url}]

        for sp in pages_to_scrape[:10]:
            sp_text = sp["text"]
            sp_url = sp["href"]

            logger.info(f"\n{'='*60}")
            logger.info(f"处理子页面: [{sp_text}] {sp_url}")
            logger.info(f"{'='*60}")

            try:
                await page.goto(sp_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                await asyncio.sleep(3)
            except Exception as e:
                logger.warning(f"子页面加载失败: {e}")
                continue

            # 在列表页提取教师条目（姓名+详情链接）
            teacher_entries = await extract_teacher_list(page, seen_urls)

            logger.info(f"该页面发现 {len(teacher_entries)} 个教师条目")

            # 逐个访问详情页
            for i, entry in enumerate(teacher_entries[:MAX_TEACHERS_PER_GROUP]):
                name = entry["name"]
                profile_url = entry["url"]
                list_title = entry.get("title", "")

                logger.info(f"  [{i+1}/{len(teacher_entries[:MAX_TEACHERS_PER_GROUP])}] {name} → {profile_url[:80]}")

                try:
                    profile_page = await context.new_page()
                    try:
                        await profile_page.goto(profile_url, wait_until="domcontentloaded", timeout=PROFILE_TIMEOUT)
                        await asyncio.sleep(1.5)

                        profile_text = await profile_page.evaluate("() => document.body.innerText")
                        profile_text = _parse_at_sign(profile_text)

                        emails = _extract_emails(profile_text)
                        valid_emails = [e for e in emails if _is_valid_email(e) and not _is_admin_email(e)]

                        # 提取职称
                        title = _extract_title(profile_text) or list_title

                        if valid_emails:
                            for email in valid_emails:
                                teacher = {
                                    "name": name,
                                    "email": email,
                                    "department": "计算机科学与工程学院",
                                    "title": title,
                                    "url": profile_url,
                                }
                                all_teachers.append(teacher)
                                logger.info(f"    ✅ {name} <{email}> [{title}]")
                        else:
                            logger.info(f"    ⚠️ {name} — 详情页未找到个人邮箱")

                            # 检查是否列表页就有邮箱
                            list_emails = _extract_emails(entry.get("context", ""))
                            valid_list_emails = [e for e in list_emails if _is_valid_email(e) and not _is_admin_email(e)]
                            if valid_list_emails:
                                for email in valid_list_emails:
                                    teacher = {
                                        "name": name,
                                        "email": email,
                                        "department": "计算机科学与工程学院",
                                        "title": title or list_title,
                                        "url": profile_url,
                                    }
                                    all_teachers.append(teacher)
                                    logger.info(f"    ✅ {name} <{email}> (从列表页提取) [{title}]")
                    finally:
                        await profile_page.close()
                except Exception as e:
                    logger.warning(f"    ❌ 详情页加载失败 {name}: {e}")

            # 翻页处理
            await handle_pagination(page, sp_url, seen_urls, all_teachers, context)

        await context.close()
        await browser.close()

    # 去重（按邮箱+姓名）
    seen = set()
    unique = []
    for t in all_teachers:
        key = (t["email"], t["name"])
        if key not in seen:
            seen.add(key)
            unique.append(t)
    all_teachers = unique

    logger.info(f"\n总计: {len(all_teachers)} 位教师（去重后）")
    return all_teachers


async def extract_teacher_list(page, seen_urls: set) -> list[dict]:
    """从列表页提取教师条目（姓名+详情页链接）。"""
    entries = await page.evaluate("""() => {
        const entries = [];
        const seen = new Set();

        // 策略1：表格行中查找
        const tables = document.querySelectorAll('table');
        tables.forEach(table => {
            const rows = table.querySelectorAll('tr');
            rows.forEach(row => {
                const links = row.querySelectorAll('a');
                const cells = row.querySelectorAll('td, th');
                links.forEach(a => {
                    const text = a.textContent.trim();
                    const href = a.href;
                    if (!href || seen.has(href)) return;
                    if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text)) {
                        seen.add(href);
                        // 尝试获取同行中的职称和邮箱
                        let context = '';
                        cells.forEach(c => { context += c.textContent.trim() + ' '; });
                        let title = '';
                        for (const t of ['教授', '副教授', '讲师', '研究员', '高级工程师', '工程师']) {
                            if (context.includes(t)) { title = t; break; }
                        }
                        entries.push({
                            name: text,
                            url: href,
                            title: title,
                            context: context
                        });
                    }
                });
            });
        });

        // 策略2：列表中查找
        if (entries.length === 0) {
            const containers = document.querySelectorAll(
                'ul, div.list, div.teacher-list, div.faculty-list, div.teacher, div.teachers, div.member-list'
            );
            containers.forEach(container => {
                const items = container.querySelectorAll('li, div.item, div.card, div.entry, div.teacher-item');
                items.forEach(item => {
                    const a = item.querySelector('a');
                    if (!a) return;
                    const text = a.textContent.trim();
                    const href = a.href;
                    if (!href || seen.has(href)) return;
                    if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text)) {
                        seen.add(href);
                        const context = item.textContent.trim();
                        let title = '';
                        for (const t of ['教授', '副教授', '讲师', '研究员', '高级工程师', '工程师']) {
                            if (context.includes(t)) { title = t; break; }
                        }
                        entries.push({name: text, url: href, title: title, context: context});
                    }
                });
            });
        }

        // 策略3：任何页面中查找可能是教师姓名的链接
        if (entries.length === 0) {
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href;
                if (!href || seen.has(href)) return;
                const navWords = ['概况','简介','新闻','通知','公告','招生','培养','就业',
                    '学位','学科','科研','学术','党建','工会','校友','首页','返回','更多',
                    '下载','联系我们','登录'];
                if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text) &&
                    !navWords.includes(text)) {
                    seen.add(href);
                    entries.push({name: text, url: href, title: '', context: ''});
                }
            });
        }

        return entries;
    }""")

    # 过滤已见过的URL
    filtered = [e for e in entries if e["url"] not in seen_urls]
    for e in filtered:
        seen_urls.add(e["url"])

    return filtered


async def handle_pagination(page, base_url: str, seen_urls: set, all_teachers: list, context):
    """处理翻页（如果有的话）。"""
    # 查找翻页链接
    next_links = await page.evaluate("""() => {
        const results = [];
        document.querySelectorAll('a').forEach(a => {
            const text = a.textContent.trim();
            if (['下一页', '下页', '»', '>', 'next'].includes(text)) {
                results.push(a.href);
            }
        });
        return results;
    }""")

    for next_url in next_links[:3]:  # 最多翻3页
        if next_url in seen_urls:
            continue
        seen_urls.add(next_url)
        logger.info(f"  → 翻页: {next_url}")
        try:
            await page.goto(next_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
            await asyncio.sleep(2)
            teacher_entries = await extract_teacher_list(page, seen_urls)
            logger.info(f"  翻页发现 {len(teacher_entries)} 个教师条目")

            for entry in teacher_entries[:MAX_TEACHERS_PER_GROUP]:
                name = entry["name"]
                profile_url = entry["url"]

                try:
                    profile_page = await context.new_page()
                    try:
                        await profile_page.goto(profile_url, wait_until="domcontentloaded", timeout=PROFILE_TIMEOUT)
                        await asyncio.sleep(1)
                        profile_text = await profile_page.evaluate("() => document.body.innerText")
                        profile_text = _parse_at_sign(profile_text)
                        emails = _extract_emails(profile_text)
                        valid_emails = [e for e in emails if _is_valid_email(e) and not _is_admin_email(e)]
                        title = _extract_title(profile_text) or entry.get("title", "")

                        if valid_emails:
                            for email in valid_emails:
                                teacher = {
                                    "name": name,
                                    "email": email,
                                    "department": "计算机科学与工程学院",
                                    "title": title,
                                    "url": profile_url,
                                }
                                all_teachers.append(teacher)
                                logger.info(f"    ✅ {name} <{email}> [{title}]")
                        else:
                            logger.info(f"    ⚠️ {name} — 无个人邮箱")
                    finally:
                        await profile_page.close()
                except Exception as e:
                    logger.warning(f"    ❌ 详情页失败 {name}: {e}")
        except Exception as e:
            logger.warning(f"翻页失败: {e}")


# —— 文件导出 ——


def export_csv(records: list[dict], output_dir: Path) -> Path:
    """导出 CSV 文件。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"南京理工大学_计算机学院_教师邮箱_{ts}.csv"

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        for i, r in enumerate(records, 1):
            writer.writerow([
                i,
                r.get("name", ""),
                r.get("email", ""),
                r.get("department", ""),
                r.get("title", ""),
                r.get("url", ""),
            ])

    logger.info(f"CSV 已保存: {filepath} ({len(records)} 条记录)")
    return filepath


# —— 主入口 ——


async def main():
    logger.info("="*60)
    logger.info("南京理工大学计算机学院教师邮箱爬取")
    logger.info("="*60)

    teachers = await scrape_njust_cs()

    if teachers:
        filepath = export_csv(teachers, OUTPUT_DIR)

        # 打印统计
        titles = {}
        for t in teachers:
            title = t.get("title", "未知")
            titles[title] = titles.get(title, 0) + 1

        logger.info(f"\n{'='*60}")
        logger.info(f"爬取完成！")
        logger.info(f"  教师总数: {len(teachers)}")
        logger.info(f"  输出文件: {filepath}")
        logger.info(f"  职称分布:")
        for title, count in sorted(titles.items(), key=lambda x: -x[1]):
            logger.info(f"    {title}: {count}人")

        # 打印前20条预览
        logger.info(f"\n前20条预览:")
        for t in teachers[:20]:
            logger.info(f"  {t['name']} <{t['email']}> [{t['title']}]")
    else:
        logger.error("未提取到任何教师信息！")
        logger.info("可能原因：")
        logger.info("  1. 网站结构已变化")
        logger.info("  2. 需要先在浏览器中手动分析页面结构")
        logger.info("  3. 教师信息在iframe或动态加载中")

    return teachers


if __name__ == "__main__":
    asyncio.run(main())
