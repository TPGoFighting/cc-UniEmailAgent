"""探测南京信息工程大学网站结构"""
import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # 访问主站
        await page.goto("https://www.nuist.edu.cn/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # 获取所有链接
        links = await page.evaluate(
            """() => {
            const all_links = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href;
                if (text && href && !href.startsWith('javascript')) {
                    all_links.push({text: text.substring(0, 60), href: href.substring(0, 200)});
                }
            });
            return all_links;
        }"""
        )

        print("=== 所有链接 ===")
        for link in links:
            if link["text"]:
                print(f'{link["text"]:50s} | {link["href"]}')

        # 获取页面标题
        title = await page.title()
        print(f"\n=== 页面标题 ===\n{title}")

        # 页面快照
        content = await page.content()
        print(f"\n=== HTML长度 ===\n{len(content)} bytes")

        await browser.close()


asyncio.run(main())
