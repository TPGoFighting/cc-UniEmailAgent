#!/usr/bin/env python3
"""检查 NJAU JSP CMS 页面中教师名如何嵌入HTML"""
import asyncio
from playwright.async_api import async_playwright

async def check_cms():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})
        page = await context.new_page()

        # 测试植保学院 - 查看mainCon区域中包含教师名的HTML
        await page.goto('https://plant.njau.edu.cn/zwbhxy_all.jsp?urltype=tree.TreeTempUrl&wbtreeid=1192',
                       wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        # 获取mainCon区域的HTML
        main_html = await page.evaluate("""() => {
            const mainCon = document.querySelector('.mainCon');
            if (!mainCon) return 'NO .mainCon FOUND';
            return mainCon.innerHTML.substring(0, 5000);
        }""")

        # 获取全部HTML中body部分
        body_html = await page.evaluate("() => document.body.innerHTML.substring(0, 8000)")

        print("=== 植保学院 mainCon HTML (前5000字) ===")
        print(main_html)
        print("\n\n=== body HTML (前3000字) ===")
        print(body_html[:3000])

        await browser.close()

asyncio.run(check_cms())
