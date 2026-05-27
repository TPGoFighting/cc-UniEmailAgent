"""针对性快速补爬 - 保存每个学院完成后立即存盘。"""

import asyncio
import csv
import re
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)
TS = datetime.now().strftime("%Y%m%d_%H%M%S")

PAGE_TIMEOUT = 25000
PROFILE_TIMEOUT = 12000

ADMIN_PREFIXES = ["wxyxz", "xwcb", "bgs", "dangzheng", "office", "yuanban",
                  "webmaster", "admin", "info", "master", "root", "postmaster", "gcglxydw"]


def ok_email(e: str) -> bool:
    e = e.lower()
    for p in ADMIN_PREFIXES:
        if e.startswith(p + "@"):
            return False
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', e))


def emails_from(text: str) -> list[str]:
    text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
    return list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)))


def title_from(text: str) -> str:
    ks = ["教授", "副教授", "助理教授", "讲师", "研究员", "副研究员",
          "助理研究员", "工程师", "高级工程师", "院士", "博导", "硕导",
          "长江学者", "杰青", "优青", "博士后"]
    return "、".join(t for t in ks if t in text)


def save_dept(name: str, records: list):
    """立即保存单个学院的爬取结果。"""
    safe = name.replace("/", "_")
    fp = OUTPUT_DIR / f"南京大学_{safe}_targeted_{TS}.csv"
    with open(fp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["序号", "姓名", "邮箱", "学院", "职称", "主页链接"])
        for i, r in enumerate(records, 1):
            w.writerow([i, r["name"], r["email"], r["department"], r.get("title", ""), r.get("url", "")])
    print(f"  💾 已保存: {fp} ({len(records)}人)")
    return fp


async def scrape_list_then_profiles(context, urls: list[str], dept_name: str) -> list[dict]:
    """访问列表页→提取教师链接→访问详情页→提取邮箱。"""
    page = await context.new_page()
    all_results = []

    try:
        for url in urls:
            print(f"    📄 {url[:90]}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                await asyncio.sleep(2)
            except:
                continue

            # 先看页面文本是否直接含邮箱
            body = await page.evaluate("() => document.body.innerText")

            # 获取教师链接
            links = await page.evaluate("""() => {
                const entries = [];
                const seen = new Set();

                // teacher-name 类（教育研究院风格）
                document.querySelectorAll('.teacher-name a, .tea_con a').forEach(a => {
                    const t = a.textContent.trim();
                    if (/^[一-鿿]{2,4}$/.test(t) && !seen.has(a.href)) {
                        seen.add(a.href);
                        entries.push([t, a.href]);
                    }
                });

                // CMS news_list（电子科学/文学院风格）
                if (entries.length < 5) {
                    document.querySelectorAll('.news_list .news_title a').forEach(a => {
                        const t = a.textContent.trim();
                        if (/^[一-鿿]{2,4}$/.test(t) && !seen.has(a.href)) {
                            seen.add(a.href);
                            entries.push([t, a.href]);
                        }
                    });
                }

                // 表格中的教师链接
                if (entries.length < 5) {
                    document.querySelectorAll('table a').forEach(a => {
                        const t = a.textContent.trim();
                        if (/^[一-鿿]{2,4}$/.test(t) && !seen.has(a.href)) {
                            seen.add(a.href);
                            entries.push([t, a.href]);
                        }
                    });
                }

                // 通用链接（排除导航）
                if (entries.length < 5) {
                    document.querySelectorAll('a').forEach(a => {
                        const t = a.textContent.trim();
                        const h = a.href;
                        if (!h || h.startsWith('javascript:') || seen.has(h)) return;
                        if (/^[一-鿿]{2,4}$/.test(t)) {
                            const p = a.closest('nav,.nav,.header,.footer,.navi,.menu,.sidebar');
                            if (!p) { seen.add(h); entries.push([t, h]); }
                        }
                    });
                }

                return entries.slice(0, 60);
            }""")

            print(f"      找到 {len(links)} 个教师链接")

            # 访问详情页
            for i, (name, href) in enumerate(links):
                try:
                    pp = await context.new_page()
                    try:
                        await pp.goto(href, wait_until="domcontentloaded", timeout=PROFILE_TIMEOUT)
                        await asyncio.sleep(0.5)
                        txt = await pp.evaluate("() => document.body.innerText")
                        ems = [e for e in emails_from(txt) if ok_email(e)]
                        if ems:
                            all_results.append({
                                "name": name, "email": ems[0],
                                "department": dept_name,
                                "title": title_from(txt), "url": href,
                            })
                    finally:
                        await pp.close()
                except:
                    pass

                if (i + 1) % 20 == 0:
                    print(f"      进度 {i+1}/{len(links)}, 已提取 {len(all_results)}")
    finally:
        await page.close()

    # 去重
    seen = set()
    uniq = []
    for r in all_results:
        k = (r["name"], r["email"])
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


async def main():
    from playwright.async_api import async_playwright

    print(f"🎯 针对性补爬 - {datetime.now().strftime('%H:%M:%S')}")
    print()

    # 定义爬取任务（顺序：容易→困难）
    tasks = [
        # 1. 匡亚明学院 - 邮箱在列表页
        ("匡亚明学院", ["https://dii.nju.edu.cn/lsjs/list.htm"]),
        # 2. 教育研究院 - 清洁teacher-list
        ("教育研究院", ["https://edu.nju.edu.cn/8746/list.htm"]),
        # 3. 艺术学院 - 3个子系
        ("艺术学院", [
            "https://art.nju.edu.cn/ysllycyx/list.htm",
            "https://art.nju.edu.cn/msysjx/list.htm",
            "https://art.nju.edu.cn/whysjyzx/list.htm",
        ]),
        # 4. 工程管理学院 - 4个子系
        ("工程管理学院", [
            "https://sme.nju.edu.cn/gygcyyyglx/list.htm",
            "https://sme.nju.edu.cn/fzgcglx/list.htm",
            "https://sme.nju.edu.cn/jrkjygcx/list.htm",
            "https://sme.nju.edu.cn/2031/list.htm",
        ]),
        # 5. 文学院 - 7个子学科
        ("文学院", [
            "https://chin.nju.edu.cn/szdw/xrjs/zggdwx/index.html",
            "https://chin.nju.edu.cn/szdw/xrjs/zggdwxx/index.html",
            "https://chin.nju.edu.cn/szdw/xrjs/zgxddwx/index.html",
            "https://chin.nju.edu.cn/szdw/xrjs/xjyysx/index.html",
            "https://chin.nju.edu.cn/szdw/xrjs/bjwxysjwx/index.html",
            "https://chin.nju.edu.cn/szdw/xrjs/hyywzx/index.html",
            "https://chin.nju.edu.cn/szdw/xrjs/yyxjyyyyx/index.html",
        ]),
        # 6. 化学化工学院 - 多个子学科
        ("化学化工学院", [
            "https://chem.nju.edu.cn/szll/list.htm",
            "http://chem.nju.edu.cn/d7/58/c12556a251736/page.htm",
            "http://chem.nju.edu.cn/d7/59/c12557a251737/page.htm",
            "http://chem.nju.edu.cn/08/5c/c12558a460892/page.htm",
            "http://chem.nju.edu.cn/08/5b/c12559a460891/page.htm",
            "http://chem.nju.edu.cn/d7/5c/c12560a251740/page.htm",
            "http://chem.nju.edu.cn/08/51/c12561a460881/page.htm",
        ]),
    ]

    all_saved = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        )

        try:
            for dept_name, urls in tasks:
                print(f"\n{'='*50}")
                print(f"🔍 {dept_name} ({len(urls)} 个页面)")
                print(f"{'='*50}")
                records = await scrape_list_then_profiles(context, urls, dept_name)
                print(f"  ✅ {dept_name}: {len(records)} 人（去重后）")
                all_saved[dept_name] = records
                save_dept(dept_name, records)
        finally:
            await context.close()
            await browser.close()

    # 统计
    total = sum(len(r) for r in all_saved.values())
    print(f"\n{'='*50}")
    print(f"📊 补爬完成！总计 {total} 人")
    for name, records in all_saved.items():
        print(f"  {name}: {len(records)} 人")


if __name__ == "__main__":
    asyncio.run(main())
