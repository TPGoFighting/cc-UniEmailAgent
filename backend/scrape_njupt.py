"""
南京邮电大学计算机学院教师邮箱抓取脚本 v4（完整版）

数据来源：
1. 研究生院导师系统 (dsfcxq.htm) - 教授/副教授级别导师
2. 计算机学院教师列表页 (18765/list.htm) - 专任教师详情页
3. 非专任教师列表页 (18766/list.htm) - 行政/辅导员等
"""
import asyncio
import re
import sys
from pathlib import Path
from datetime import datetime

COMMON_EMAILS = {
    "jsjsj@njupt.edu.cn", "jsjxy@njupt.edu.cn",
    "jsjyz@njupt.edu.cn", "njupt@njupt.edu.cn",
}

NAV_KEYWORDS = [
    "首页", "学院概况", "学院简介", "现任领导", "机构设置", "院徽院训",
    "师资队伍", "师资概况", "教师名录", "专任教师", "非专任教师",
    "人才培养", "本科生教育", "本科教学", "研究生教育", "研究生培养",
    "研究生管理", "研究生教学", "专业介绍", "招生宣传", "创新班", "创新竞赛",
    "科学研究", "科研工作", "学科建设", "科研平台", "科研方向", "学术交流",
    "实验室建设", "师资建设", "师德师风",
    "党建思政", "党建活动", "党委概况", "理论学习", "党员发展", "廉政监督",
    "工会工作", "学生工作", "学工队伍", "分团委", "学生活动", "学子风采",
    "校友之家", "下载专区", "领导信箱", "诚聘英才", "智慧校园", "南邮主页",
    "导师介绍", "教学动态", "招聘", "新闻", "版权所有",
]

BASE_URL = "https://cs.njupt.edu.cn"
SUPERVISOR_DETAIL_URL = "https://yjs.njupt.edu.cn/dsgl/nocontrol/college/dsfcxq.htm"
SUPERVISOR_LIST_URL = "https://yjs.njupt.edu.cn/dsgl/nocontrol/college/dsfc.htm"


def clean_name(raw: str) -> str | None:
    """从原始文本中提取纯姓名，去掉括号内容和职称前缀。"""
    name = raw.strip()
    name = re.sub(r"[（(][^)）]*[)）]", "", name).strip()
    name = re.sub(r"^(教授|副教授|讲师|博士后|预聘副教授|预聘教授|青年专聘教授)\s*", "", name)
    if len(name) < 2 or len(name) > 6:
        return None
    if not all("一" <= c <= "鿿" or c.isalpha() or c in "·-" for c in name):
        return None
    if name in NAV_KEYWORDS:
        return None
    return name


def extract_emails(text: str) -> list[str]:
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


def is_personal_email(email: str) -> bool:
    email = email.strip().lower()
    if email in COMMON_EMAILS:
        return False
    return True


async def scrape_njupt():
    from playwright.async_api import async_playwright

    print("=" * 60)
    print("南京邮电大学计算机学院 — 教师邮箱抓取 v4")
    print("=" * 60)

    all_results = {}  # name_lower -> {name, email, title}
    teacher_ids = {}  # id -> name (from supervisor system)
    profile_urls = {}  # href -> name (from CS dept site)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        # ====== 来源 1：研究生院导师系统 ======
        print("\n[来源 1] 研究生院导师系统...")
        try:
            await page.goto(SUPERVISOR_LIST_URL, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(4)

            # 获取所有导师的 td 元素（含 onclick）
            all_supervisors = await page.evaluate("""
                () => {
                    const tds = document.querySelectorAll('td[onclick*="jumpDsfcxq"]');
                    return Array.from(tds).map(td => {
                        const onclick = td.getAttribute('onclick');
                        const match = onclick.match(/jumpDsfcxq\\('([^']+)'\\)/);
                        return {
                            name: td.textContent.trim(),
                            id: match ? match[1] : null
                        };
                    });
                }
            """)

            # 需要过滤出 计算机学院 的导师
            # 页面结构是按学科排列的：0812 计算机科学与技术 - 计算机学院
            cs_supervisors = await page.evaluate("""
                () => {
                    const results = [];
                    let inCS = false;
                    const rows = document.querySelectorAll('tr');
                    for (const row of rows) {
                        const text = row.textContent;
                        // 检测是否进入计算机学院区域
                        if (text.includes('0812') && text.includes('计算机科学与技术') && text.includes('计算机学院')) {
                            inCS = true;
                        }
                        if (text.includes('0839') && text.includes('网络空间安全') && text.includes('计算机学院')) {
                            inCS = true;
                        }
                        // 检测是否离开计算机学院区域
                        if (inCS && text.match(/^\\d{4}\\s/) && !text.includes('0812') && !text.includes('0839') && !text.includes('计算机')) {
                            inCS = false;
                        }
                        if (inCS) {
                            const tds = row.querySelectorAll('td[onclick*="jumpDsfcxq"]');
                            for (const td of tds) {
                                const onclick = td.getAttribute('onclick');
                                const match = onclick.match(/jumpDsfcxq\\('([^']+)'\\)/);
                                if (match) {
                                    results.push({name: td.textContent.trim(), id: match[1]});
                                }
                            }
                        }
                    }
                    return results;
                }
            """)

            print(f"  识别到 {len(cs_supervisors)} 位 计算机学院 导师")

            for s in cs_supervisors:
                name = clean_name(s["name"])
                if name:
                    teacher_ids[s["id"]] = name

            # 逐个访问详情页
            print(f"  正在访问详情页...")
            success = 0
            for i, (tid, name) in enumerate(teacher_ids.items(), 1):
                try:
                    detail_url = f"{SUPERVISOR_DETAIL_URL}?dsJbxxId={tid}"
                    await page.goto(detail_url, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(0.5)

                    page_text = await page.evaluate("() => document.body.innerText")
                    emails = extract_emails(page_text)
                    personal = [e for e in emails if is_personal_email(e) and "njupt" in e.lower()]

                    if personal:
                        success += 1
                        key = name.lower()
                        if key not in all_results:
                            all_results[key] = {"name": name, "email": personal[0], "title": ""}
                        print(f"  [{i}/{len(teacher_ids)}] {name}: {personal[0]}")

                        # 尝试解析职称
                        if "教授" in page_text:
                            if "副教授" in page_text:
                                all_results[key]["title"] = "副教授"
                            else:
                                all_results[key]["title"] = "教授"
                        elif "讲师" in page_text:
                            all_results[key]["title"] = "讲师"
                        elif "博士后" in page_text:
                            all_results[key]["title"] = "博士后"

                    else:
                        print(f"  [{i}/{len(teacher_ids)}] {name}: 未找到邮箱")

                except Exception as e:
                    print(f"  [{i}/{len(teacher_ids)}] {name}: 失败 ({str(e)[:50]})")

            print(f"  导师系统: 成功 {success}/{len(teacher_ids)} 人")

        except Exception as e:
            print(f"  导师系统访问失败: {e}")

        # ====== 来源 2：计算机学院专任教师详情页 ======
        print("\n[来源 2] 计算机学院专任教师详情页...")
        try:
            await page.goto(f"{BASE_URL}/18765/list.htm", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)

            # 提取所有 page.htm 链接
            page_links = await page.evaluate("""
                () => {
                    const links = document.querySelectorAll('a[href*="page.htm"]');
                    return Array.from(links).map(a => ({
                        text: a.textContent.trim(),
                        href: a.href
                    }));
                }
            """)

            for item in page_links:
                name = clean_name(item["text"])
                if name and "page.htm" in item["href"]:
                    profile_urls[item["href"]] = name

            print(f"  发现 {len(profile_urls)} 个教师详情页")

            visited = 0
            new_found = 0
            for i, (href, name) in enumerate(profile_urls.items(), 1):
                key = name.lower()
                try:
                    await page.goto(href, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(0.3)

                    page_text = await page.evaluate("() => document.body.innerText")
                    emails = extract_emails(page_text)
                    personal = [e for e in emails if is_personal_email(e) and "njupt" in e.lower()]

                    visited += 1
                    if personal and key not in all_results:
                        new_found += 1
                        all_results[key] = {"name": name, "email": personal[0], "title": ""}
                        # 确定职称
                        if "教授" in page_text:
                            if "副" in page_text:
                                all_results[key]["title"] = "副教授"
                            else:
                                all_results[key]["title"] = "教授"
                        elif "讲师" in page_text:
                            all_results[key]["title"] = "讲师"
                        print(f"  [+{i}] {name}: {personal[0]} (新增)")
                    elif personal:
                        print(f"  [{i}] {name}: {personal[0]} (已有)")
                    else:
                        if key not in all_results:
                            print(f"  [{i}] {name}: 未找到邮箱")

                except Exception as e:
                    print(f"  [{i}] {name}: 失败 ({str(e)[:50]})")

            print(f"  详情页: 访问 {visited}/{len(profile_urls)}，新增 {new_found} 人")

        except Exception as e:
            print(f"  学院网站访问失败: {e}")

        # ====== 来源 3：非专任教师 ======
        print("\n[来源 3] 非专任教师...")
        try:
            await page.goto(f"{BASE_URL}/18766/list.htm", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)

            non_teacher_links = await page.evaluate("""
                () => {
                    const links = document.querySelectorAll('a[href*="page.htm"]');
                    return Array.from(links).map(a => ({
                        text: a.textContent.trim(),
                        href: a.href
                    }));
                }
            """)

            non_teacher_count = 0
            for item in non_teacher_links:
                name = clean_name(item["text"])
                if not name:
                    continue
                key = name.lower()
                if key in all_results:
                    continue

                try:
                    await page.goto(item["href"], wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(0.3)

                    page_text = await page.evaluate("() => document.body.innerText")
                    emails = extract_emails(page_text)
                    personal = [e for e in emails if is_personal_email(e) and "njupt" in e.lower()]

                    if personal:
                        non_teacher_count += 1
                        all_results[key] = {"name": name, "email": personal[0], "title": "非专任教师"}
                        print(f"  {name}: {personal[0]}")

                except Exception as e:
                    pass

            print(f"  非专任教师: 新增 {non_teacher_count} 人")

        except Exception as e:
            print(f"  非专任教师页面访问失败: {e}")

        await browser.close()

    # ====== 汇总导出 ======
    results = list(all_results.values())
    print(f"\n{'='*60}")
    print(f"[汇总] 共 {len(results)} 位教师获取到邮箱")
    print(f"{'='*60}")

    if results:
        from agent.exporter import export_all
        files = export_all(results, "南京邮电大学计算机学院")
        csv_file = Path("outputs") / files["csv"]
        xlsx_file = Path("outputs") / files["xlsx"]
        print(f"\n  文件已生成:")
        print(f"    CSV:  {csv_file}")
        print(f"    XLSX: {xlsx_file}")

        print(f"\n  教师邮箱明细:")
        for r in sorted(results, key=lambda x: x["name"]):
            title_str = f" ({r['title']})" if r['title'] else ""
            print(f"  {r['name']}{title_str}: {r['email']}")
    else:
        print("\n  未找到任何教师邮箱！")

    return results


if __name__ == "__main__":
    asyncio.run(scrape_njupt())
