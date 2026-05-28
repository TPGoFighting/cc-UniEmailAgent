"""深度调试 NJU CS 页面HTML结构 - 查看教师列表的实际 DOM。"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        # 教授页面
        url = "https://cs.nju.edu.cn/2639/list.htm"
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

        # 获取 list-content 区域的原始 HTML
        html = await page.evaluate("""() => {
            const main = document.querySelector('.list-content, .wp, .content, .main-content, #content, main, article');
            if (main) return main.innerHTML.substring(0, 5000);
            return document.body.innerHTML.substring(0, 5000);
        }""")
        print("=== HTML (list-content) 前5000字符 ===")
        print(html)

        # 找所有包含教师名的元素（不限于 a 标签）
        items = await page.evaluate("""() => {
            const results = [];
            // 查找所有元素，看哪些包含中文名+括号（如"吕建 (院士、博导)"）
            const all = document.querySelectorAll('*');
            for (const el of all) {
                const text = (el.textContent || '').trim();
                if (text.length >= 2 && text.length <= 30 && /^[一-鿿]{2,3}[\\s(（]/.test(text)) {
                    results.push({
                        tag: el.tagName,
                        text: text,
                        href: el.href || el.querySelector('a')?.href || '',
                        class: el.className || '',
                    });
                }
            }
            return results.slice(0, 20);
        }""")
        print("\n=== 教师条目（带括号的文本）===")
        for item in items:
            print(f"  <{item['tag']}> class='{item['class'][:50]}' href='{item['href']}'")
            print(f"    text: {item['text']}")

        # 检查是否有包含教师名的链接
        await browser.close()

asyncio.run(main())
