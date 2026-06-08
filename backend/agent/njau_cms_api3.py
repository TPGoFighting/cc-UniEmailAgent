#!/usr/bin/env python3
"""查找 tsites_load_data_options 数据和 queryteacher.js"""
import asyncio
from playwright.async_api import async_playwright

async def find_api():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})
        page = await context.new_page()

        await page.goto('https://plant.njau.edu.cn/zwbhxy_all.jsp?urltype=tree.TreeTempUrl&wbtreeid=1192',
                       wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(5)

        # 获取 tsites_load_data_options (可能在页面脚本中定义)
        data_options = await page.evaluate("""() => {
            // 查找所有script标签中包含tsites_load_data_options的内容
            const scripts = document.querySelectorAll('script');
            for (let s of scripts) {
                if (s.textContent && s.textContent.includes('tsites_load_data_options')) {
                    return s.textContent;
                }
            }
            // 尝试通过window查找
            if (typeof tsites_load_data_options !== 'undefined') {
                return 'WINDOW VARIABLE: ' + JSON.stringify(tsites_load_data_options);
            }
            return 'NOT FOUND';
        }""")

        print(f"tsites_load_data_options 脚本内容:")
        print(data_options[:2000])

        # 获取 queryteacher.js
        print("\n\n=== 尝试加载 queryteacher.js ===")
        try:
            await page.goto('https://plant.njau.edu.cn/system/resource/tsites/portal/queryteacher.js',
                           wait_until='domcontentloaded', timeout=10000)
            js = await page.evaluate("() => document.body.innerText")
            print(js[:3000])
        except Exception as e:
            print(f"Failed: {e}")

        await browser.close()

asyncio.run(find_api())
