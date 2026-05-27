"""针对性深度爬取南京大学教师数最少的8个学院。

直接访问各学院子域名 → 定位师资列表页 → 遍历教师详情页 → 提取邮箱。
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

# 8个目标学院配置：{名称: (子域名首页, 已知师资列表页URL)}
TARGET_DEPARTMENTS = [
    {
        "name": "艺术学院",
        "home": "https://art.nju.edu.cn",
        "faculty_hint": "szdw",  # 师资队伍路径关键词
    },
    {
        "name": "能源与资源学院",
        "home": "https://energy.nju.edu.cn",
        "faculty_hint": "ktzcy/js",
    },
    {
        "name": "工程管理学院",
        "home": "https://sme.nju.edu.cn",
        "faculty_hint": "szdw",
    },
    {
        "name": "匡亚明学院",
        "home": "https://dii.nju.edu.cn",
        "faculty_hint": "szdw",
    },
    {
        "name": "化学化工学院",
        "home": "https://chem.nju.edu.cn",
        "faculty_hint": "szdw",
    },
    {
        "name": "电子科学与工程学院",
        "home": "https://ese.nju.edu.cn",
        "faculty_hint": "szdw",
    },
    {
        "name": "文学院",
        "home": "https://chin.nju.edu.cn",
        "faculty_hint": "szdw/xrjs",
    },
    {
        "name": "教育研究院",
        "home": "https://edu.nju.edu.cn",
        "faculty_hint": "szdw",
    },
]

# 导航关键词（用于排除非教师链接）
NAV_KEYWORDS = [
    "概况", "简介", "新闻", "通知", "公告", "招生", "培养", "就业",
    "学位", "学科", "科研", "学术", "党建", "工会", "校友", "捐赠",
    "图书馆", "校园", "地图", "网站", "登录", "邮箱", "联系我们",
    "欢迎", "首页", "返回", "更多", "详情", "查看", "下载",
    "当前位置", "当前位置：", "师资队伍", "教师名录",
]

# 学院公共邮箱前缀
ADMIN_EMAIL_PREFIXES = [
    "wxyxz", "xwcb", "bgs", "dangzheng", "office", "yuanban",
    "webmaster", "admin", "info", "master", "root", "postmaster",
    "gcglxydw",  # 工程管理学院党委
]

PAGE_TIMEOUT = 30000  # ms
PROFILE_TIMEOUT = 15000  # ms
MAX_TEACHERS_PER_DEPT = 50


def is_valid_teacher_name(text: str) -> bool:
    """检查是否为合法的中文教师姓名（2-4个汉字）。"""
    text = text.strip()
    if not re.match(r'^[一-鿿]{2,4}$', text):
        return False
    for kw in NAV_KEYWORDS:
        if kw in text:
            return False
    return True


def is_valid_personal_email(email: str) -> bool:
    """检查是否为个人邮箱（非公共/行政邮箱）。"""
    email_lower = email.lower()
    for prefix in ADMIN_EMAIL_PREFIXES:
        if email_lower.startswith(prefix + "@"):
            return False
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return False
    return True


def extract_emails(text: str) -> list[str]:
    """从文本中提取邮箱地址。"""
    # 先恢复反爬邮箱
    text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*#@\s*', '@', text)
    text = re.sub(r'\s*\[@\]\s*', '@', text)
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return list(set(re.findall(pattern, text)))


def extract_title(text: str) -> str:
    """从详情页文本中提取职称。"""
    title_keywords = [
        "教授", "副教授", "助理教授", "讲师", "研究员", "副研究员",
        "助理研究员", "工程师", "高级工程师", "院士", "博导", "硕导",
        "长江学者", "杰青", "优青", "千人计划", "博士后",
    ]
    found = []
    for title in title_keywords:
        if title in text:
            found.append(title)
    return "、".join(found) if found else ""


async def scrape_department(browser_context, dept: dict, semaphore: asyncio.Semaphore) -> list[dict]:
    """爬取单个学院的所有教师邮箱。"""
    name = dept["name"]
    home = dept["home"]
    print(f"\n{'='*60}")
    print(f"🔍 开始爬取：{name} ({home})")
    print(f"{'='*60}")

    results = []
    page = await browser_context.new_page()

    try:
        # 第1步：访问学院首页，找到师资队伍入口
        print(f"  [1/4] 访问首页...")
        await page.goto(home, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        await asyncio.sleep(2)

        # 查找师资队伍链接
        faculty_links = await page.evaluate("""() => {
            const links = [];
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                const href = (a.href || '').toLowerCase();
                if ((text.includes('师资') || text.includes('教师') || text.includes('人员') ||
                     text.includes('faculty') || text.includes('staff') ||
                     href.includes('szdw') || href.includes('jsxx') || href.includes('xrjs') ||
                     href.includes('faculty') || href.includes('jzyg') || href.includes('szll') ||
                     href.includes('ktzcy')) &&
                    text.length <= 20) {
                    links.push({text: text, href: a.href});
                }
            });
            return links;
        }""")

        faculty_url = None
        if faculty_links:
            # 优先选择"师资队伍"或"教师名录"
            for fl in faculty_links:
                if "师资队伍" in fl["text"] or "教师名录" in fl["text"]:
                    faculty_url = fl["href"]
                    break
            if not faculty_url:
                faculty_url = faculty_links[0]["href"]
            print(f"  [2/4] 找到师资入口：{faculty_url}")
        else:
            # 尝试常见的师资页面路径
            hint = dept.get("faculty_hint", "szdw")
            faculty_url = urljoin(home, hint)
            print(f"  [2/4] 未找到入口，尝试：{faculty_url}")

        # 第2步：进入师资列表页
        await page.goto(faculty_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        await asyncio.sleep(3)

        # 多策略查找教师列表入口（有些学院在师资页面还有子分类）
        teacher_list_links = await page.evaluate("""() => {
            const links = [];
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                const href = (a.href || '').toLowerCase();
                if ((text.includes('教师') || text.includes('教授') || text.includes('讲师') ||
                     text.includes('专任') || text.includes('教研') || text.includes('教职') ||
                     text.includes('faculty') || text.includes('staff')) &&
                    text.length <= 15 &&
                    !text.includes('通知') && !text.includes('新闻')) {
                    links.push({text: text, href: a.href});
                }
            });
            return links;
        }""")

        if teacher_list_links:
            print(f"  [2/4] 发现 {len(teacher_list_links)} 个教师子分类：")
            for tl in teacher_list_links[:5]:
                print(f"        - {tl['text']} → {tl['href'][:80]}")

            # 如果子分类很少（<=5个），逐个进入
            if len(teacher_list_links) <= 10:
                for tl in teacher_list_links:
                    try:
                        sub_page = await browser_context.new_page()
                        await sub_page.goto(tl["href"], wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                        await asyncio.sleep(2)
                        sub_teachers = await extract_teachers_from_page(sub_page, name)
                        results.extend(sub_teachers)
                        await sub_page.close()
                        print(f"        {tl['text']}：找到 {len(sub_teachers)} 位教师")
                    except Exception as e:
                        print(f"        {tl['text']}：出错 - {str(e)[:80]}")
            else:
                # 子分类太多，在当前页面提取
                teachers = await extract_teachers_from_page(page, name)
                results.extend(teachers)
        else:
            # 当前页面就是教师列表页
            print(f"  [2/4] 当前页面即为教师列表页")
            teachers = await extract_teachers_from_page(page, name)
            results.extend(teachers)

        # 第3步：检查是否有分页
        # 保存当前页面教师数
        initial_count = len(results)

        # 查找"下一页"或分页链接
        pagination_links = await page.evaluate("""() => {
            const links = [];
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                if (text === '下一页' || text === '>' || text === '>>' ||
                    text === 'next' || /^\\d+$/.test(text)) {
                    links.push({text: text, href: a.href});
                }
            });
            return links;
        }""")

        if pagination_links:
            print(f"  [3/4] 发现分页链接 {len(pagination_links)} 个，尝试翻页...")
            for pl in pagination_links[:10]:  # 最多翻10页
                try:
                    await page.goto(pl["href"], wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                    await asyncio.sleep(2)
                    more_teachers = await extract_teachers_from_page(page, name)
                    results.extend(more_teachers)
                except Exception as e:
                    print(f"        翻页出错：{str(e)[:80]}")

        # 第4步：去重
        seen = set()
        unique_results = []
        for r in results:
            key = (r["name"], r["email"])
            if key not in seen and r["email"]:
                seen.add(key)
                unique_results.append(r)

        print(f"  [4/4] {name}：共 {len(unique_results)} 位教师（去重后）")
        return unique_results

    except Exception as e:
        print(f"  ❌ {name} 爬取出错：{str(e)[:200]}")
        import traceback
        traceback.print_exc()
        return results
    finally:
        await page.close()


async def extract_teachers_from_page(page, dept_name: str) -> list[dict]:
    """在教师列表页提取教师姓名和链接，然后逐个访问详情页提取邮箱。"""
    # 先提取所有教师姓名链接
    teacher_entries = await page.evaluate("""() => {
        const entries = [];
        const seen = new Set();

        // 策略1：在表格中查找
        document.querySelectorAll('table tr').forEach(row => {
            const links = row.querySelectorAll('a');
            const cells = Array.from(row.querySelectorAll('td, th')).map(c => c.textContent.trim());
            links.forEach(a => {
                const text = a.textContent.trim();
                const href = a.href;
                if (!href || href.startsWith('javascript:') || href.startsWith('#') || seen.has(href)) return;
                if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text)) {
                    seen.add(href);
                    entries.push({name: text, url: href});
                }
            });
        });

        // 策略2：在列表中查找
        if (entries.length < 3) {
            document.querySelectorAll('ul li a, ol li a, div.list a, div.item a').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href;
                if (!href || href.startsWith('javascript:') || href.startsWith('#') || seen.has(href)) return;
                if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text) &&
                    !text.includes('学院') && !text.includes('大学') &&
                    !text.includes('通知') && !text.includes('新闻')) {
                    seen.add(href);
                    entries.push({name: text, url: href});
                }
            });
        }

        // 策略3：查找所有可能的教师链接（更宽松）
        if (entries.length < 3) {
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href;
                if (!href || href.startsWith('javascript:') || href.startsWith('#') || seen.has(href)) return;
                if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text)) {
                    // 排除明显的导航链接
                    const parentText = (a.parentElement?.textContent || '').trim();
                    if (parentText.includes('通知') || parentText.includes('新闻') ||
                        parentText.includes('概况') || parentText.includes('公告')) return;
                    seen.add(href);
                    entries.push({name: text, url: href});
                }
            });
        }

        return entries.slice(0, 80);
    }""")

    if not teacher_entries:
        print(f"        ⚠️ 未找到教师链接")
        return []

    print(f"        找到 {len(teacher_entries)} 个教师链接")

    # 逐个访问详情页
    results = []
    for i, entry in enumerate(teacher_entries):
        name = entry["name"]
        profile_url = entry["url"]

        try:
            ctx = page.context
            profile_page = await ctx.new_page()
            try:
                await profile_page.goto(profile_url, wait_until="domcontentloaded", timeout=PROFILE_TIMEOUT)
                await asyncio.sleep(0.8)

                profile_text = await profile_page.evaluate("() => document.body.innerText")
                emails = extract_emails(profile_text)
                valid_emails = [e for e in emails if is_valid_personal_email(e)]

                if valid_emails:
                    title = extract_title(profile_text)
                    results.append({
                        "name": name,
                        "email": valid_emails[0],
                        "department": dept_name,
                        "title": title,
                        "url": profile_url,
                    })
            finally:
                await profile_page.close()
        except Exception as e:
            pass  # 详情页加载失败，跳过

        if (i + 1) % 20 == 0:
            print(f"          进度：{i+1}/{len(teacher_entries)}，已提取邮箱 {len(results)} 个")

    return results


def save_results(all_results: dict[str, list[dict]]):
    """保存各学院数据和合并数据。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 保存各学院单独文件
    for dept_name, records in all_results.items():
        if not records:
            continue
        safe_name = dept_name.replace("/", "_")
        filepath = OUTPUT_DIR / f"南京大学_{safe_name}_补全_{ts}.csv"
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["序号", "姓名", "邮箱", "学院", "职称", "主页链接"])
            for i, r in enumerate(records, 1):
                writer.writerow([i, r["name"], r["email"], r["department"], r.get("title", ""), r.get("url", "")])
        print(f"  💾 {dept_name}：{len(records)} 条 → {filepath}")

    # 合并所有8个学院
    all_records = []
    for records in all_results.values():
        all_records.extend(records)

    # 去重（按邮箱）
    seen = set()
    unique = []
    for r in all_records:
        if r["email"] not in seen:
            seen.add(r["email"])
            unique.append(r)

    filepath = OUTPUT_DIR / f"南京大学_8院补全_合并_{ts}.csv"
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["序号", "姓名", "邮箱", "学院", "职称", "主页链接"])
        for i, r in enumerate(unique, 1):
            writer.writerow([i, r["name"], r["email"], r["department"], r.get("title", ""), r.get("url", "")])
    print(f"\n  📦 合并文件：{len(unique)} 条 → {filepath}")

    return filepath


async def main():
    from playwright.async_api import async_playwright

    print("🚀 启动深度爬取引擎 - 目标：南京大学8个学院")
    print(f"   时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   并发限制：2（避免被反爬）")

    semaphore = asyncio.Semaphore(2)
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
            for dept in TARGET_DEPARTMENTS:
                async with semaphore:
                    records = await scrape_department(context, dept, semaphore)
                    all_results[dept["name"]] = records
        finally:
            await context.close()
            await browser.close()

    # 统计
    print(f"\n{'='*60}")
    print(f"📊 爬取完成！统计：")
    print(f"{'='*60}")
    for dept_name, records in all_results.items():
        print(f"  {dept_name}：{len(records)} 人")

    total = sum(len(r) for r in all_results.values())
    print(f"  🎯 总计：{total} 人")

    # 保存
    merged_path = save_results(all_results)
    print(f"\n✅ 完成！合并文件：{merged_path}")


if __name__ == "__main__":
    asyncio.run(main())
