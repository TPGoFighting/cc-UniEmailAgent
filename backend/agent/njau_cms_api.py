#!/usr/bin/env python3
"""查找 NJAU CMS AJAX 数据端点和 tsites_load_data_options"""
import asyncio
from playwright.async_api import async_playwright

async def find_api():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})
        page = await context.new_page()

        # 跟踪XHR请求
        api_calls = []
        def handle_request(request):
            url = request.url
            if any(kw in url.lower() for kw in ['query', 'teacher', 'tsites', 'getdata', 'loaddata', 'ajax']):
                if not any(kw in url for kw in ['.js', '.css']):
                    api_calls.append({
                        'url': url[:200],
                        'method': request.method,
                        'headers': dict(request.headers)[:5]
                    })

        page.on('request', handle_request)

        await page.goto('https://plant.njau.edu.cn/zwbhxy_all.jsp?urltype=tree.TreeTempUrl&wbtreeid=1192',
                       wait_until='networkidle', timeout=30000)
        await asyncio.sleep(5)

        # 获取 tsites_load_data_options
        data_options = await page.evaluate("""() => {
            if (typeof tsites_load_data_options !== 'undefined') {
                return JSON.stringify(tsites_load_data_options).substring(0, 1000);
            }
            return 'NO tsites_load_data_options';

            // 也可以检查 window 中其他相关变量
        }""")

        print(f"tsites_load_data_options: {data_options}")

        # 检查queryteacher.js的内容
        js_content = await page.evaluate("""async () => {
            try {
                const resp = await fetch('/system/resource/tsites/portal/queryteacher.js');
                const text = await resp.text();
                return text.substring(0, 3000);
            } catch(e) {
                return 'FETCH ERROR: ' + e.toString();
            }
        }""")

        print(f"\nqueryteacher.js (前3000字):\n{js_content}")

        # API calls found
        if api_calls:
            print(f"\n=== API 调用 ({len(api_calls)}) ===")
            for c in api_calls:
                print(f"  [{c['method']}] {c['url']}")

        # 等待额外时间加载更多内容，然后提取教师信息
        await asyncio.sleep(3)

        # 获取加载后的页面内容 - 查看是否有教师列表
        loaded_content = await page.evaluate("""() => {
            // 查找教师列表容器
            const containers = document.querySelectorAll('.mainCon, .mainR, .content, #content, .list, .teacherList, [class*="teacher"], [class*="list"]');
            const results = [];
            containers.forEach(c => {
                const html = c.innerHTML.substring(0, 200);
                const text = c.textContent.replace(/\\s+/g, ' ').trim();
                results.push({
                    class: c.className,
                    html: html,
                    text_summary: text.substring(0, 300)
                });
            });
            // 如果没找到，获取整体内容
            if (results.length === 0) {
                results.push({
                    class: 'body',
                    html: document.body.innerHTML.substring(0, 500),
                    text_summary: document.body.innerText.replace(/\\s+/g, ' ').substring(0, 300)
                });
            }
            return results;
        }""")

        print(f"\n=== 加载后的内容 ({len(loaded_content)} 个容器) ===")
        for c in loaded_content:
            print(f"\n  [{c['class']}]")
            print(f"  HTML: {c['html'][:300]}")
            print(f"  Text: {c['text_summary'][:300]}")

        await browser.close()

asyncio.run(find_api())
