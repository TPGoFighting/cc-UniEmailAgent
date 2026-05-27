"""东南大学教师邮箱爬取脚本 — Playwright 多级深层爬取。

爬取层次：学院列表页 → 教师列表 → 教师个人详情页 → 提取邮箱/职称/主页链接
输出：XLSX 格式，保存到 outputs/3d04ef13-e9fe-473c-b6df-a161f612c01c/
"""

import asyncio
import re
import sys
import logging
from datetime import datetime
from pathlib import Path

# 确保能导入项目模块
sys.path.insert(0, str(Path(__file__).parent))

from agent.exporter import export_xlsx
from agent.cleaner import clean_records

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TASK_ID = "3d04ef13-e9fe-473c-b6df-a161f612c01c"
UNI_NAME = "东南大学"
OUTPUT_DIR = Path(__file__).parent / "outputs" / TASK_ID

PAGE_TIMEOUT = 30000
PROFILE_TIMEOUT = 15000
MAX_TEACHERS_PER_DEPT = 50
MAX_DEPTS = 20

# 东南大学各学院师资队伍页面
DEPT_TEACHER_PAGES = [
    # (学院名, 教师列表页URL)
    ("计算机科学与工程学院", "https://cse.seu.edu.cn/101006608/list.htm"),
    ("信息科学与工程学院", "https://radio.seu.edu.cn/xxgcxy/szdw/list.htm"),
    ("电子科学与工程学院", "https://electronic.seu.edu.cn/szdw/list.htm"),
    ("自动化学院", "https://automation.seu.edu.cn/szdw/list.htm"),
    ("机械工程学院", "https://me.seu.edu.cn/34211/list.htm"),
    ("能源与环境学院", "https://power.seu.edu.cn/szdw/list.htm"),
    ("土木工程学院", "https://civil.seu.edu.cn/szdw1/list.htm"),
    ("建筑学院", "https://arch.seu.edu.cn/szdw/list.htm"),
    ("数学学院", "https://math.seu.edu.cn/szdw/list.htm"),
    ("物理学院", "https://physics.seu.edu.cn/szdw/list.htm"),
    ("化学化工学院", "https://chem.seu.edu.cn/szdw/list.htm"),
    ("经济管理学院", "https://em.seu.edu.cn/001_36145/list.htm"),
    ("电气工程学院", "https://ee.seu.edu.cn/szdw/list.htm"),
    ("外国语学院", "https://sfl.seu.edu.cn/_t69/9853/list.psp"),
    ("交通学院", "https://transport.seu.edu.cn/szdw/list.htm"),
    ("仪器科学与工程学院", "https://ins.seu.edu.cn/45092/list.psp"),
    ("法学院", "https://law.seu.edu.cn/szdw/list.htm"),
    ("医学院", "https://med.seu.edu.cn/szdw/list.htm"),
    ("材料科学与工程学院", "https://smse.seu.edu.cn/szdw/list.htm"),
    ("网络空间安全学院", "https://cyber.seu.edu.cn/_t1536/18200/list.htm"),
    ("软件学院", "https://software.seu.edu.cn/szdw/list.htm"),
    ("人工智能学院", "https://ai.seu.edu.cn/szdw/list.htm"),
    ("集成电路学院", "https://ic.seu.edu.cn/47772/list.htm"),
    ("生物科学与医学工程学院", "https://bme.seu.edu.cn/szdw/list.htm"),
]

# 反爬邮箱正则
ANTI_CRAWL_PATTERNS = [
    (re.compile(r"\[at\]", re.IGNORECASE), "@"),
    (re.compile(r"\(at\)", re.IGNORECASE), "@"),
    (re.compile(r"#@"), "@"),
    (re.compile(r"\[@\]"), "@"),
    (re.compile(r"\(@\)"), "@"),
    (re.compile(r"\s*at\s+"), "@"),
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

ADMIN_EMAIL_PATTERNS = [
    re.compile(r"^webmaster@", re.IGNORECASE),
    re.compile(r"^admin@", re.IGNORECASE),
    re.compile(r"^office@", re.IGNORECASE),
    re.compile(r"^info@", re.IGNORECASE),
    re.compile(r"^master@", re.IGNORECASE),
    re.compile(r"^postmaster@", re.IGNORECASE),
]

def parse_at_sign(text: str) -> str:
    for pattern, replacement in ANTI_CRAWL_PATTERNS:
        text = pattern.sub(replacement, text)
    return text

def extract_emails(text: str) -> list[str]:
    return list(set(EMAIL_RE.findall(text)))

def is_admin_email(email: str) -> bool:
    email_lower = email.lower()
    for p in ADMIN_EMAIL_PATTERNS:
        if p.match(email_lower):
            return True
    admin_prefixes = ["wxyxz", "xwcb", "bgs", "dangzheng", "office", "yuanban", "jxky"]
    for prefix in admin_prefixes:
        if email_lower.startswith(prefix + "@"):
            return True
    return False

def extract_title(text: str) -> str:
    title_keywords = [
        "教授", "副教授", "助理教授", "讲师", "研究员", "副研究员",
        "助理研究员", "工程师", "高级工程师", "院士", "博导", "硕导",
        "长江学者", "杰青", "优青", "千人计划", "青年首席教授",
        "青年特聘教授", "特聘教授", "首席教授",
    ]
    found = []
    for title in title_keywords:
        if title in text:
            found.append(title)
    return "、".join(found[:3]) if found else ""


async def crawl_seu():
    from playwright.async_api import async_playwright

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_teachers = []
    seen_url = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        )

        try:
            dept_count = 0
            for dept_name, list_url in DEPT_TEACHER_PAGES:
                if dept_count >= MAX_DEPTS:
                    break

                print(f"\n{'='*60}")
                print(f"📌 [{dept_count+1}/{len(DEPT_TEACHER_PAGES)}] {dept_name}")
                print(f"   列表页: {list_url}")

                try:
                    page = await context.new_page()
                    teacher_entries = []

                    try:
                        # Step 1: 加载教师列表页
                        await page.goto(list_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                        await asyncio.sleep(3)

                        # 检查是否是分页列表（list.htm类型），尝试翻页收集更多教师
                        page_title = await page.title()
                        print(f"   页面标题: {page_title[:80]}")

                        # Step 2: 提取教师姓名和链接
                        teacher_entries = await page.evaluate("""() => {
                            const entries = [];
                            const seen = new Set();

                            // 策略1：表格行（最常用）
                            const tables = document.querySelectorAll('table');
                            tables.forEach(table => {
                                const rows = table.querySelectorAll('tr');
                                rows.forEach(row => {
                                    const links = row.querySelectorAll('a');
                                    links.forEach(a => {
                                        const text = a.textContent.trim();
                                        const href = a.href;
                                        if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;
                                        if (seen.has(href)) return;
                                        // 中文姓名：2-4字
                                        if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text) &&
                                            !text.includes('学院') && !text.includes('大学') &&
                                            !text.includes('首页') && !text.includes('返回') &&
                                            !text.includes('更多') && !text.includes('通知')) {
                                            seen.add(href);
                                            entries.push({name: text, url: href});
                                        }
                                    });
                                });
                            });

                            // 策略2：列表容器
                            if (entries.length === 0) {
                                const containers = document.querySelectorAll(
                                    'ul.list, div.list, div.teacher-list, div.faculty-list, ' +
                                    'div.wp_list, div.article_list, div.news_list, div.people_list, ' +
                                    'ul.wp_list, ul.news_list, div.xxgk_list'
                                );
                                containers.forEach(container => {
                                    container.querySelectorAll('li, div.item, div.card, div.entry, div.tr').forEach(item => {
                                        const a = item.querySelector('a');
                                        if (!a) return;
                                        const text = a.textContent.trim();
                                        const href = a.href;
                                        if (!href || seen.has(href)) return;
                                        if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text) && text.length >= 2) {
                                            seen.add(href);
                                            entries.push({name: text, url: href});
                                        }
                                    });
                                });
                            }

                            // 策略3：通用链接（缩小范围到主内容区）
                            if (entries.length === 0) {
                                const mainArea = document.querySelector(
                                    'div.main, div.content, article, div.article, div.con, ' +
                                    'div.wrap, div.container, div.main_con, div.right, div.right_con'
                                );
                                const searchRoot = mainArea || document;
                                searchRoot.querySelectorAll('a').forEach(a => {
                                    const text = a.textContent.trim();
                                    const href = a.href;
                                    if (!href || seen.has(href)) return;
                                    if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text) &&
                                        !text.includes('学院') && !text.includes('大学') &&
                                        !text.includes('概况') && !text.includes('新闻') &&
                                        !text.includes('通知') && !text.includes('公告') &&
                                        !text.includes('首页') && !text.includes('更多') &&
                                        !text.includes('上一页') && !text.includes('下一页')) {
                                        seen.add(href);
                                        entries.push({name: text, url: href});
                                    }
                                });
                            }

                            return entries.slice(0, 100);
                        }""")

                        print(f"   列表页发现 {len(teacher_entries)} 位教师条目")

                        # 翻页：尝试获取更多页的教师
                        if len(teacher_entries) > 0 and ("list.htm" in list_url or "list.psp" in list_url):
                            # 尝试翻页
                            try:
                                for page_num in range(2, 10):
                                    # 尝试多种分页URL模式
                                    next_page_variants = []
                                    base = list_url

                                    # 模式1: list.htm → list2.htm 或 list_2.htm
                                    if base.endswith("list.htm"):
                                        base_no_ext = base[:-8]
                                        next_page_variants = [
                                            f"{base_no_ext}/list{page_num}.htm",
                                            f"{base_no_ext}/list_{page_num}.htm",
                                            f"{base_no_ext}list{page_num}.htm",
                                        ]
                                    elif base.endswith("list.psp"):
                                        base_no_ext = base[:-8]
                                        next_page_variants = [
                                            f"{base_no_ext}/list{page_num}.psp",
                                            f"{base_no_ext}list{page_num}.psp",
                                        ]
                                    # 模式2: query参数 ?page=N
                                    if "?" in base:
                                        next_page_variants.append(re.sub(r'page=\d+', f'page={page_num}', base))
                                    else:
                                        next_page_variants.append(f"{base}?page={page_num}")

                                    found_more = False
                                    for next_url in next_page_variants:
                                        try:
                                            await page.goto(next_url, wait_until="domcontentloaded", timeout=10000)
                                            await asyncio.sleep(1.5)

                                            more_entries = await page.evaluate("""() => {
                                                const entries = [];
                                                const seen = new Set();
                                                document.querySelectorAll('a').forEach(a => {
                                                    const text = a.textContent.trim();
                                                    const href = a.href;
                                                    if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;
                                                    if (seen.has(href)) return;
                                                    if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text) &&
                                                        !text.includes('学院') && !text.includes('大学') &&
                                                        !text.includes('首页') && !text.includes('更多')) {
                                                        seen.add(href);
                                                        entries.push({name: text, url: href});
                                                    }
                                                });
                                                return entries.slice(0, 100);
                                            }""")

                                            if more_entries:
                                                teacher_entries.extend(more_entries)
                                                found_more = True
                                                print(f"   第{page_num}页: +{len(more_entries)} 位教师")
                                            break
                                        except Exception:
                                            continue

                                    if not found_more:
                                        break
                            except Exception as e:
                                print(f"   翻页结束: {e}")

                        # 去重
                        unique_entries = []
                        seen_entry_urls = set()
                        for e in teacher_entries:
                            if e["url"] not in seen_entry_urls:
                                seen_entry_urls.add(e["url"])
                                unique_entries.append(e)
                        teacher_entries = unique_entries[:MAX_TEACHERS_PER_DEPT]
                        print(f"   去重后 {len(teacher_entries)} 位教师")

                    finally:
                        await page.close()

                    # Step 3: 逐个访问教师个人详情页
                    dept_teachers = []
                    for i, entry in enumerate(teacher_entries):
                        name = entry["name"]
                        profile_url = entry["url"]

                        if profile_url in seen_url:
                            continue
                        seen_url.add(profile_url)

                        try:
                            profile_page = await context.new_page()
                            try:
                                await profile_page.goto(profile_url, wait_until="domcontentloaded", timeout=PROFILE_TIMEOUT)
                                await asyncio.sleep(1)

                                profile_text = await profile_page.evaluate("() => document.body.innerText")
                                profile_text = parse_at_sign(profile_text)

                                emails = extract_emails(profile_text)
                                valid_emails = [e for e in emails if not is_admin_email(e)]

                                if valid_emails:
                                    title = extract_title(profile_text)
                                    dept_teachers.append({
                                        "name": name,
                                        "email": valid_emails[0],
                                        "department": dept_name,
                                        "title": title,
                                        "url": profile_url,
                                    })

                                if (i + 1) % 10 == 0:
                                    print(f"   进度: {i+1}/{len(teacher_entries)}, 已提取 {len(dept_teachers)} 条邮箱")

                            finally:
                                await profile_page.close()
                        except Exception as e:
                            logger.debug(f"详情页失败 {name}: {str(e)[:80]}")

                    print(f"   ✅ {dept_name}：{len(dept_teachers)} 条有效邮箱")
                    all_teachers.extend(dept_teachers)
                    dept_count += 1

                except Exception as e:
                    print(f"   ❌ {dept_name} 失败: {str(e)[:100]}")

        finally:
            await context.close()
            await browser.close()

    # 去重（按邮箱）
    seen_email = set()
    unique_teachers = []
    for t in all_teachers:
        if t["email"] not in seen_email:
            seen_email.add(t["email"])
            unique_teachers.append(t)

    print(f"\n{'='*60}")
    print(f"🎉 爬取完成！共 {len(unique_teachers)} 位教师（去重后）")

    # 数据清洗
    cleaned = clean_records(unique_teachers)
    print(f"清洗: {len(unique_teachers)} → {len(cleaned)} 条")

    # 导出 XLSX
    if cleaned:
        filepath = export_xlsx(cleaned, UNI_NAME, TASK_ID)
        print(f"\n📁 XLSX 已保存: {filepath}")
        print(f"   文件大小: {filepath.stat().st_size / 1024:.1f} KB")

        # 打印前10条摘要
        print("\n📋 前10条摘要:")
        for i, t in enumerate(cleaned[:10]):
            print(f"   {t['name']} | {t['email']} | {t.get('department','')} | {t.get('title','')}")
    else:
        print("\n⚠️ 未能提取到任何教师邮箱")

    return unique_teachers, cleaned


if __name__ == "__main__":
    teachers, cleaned = asyncio.run(crawl_seu())
