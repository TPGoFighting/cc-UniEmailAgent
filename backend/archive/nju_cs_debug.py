"""快速调试 NJU CS 页面结构。"""
import asyncio
import sys
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        urls = [
            "https://cs.nju.edu.cn/1651/list.htm",
            "https://cs.nju.edu.cn/2639/list.htm",
            "https://cs.nju.edu.cn/2640/list.htm",
        ]

        for url in urls:
            print(f"\n{'='*60}")
            print(f"URL: {url}")
            print(f"{'='*60}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(1)

                # 提取所有链接文本（前50个）
                links = await page.evaluate("""() => {
                    const results = [];
                    const main = document.querySelector('.list-content, .wp, .content, main, article, #content') || document.body;
                    const all = main.querySelectorAll('a');
                    for (const a of all) {
                        const text = (a.textContent || '').trim();
                        const href = a.href || '';
                        if (text && href && !href.startsWith('javascript:') && !href.startsWith('mailto:')) {
                            results.push({text: text.substring(0, 80), href: href.substring(0, 120)});
                        }
                    }
                    return results.slice(0, 60);
                }""")
                for l in links:
                    print(f"  [{l['text']}] → {l['href']}")

                # 页面标题
                title = await page.title()
                print(f"\n标题: {title}")

                # 提取页面文本前500字符
                text = await page.evaluate("() => (document.body?.innerText || '').substring(0, 800)")
                print(f"\n文本预览:\n{text[:800]}")

            except Exception as e:
                print(f"ERROR: {e}")

        await browser.close()

asyncio.run(main())
