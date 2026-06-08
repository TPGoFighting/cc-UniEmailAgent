#!/usr/bin/env python3
"""查找 NJAU CMS AJAX 数据端点"""
import asyncio
from playwright.async_api import async_playwright

async def find_api():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})
        page = await context.new_page()

        # 收集XHR请求URLs
        api_urls = set()
        def handle_route(route):
            url = route.request.url
            if any(kw in url.lower() for kw in ['query', 'teacher', 'tsites', 'getdata', 'loaddata', 'ajax', 'json']):
                if not any(kw in url for kw in ['.js', '.css', '.png', '.jpg', '.gif', '.ico']):
                    api_urls.add(url[:200])
            route.continue_()
            asyncio.ensure_future(asyncio.sleep(0))

        await page.route("**/*", handle_route)

        await page.goto('https://plant.njau.edu.cn/zwbhxy_all.jsp?urltype=tree.TreeTempUrl&wbtreeid=1192',
                       wait_until='networkidle', timeout=30000)
        await asyncio.sleep(5)

        # 获取 tsites_load_data_options
        data_options = await page.evaluate("""() => {
            if (typeof tsites_load_data_options !== 'undefined') {
                try {
                    return JSON.stringify(tsites_load_data_options);
                } catch(e) {
                    return 'stringify error: ' + e;
                }
            }
            // 查找脚本中定义该变量的位置
            const scripts = document.querySelectorAll('script');
            for (let s of scripts) {
                if (s.textContent && s.textContent.includes('tsites_load_data_options')) {
                    return s.textContent.substring(0, 2000);
                }
            }
            return 'NO tsites_load_data_options FOUND';
        }""")

        print(f"tsites_load_data_options:")
        print(data_options[:1000])

        print(f"\n检测到的API URL ({len(api_urls)}):")
        for u in api_urls:
            print(f"  {u}")

        # 尝试直接获取 queryteacher.js
        js = await page.evaluate("""async () => {
            try {
                const resp = await fetch('/system/resource/tsites/portal/queryteacher.js');
                return await resp.text();
            } catch(e) {
                return 'FETCH ERROR: ' + e.toString();
            }
        }""")

        print(f"\nqueryteacher.js (前2000字):")
        print(js[:2000])

        await browser.close()

asyncio.run(find_api())
