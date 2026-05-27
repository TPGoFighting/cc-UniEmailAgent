"""针对南京大学8个教师数最少的学院进行深度补全爬取。

每个学院使用已知的师资页面URL和定制化的DOM提取策略。
"""

import asyncio
import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

OUTPUT_DIR = Path(__file__).parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

PAGE_TIMEOUT = 30000
PROFILE_TIMEOUT = 15000

ADMIN_EMAIL_PREFIXES = [
    "wxyxz", "xwcb", "bgs", "dangzheng", "office", "yuanban",
    "webmaster", "admin", "info", "master", "root", "postmaster",
    "gcglxydw",
]


def is_personal_email(email: str) -> bool:
    email_lower = email.lower()
    for prefix in ADMIN_EMAIL_PREFIXES:
        if email_lower.startswith(prefix + "@"):
            return False
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email))


def extract_emails(text: str) -> list[str]:
    text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*#@\s*', '@', text)
    text = re.sub(r'\s*\[@\]\s*', '@', text)
    return list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)))


def extract_title(text: str) -> str:
    keywords = ["教授", "副教授", "助理教授", "讲师", "研究员", "副研究员",
                "助理研究员", "工程师", "高级工程师", "院士", "博导", "硕导",
                "长江学者", "杰青", "优青", "博士后"]
    found = [t for t in keywords if t in text]
    return "、".join(found) if found else ""


async def scrape_page_for_teacher_links(page, url: str, dept_name: str):
    """访问页面，提取所有教师姓名+详情链接。"""
    print(f"    访问: {url[:100]}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        await asyncio.sleep(2)
    except Exception as e:
        print(f"    加载失败: {e}")
        return []

    # 获取页面文本（用于判断是否有邮箱直接在列表页）
    body_text = await page.evaluate("() => document.body.innerText")

    # 策略：检查列表页是否包含邮箱（如匡亚明学院）
    emails_in_page = extract_emails(body_text)
    personal_emails = [e for e in emails_in_page if is_personal_email(e)]

    # 先尝试提取教师链接
    teacher_links = await page.evaluate("""() => {
        const entries = [];
        const seen = new Set();

        // 策略1：表格中的教师链接
        document.querySelectorAll('table tr').forEach(row => {
            const links = row.querySelectorAll('a');
            links.forEach(a => {
                const text = a.textContent.trim();
                const href = a.href;
                if (!href || href.startsWith('javascript:') || href.startsWith('#') || seen.has(href)) return;
                if (/^[一-鿿]{2,4}$/.test(text)) {
                    seen.add(href);
                    entries.push({name: text, url: href});
                }
            });
        });

        // 策略2：teacher-name 类 (教育研究院风格)
        document.querySelectorAll('.teacher-name a, .tea_con a').forEach(a => {
            const text = a.textContent.trim();
            const href = a.href;
            if (!href || seen.has(href)) return;
            if (/^[一-鿿]{2,4}$/.test(text)) {
                seen.add(href);
                entries.push({name: text, url: href});
            }
        });

        // 策略3：列表中的教师链接 (文学院、电子科学风格)
        if (entries.length < 5) {
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href;
                if (!href || href.startsWith('javascript:') || href.startsWith('#') || seen.has(href)) return;
                if (/^[一-鿿]{2,4}$/.test(text) &&
                    !text.includes('学院') && !text.includes('大学') &&
                    !text.includes('首页') && !text.includes('通知') &&
                    !text.includes('新闻') && !text.includes('公告') &&
                    !text.includes('概况') && !text.includes('招生') &&
                    !text.includes('返回') && !text.includes('更多') &&
                    !text.includes('当前位置')) {
                    // 额外检查：父元素不应是导航
                    const parent = a.closest('nav, .nav, .header, .footer, .navi, .menu, .sidebar');
                    if (!parent) {
                        seen.add(href);
                        entries.push({name: text, url: href});
                    }
                }
            });
        }

        return entries.slice(0, 100);
    }""")

    # 如果列表页有邮箱且教师链接很少，直接用列表页数据
    if len(teacher_links) <= 3 and personal_emails and len(personal_emails) >= 3:
        print(f"    ⚡ 列表页直接含邮箱！从页面文本提取...")
        results = extract_teachers_from_text(body_text, dept_name)
        if results:
            return results

    return teacher_links


def extract_teachers_from_text(text: str, dept_name: str) -> list[dict]:
    """从包含邮箱的列表页文本中直接提取教师信息（如匡亚明学院）。"""
    results = []
    # 模式：姓名\n...职称...\n...邮箱...
    # 分割成教师块
    lines = text.split('\n')
    current_name = None
    current_title = ""
    current_email = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 检查是否包含邮箱
        emails = extract_emails(line)
        if emails:
            for e in emails:
                if is_personal_email(e):
                    current_email = e
                    break

        # 检查职称
        title = extract_title(line)
        if title:
            current_title = title

        # 检查姓名（2-4个汉字，且不是其他内容）
        if re.match(r'^[一-鿿]{2,4}$', line):
            # 排除导航关键词
            nav_words = ["首页", "通知", "新闻", "公告", "返回", "更多", "概况", "招生",
                         "邮箱", "电话", "地址", "邮编", "导航", "搜索", "当前位置"]
            if line not in nav_words:
                if current_name and (current_email or current_title):
                    results.append({
                        "name": current_name,
                        "email": current_email,
                        "department": dept_name,
                        "title": current_title,
                        "url": "",
                    })
                current_name = line
                current_title = ""
                current_email = ""

        # 邮箱行
        if ("邮箱" in line or "邮 箱" in line or "E-mail" in line.lower()) and not current_email:
            emails = extract_emails(line)
            for e in emails:
                if is_personal_email(e):
                    current_email = e
                    break

    # 最后一个
    if current_name and (current_email or current_title):
        results.append({
            "name": current_name,
            "email": current_email,
            "department": dept_name,
            "title": current_title,
            "url": "",
        })

    return results


async def visit_profile_pages(context, teacher_links: list[dict], dept_name: str) -> list[dict]:
    """批量访问教师详情页提取邮箱。"""
    results = []
    total = len(teacher_links)
    print(f"    共 {total} 个教师链接，开始访问详情页...")

    for i, entry in enumerate(teacher_links):
        name = entry["name"]
        url = entry["url"]

        try:
            profile_page = await context.new_page()
            try:
                await profile_page.goto(url, wait_until="domcontentloaded", timeout=PROFILE_TIMEOUT)
                await asyncio.sleep(0.5)

                text = await profile_page.evaluate("() => document.body.innerText")
                emails = extract_emails(text)
                valid_emails = [e for e in emails if is_personal_email(e)]

                if valid_emails:
                    title = extract_title(text)
                    results.append({
                        "name": name,
                        "email": valid_emails[0],
                        "department": dept_name,
                        "title": title,
                        "url": url,
                    })
            finally:
                await profile_page.close()
        except Exception:
            pass

        if (i + 1) % 25 == 0:
            print(f"      进度: {i+1}/{total}, 已提取邮箱 {len(results)} 个")

    return results


async def scrape_department_direct(context, name: str, urls: list[str]):
    """直接爬取指定学院的指定URL列表（处理子系/子分类）。"""
    print(f"\n{'='*50}")
    print(f"🔍 {name}")
    print(f"{'='*50}")

    page = await context.new_page()
    all_results = []

    try:
        for url in urls:
            teacher_links = await scrape_page_for_teacher_links(page, url, name)

            if isinstance(teacher_links, list) and teacher_links and isinstance(teacher_links[0], dict) and "email" in teacher_links[0]:
                # 直接从列表页提取到了完整数据
                all_results.extend(teacher_links)
                print(f"    列表页直接提取: {len(teacher_links)} 人")
            elif teacher_links:
                # 需要访问详情页
                results = await visit_profile_pages(context, teacher_links, name)
                all_results.extend(results)
                print(f"    {url.split('/')[-2] if '/' in url else url}: {len(results)} 人")
            else:
                print(f"    未找到教师链接: {url}")
    finally:
        await page.close()

    # 去重
    seen = set()
    unique = []
    for r in all_results:
        key = (r["name"], r["email"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    print(f"  ✅ {name}: {len(unique)} 人（去重后）")
    return unique


async def main():
    from playwright.async_api import async_playwright

    print("🚀 南京大学8学院深度补全爬取")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 定义每个学院的爬取URL
    dept_configs = [
        # 1. 匡亚明学院 - 邮箱在列表页！
        ("匡亚明学院", [
            "https://dii.nju.edu.cn/lsjs/list.htm",
        ]),
        # 2. 教育研究院 - 清洁的teacher-list结构
        ("教育研究院", [
            "https://edu.nju.edu.cn/8746/list.htm",
        ]),
        # 3. 电子科学与工程学院 - 文章列表
        ("电子科学与工程学院", [
            "https://ese.nju.edu.cn/szdw/list.htm",
            "https://ese.nju.edu.cn/szdw/list2.htm",
            "https://ese.nju.edu.cn/szdw/list3.htm",
        ]),
        # 4. 文学院 - 7个子学科
        ("文学院", [
            "https://chin.nju.edu.cn/szdw/xrjs/zggdwx/index.html",
            "https://chin.nju.edu.cn/szdw/xrjs/zggdwxx/index.html",
            "https://chin.nju.edu.cn/szdw/xrjs/zgxddwx/index.html",
            "https://chin.nju.edu.cn/szdw/xrjs/xjyysx/index.html",
            "https://chin.nju.edu.cn/szdw/xrjs/bjwxysjwx/index.html",
            "https://chin.nju.edu.cn/szdw/xrjs/hyywzx/index.html",
            "https://chin.nju.edu.cn/szdw/xrjs/yyxjyyyyx/index.html",
        ]),
        # 5. 艺术学院 - 3个子系
        ("艺术学院", [
            "https://art.nju.edu.cn/ysllycyx/list.htm",
            "https://art.nju.edu.cn/msysjx/list.htm",
            "https://art.nju.edu.cn/whysjyzx/list.htm",
        ]),
        # 6. 化学化工学院 - 多个子学科
        ("化学化工学院", [
            "https://chem.nju.edu.cn/szll/list.htm",  # 院士列表
            "http://chem.nju.edu.cn/d7/58/c12556a251736/page.htm",  # 无机化学
            "http://chem.nju.edu.cn/d7/59/c12557a251737/page.htm",  # 分析化学
            "http://chem.nju.edu.cn/08/5c/c12558a460892/page.htm",  # 有机化学
            "http://chem.nju.edu.cn/08/5b/c12559a460891/page.htm",  # 物理化学
            "http://chem.nju.edu.cn/d7/5c/c12560a251740/page.htm",  # 高分子
            "http://chem.nju.edu.cn/08/51/c12561a460881/page.htm",  # 化学工程
            "http://chem.nju.edu.cn/8a/1c/c17154a297500/page.htm",  # 化学生物学
        ]),
        # 7. 工程管理学院 - 4个子系
        ("工程管理学院", [
            "https://sme.nju.edu.cn/gygcyyyglx/list.htm",
            "https://sme.nju.edu.cn/fzgcglx/list.htm",
            "https://sme.nju.edu.cn/jrkjygcx/list.htm",
            "https://sme.nju.edu.cn/2031/list.htm",
        ]),
        # 8. 能源与资源学院 - 尝试各课题组
        ("能源与资源学院", [
            "https://energy.nju.edu.cn/ktzcy/js/index.html",
            "https://energy.nju.edu.cn/ktzcy/zl/index.html",
            "https://energy.nju.edu.cn/ktzcy/bsh/index.html",
        ]),
    ]

    all_results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
        )

        try:
            for name, urls in dept_configs:
                records = await scrape_department_direct(context, name, urls)
                all_results[name] = records
        finally:
            await context.close()
            await browser.close()

    # 打印统计
    print(f"\n{'='*50}")
    print(f"📊 补全爬取统计")
    print(f"{'='*50}")
    total = 0
    for name, records in all_results.items():
        print(f"  {name}: {len(records)} 人")
        total += len(records)
    print(f"  🎯 补全总计: {total} 人")

    # 保存补全数据
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for name, records in all_results.items():
        if not records:
            continue
        safe = name.replace("/", "_")
        fp = OUTPUT_DIR / f"南京大学_{safe}_补全_{ts}.csv"
        with open(fp, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["序号", "姓名", "邮箱", "学院", "职称", "主页链接"])
            for i, r in enumerate(records, 1):
                w.writerow([i, r["name"], r["email"], r["department"], r.get("title", ""), r.get("url", "")])
        print(f"  💾 {safe}: {fp}")

    # 合并所有补全数据
    all_records = []
    for records in all_results.values():
        all_records.extend(records)

    seen = set()
    unique = []
    for r in all_records:
        if r["email"] not in seen:
            seen.add(r["email"])
            unique.append(r)

    merged_fp = OUTPUT_DIR / f"南京大学_8院补全合并_{ts}.csv"
    with open(merged_fp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["序号", "姓名", "邮箱", "学院", "职称", "主页链接"])
        for i, r in enumerate(unique, 1):
            w.writerow([i, r["name"], r["email"], r["department"], r.get("title", ""), r.get("url", "")])

    print(f"\n📦 补全合并文件: {merged_fp} ({len(unique)} 人)")
    return merged_fp, all_results


if __name__ == "__main__":
    asyncio.run(main())
