"""
南京邮电大学计算机学院教师信息抓取 v3
- 提取：姓名、邮箱、职称、主页链接
- 专任教师 + 非专任教师 全部抓取
"""
import asyncio
import re
import sys
from pathlib import Path
from datetime import datetime

BASE_URL = "https://cs.njupt.edu.cn"

# 公用邮箱（非个人邮箱，需要过滤）
COMMON_EMAILS = {
    "jsjsj@njupt.edu.cn",
    "jsjxy@njupt.edu.cn",
    "jsjyz@njupt.edu.cn",
    "njupt@njupt.edu.cn",
    "cs@njupt.edu.cn",
}

# 非教师姓名的导航文本
NAV_TEXTS = {
    "南邮主页", "智慧校园", "诚聘英才", "领导信箱", "首页", "学院概况",
    "学院简介", "现任领导", "机构设置", "院徽院训", "师资队伍", "师资概况",
    "教师名录", "专任教师", "非专任教师", "导师介绍", "师德师风建设",
    "人才培养", "本科生教育", "专业介绍", "招生宣传", "创新班", "研究生教育",
    "研究生培养", "研究生管理", "创新竞赛", "教学动态", "科学研究",
    "学科建设", "科研平台", "科研方向", "学术交流", "学生工作", "学工队伍",
    "分团委", "学生活动", "学子风采", "校友之家", "下载专区", "党建思政",
    "党建活动", "党委概况", "理论学习", "廉政监督", "工会工作", "本科教学",
    "研究生教学", "科研工作", "师资建设", "实验室建设", "党员发展",
    "欢迎访问", "学院", "学校", "更多", "详情",
}


def is_valid_teacher_name(name: str) -> bool:
    """判断是否为真实教师姓名（中文2-4字，非导航文本）。"""
    name = name.strip()
    if len(name) < 2 or len(name) > 6:
        return False
    if not all("一" <= c <= "鿿" or c in "·-" for c in name):
        return False
    if name in NAV_TEXTS:
        return False
    return True


def extract_emails(text: str) -> list[str]:
    """从文本中提取邮箱地址（含反爬恢复）。"""
    text = re.sub(r"\s*\[at\]\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(at\)\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*#@\s*", "@", text)
    text = re.sub(r"\s*\[@\]\s*", "@", text)
    pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    emails = list(set(re.findall(pattern, text)))
    skip = ["example", ".png", ".jpg", ".gif", "webmaster", "noreply",
            "admin@", "support@", "info@", "contact@", "postmaster",
            "mailto@", "abuse@", "no-reply"]
    return [e for e in emails if not any(s in e.lower() for s in skip)]


def extract_title(text: str) -> str:
    """从页面文本中提取职称。"""
    patterns = [
        r"职称[：:]\s*(.+?)(?:\n|$|。|，|,)",
        r"职务[：:]\s*(.+?)(?:\n|$|。|，|,)",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            t = m.group(1).strip()
            # 清理：只保留有意义的职称
            if len(t) <= 30 and any(kw in t for kw in ["教授", "讲师", "工程师", "研究员", "实验师"]):
                return t
    return ""


async def scrape_teacher_list(page, list_url: str, max_pages: int = 10) -> dict:
    """抓取教师列表页，返回 {url: name}（用 URL 做 key 避免同名覆盖）。"""
    teachers = {}  # url -> name

    for page_num in range(1, max_pages + 1):
        if page_num == 1:
            url = list_url
        else:
            url = f"{list_url.replace('/list.htm', '')}/list{page_num}.htm"

        try:
            print(f"  加载列表第 {page_num} 页: {url}")
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            if resp and resp.status >= 400:
                print(f"    HTTP {resp.status}，已到末页")
                break

            await asyncio.sleep(1.0)

            # JS 提取所有教师链接
            items = await page.evaluate("""() => {
                const results = [];
                document.querySelectorAll('a[href*="page.htm"]').forEach(a => {
                    const text = a.textContent.trim();
                    results.push({name: text, href: a.href});
                });
                return results;
            }""")

            found = 0
            for item in items:
                raw_name = item["name"]
                # 清理名称：去括号内容、去年份数字后缀
                clean_name = re.sub(r"[（(][^)）]*[)）]", "", raw_name).strip()
                clean_name = re.sub(r"\d{4}\s*", "", clean_name).strip()
                clean_name = clean_name.strip()

                href = item["href"]
                # 补全相对 URL
                if not href.startswith("http"):
                    href = BASE_URL + href if href.startswith("/") else BASE_URL + "/" + href

                # 跳过已抓取的（用 URL 去重）
                if is_valid_teacher_name(clean_name) and href not in teachers:
                    teachers[href] = clean_name
                    found += 1

            # 如果 JS 没找到，用正则回退
            if found == 0:
                html = await page.content()
                links = re.findall(
                    r'<a[^>]*href="([^"]*page\.htm[^"]*)"[^>]*>\s*([一-鿿·]{2,6})\s*</a>',
                    html
                )
                for href, name in links:
                    if not href.startswith("http"):
                        href = BASE_URL + href if href.startswith("/") else BASE_URL + "/" + href
                    if is_valid_teacher_name(name) and href not in teachers:
                        teachers[href] = name
                        found += 1

            print(f"    本页 {found} 人，累计 {len(teachers)} 人")
            if found == 0:
                break

        except Exception as e:
            print(f"    错误: {e}")
            break

    return teachers


async def scrape_teacher_detail(page, name: str, profile_url: str) -> dict:
    """访问教师详情页，提取邮箱和职称。"""
    try:
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(0.3)

        page_text = await page.evaluate("() => document.body.innerText")
        emails = extract_emails(page_text)

        # 过滤公用邮箱，只保留个人邮箱
        personal_emails = [
            e for e in emails
            if e.lower() not in COMMON_EMAILS and "njupt" in e.lower()
        ]

        title = extract_title(page_text)

        return {
            "name": name,
            "email": personal_emails[0] if personal_emails else "",
            "title": title,
            "url": profile_url,
        }
    except Exception as e:
        print(f"    详情页错误: {e}")
        return {"name": name, "email": "", "title": "", "url": profile_url}


async def main():
    from playwright.async_api import async_playwright

    print("=" * 60)
    print("南京邮电大学计算机学院 — 教师信息抓取 v3")
    print("=" * 60)

    all_teachers = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        # ====== 阶段 1：抓取专任教师列表 ======
        print("\n[阶段 1] 抓取专任教师列表...")
        teachers_1 = await scrape_teacher_list(
            page, f"{BASE_URL}/18765/list.htm"
        )
        all_teachers.update(teachers_1)
        print(f"  专任教师: {len(teachers_1)} 人")

        # ====== 阶段 2：抓取非专任教师列表 ======
        print("\n[阶段 2] 抓取非专任教师列表...")
        teachers_2 = await scrape_teacher_list(
            page, f"{BASE_URL}/18766/list.htm"
        )
        all_teachers.update(teachers_2)
        print(f"  非专任教师: {len(teachers_2)} 人")

        print(f"\n  合计: {len(all_teachers)} 位教师")

        # ====== 阶段 3：逐个访问详情页 ======
        print(f"\n[阶段 3] 逐个访问详情页提取信息...")
        results = []
        total = len(all_teachers)

        for i, (url, name) in enumerate(all_teachers.items(), 1):
            result = await scrape_teacher_detail(page, name, url)
            results.append(result)
            status = "✓" if result["email"] else "✗"
            title_str = f" [{result['title']}]" if result["title"] else ""
            email_str = result["email"] if result["email"] else "无邮箱"
            print(f"  [{i:3d}/{total}] {status} {name}{title_str}: {email_str}")

        await browser.close()

    # ====== 阶段 4：导出 ======
    print(f"\n[阶段 4] 导出文件...")
    results.sort(key=lambda x: x["name"])

    # 统计
    with_email = sum(1 for r in results if r["email"])
    with_title = sum(1 for r in results if r["title"])
    print(f"  总计: {len(results)} 人")
    print(f"  有邮箱: {with_email}/{len(results)}")
    print(f"  有职称: {with_title}/{len(results)}")

    if results:
        from agent.exporter import export_all
        files = export_all(results, "南京邮电大学计算机学院")
        print(f"\n  文件已生成:")
        if "csv" in files:
            print(f"    CSV:  outputs/{files['csv']}")
        if "xlsx" in files:
            print(f"    XLSX: outputs/{files['xlsx']}")
    else:
        print("\n  未获取到任何数据！")

    return results


if __name__ == "__main__":
    asyncio.run(main())
