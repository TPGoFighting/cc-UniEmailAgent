"""检查南大低覆盖率学院的教师页面结构"""
import asyncio
import re
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        targets = [
            ("数学学院", "https://math.nju.edu.cn/jzyg/index.html"),
            ("物理学院", "https://physics.nju.edu.cn/szdw/qbmd/index.html"),
            ("软件学院", "https://software.nju.edu.cn/szll/szdw/index.html"),
            ("大学外语部", "https://dafls.nju.edu.cn/07/dd/c13168a460765/page.htm"),
            ("文学院", "https://chin.nju.edu.cn/szdw/xrjs/index.html"),
            ("地理与海洋科学学院", "http://sgos.nju.edu.cn/62681/list.htm"),
        ]

        for cname, url in targets:
            print(f"\n=== {cname} ===")
            print(f"URL: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(2000)

                # 查找所有链接
                links = await page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a[href]'))
                        .filter(a => a.href.startsWith('http'))
                        .map(a => ({
                            text: a.innerText.trim().substring(0, 30),
                            href: a.href
                        }));
                }""")

                # 找包含教师名字的链接
                teacher_page_links = [l for l in links if '/page.htm' in l['href'] and l['text']]

                if teacher_page_links:
                    print(f"  教师详情页链接: {len(teacher_page_links)} 个")
                    for l in teacher_page_links[:5]:
                        print(f"    {l['text']:20s} -> {l['href']}")
                else:
                    # 看有没有任何下级的链接
                    sub_links = [l for l in links if '/list.htm' in l['href'] and l['text']]
                    print(f"  无教师详情页, 但发现 {len(sub_links)} 个子页面链接")
                    if sub_links:
                        for l in sub_links[:5]:
                            print(f"    {l['text']:20s} -> {l['href']}")

                    # 检查页面主要内容的HTML结构
                    html_structure = await page.evaluate("""() => {
                        const content = document.querySelector('.list_main, .content, .main, .wp, article, table, .right, .col_right, #content');
                        if (!content) return 'NO_CONTENT_DIV';
                        const children = Array.from(content.children).slice(0, 5).map(c => ({
                            tag: c.tagName,
                            cls: c.className,
                            html: c.innerHTML.substring(0, 300)
                        }));
                        return JSON.stringify(children);
                    }""")
                    print(f"  页面结构: {html_structure[:500]}")
            except Exception as e:
                print(f"  错误: {e}")

        await browser.close()

asyncio.run(main())
