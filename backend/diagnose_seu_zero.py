"""诊断零产出学院页面结构 — 确认教师链接提取方式。"""
import asyncio
import re
from pathlib import Path
from playwright.async_api import async_playwright

ZERO_DEPTS = [
    ("机械工程学院", "https://me.seu.edu.cn/szll/list.htm"),
    ("生物科学与医学工程学院", "https://bme.seu.edu.cn/499/list.htm"),
    ("艺术学院", "https://arts.seu.edu.cn/szdw_25730/list.htm"),
    ("法学院", "https://law.seu.edu.cn/9121/list.htm"),
    ("医学院", "https://med.seu.edu.cn/8693/list.htm"),
    ("土木工程学院", "https://civil.seu.edu.cn/10475/list.htm"),
    ("仪器科学与工程学院", "https://ins.seu.edu.cn/45076/list.htm"),
    ("自动化学院", "https://automation.seu.edu.cn/szdw_32667/list.htm"),
]

PAGE_TIMEOUT = 30000

async def diagnose():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        for dept_name, url in ZERO_DEPTS:
            print(f"\n{'='*60}")
            print(f"[{dept_name}] {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                await asyncio.sleep(2)

                # 获取页面标题
                title = await page.title()
                print(f"  标题: {title}")

                # 获取所有链接
                links = await page.evaluate("""() => {
                    const results = [];
                    document.querySelectorAll('a').forEach(a => {
                        const text = a.textContent.trim().replace(/\\s+/g, ' ');
                        const href = a.href || '';
                        if (href && !href.startsWith('javascript:') && href !== '#') {
                            results.push({text: text.substring(0, 60), href: href});
                        }
                    });
                    return results;
                }""")

                print(f"  总链接数: {len(links)}")

                # 找可能是教师姓名链接的 (2-4个汉字的链接)
                teacher_links = []
                other_links = []
                for l in links:
                    text = l['text'].strip()
                    if re.match(r'^[一-鿿·]{2,4}$', text):
                        teacher_links.append(l)
                    else:
                        other_links.append(l)

                print(f"  可能是教师链接: {len(teacher_links)}")
                for l in teacher_links[:20]:
                    print(f"    [{l['text']}] → {l['href'][:100]}")

                # 显示非教师链接的重要链接
                print(f"  其他链接 (前20):")
                for l in other_links[:20]:
                    print(f"    [{l['text'][:30]}] → {l['href'][:100]}")

                # 检查是否有内联邮箱（直接在列表页上）
                body_text = await page.evaluate("() => document.body.innerText")
                emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", body_text)
                if emails:
                    print(f"  页面上直接邮箱: {len(set(emails))} 个")
                    for e in list(set(emails))[:10]:
                        print(f"    {e}")

                # 检查分页
                pagers = await page.evaluate("""() => {
                    const links = [];
                    document.querySelectorAll('a').forEach(a => {
                        if (a.textContent.match(/\\d+/) && a.href.includes('list')) {
                            links.push({page: a.textContent.trim(), href: a.href});
                        }
                    });
                    return links;
                }""")
                if pagers:
                    print(f"  分页链接: {pagers}")

            except Exception as e:
                print(f"  错误: {e}")

        await page.close()
        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(diagnose())
