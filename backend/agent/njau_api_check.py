#!/usr/bin/env python3
"""检查 NJAU JSP 页面网络请求和 API 端点"""
import asyncio
from playwright.async_api import async_playwright

async def check_api():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})
        page = await context.new_page()

        # 监控网络请求
        api_requests = []

        def handle_response(response):
            url = response.url
            if any(kw in url for kw in ['api', 'ajax', 'json', 'query', 'search', 'teacher', 'faculty', 'user', 'getTeacher', 'getData', '.do', '.action']):
                if not any(kw in url for kw in ['.css', '.js', '.png', '.jpg', '.gif', '.ico', '.svg', '.woff']):
                    api_requests.append({
                        'url': url[:150],
                        'status': response.status,
                        'type': response.request.resource_type
                    })

        page.on('response', handle_response)

        # 测试植保学院JSP页面
        await page.goto('https://plant.njau.edu.cn/zwbhxy_all.jsp?urltype=tree.TreeTempUrl&wbtreeid=1192',
                       wait_until='networkidle', timeout=30000)
        await asyncio.sleep(3)

        print(f"=== 网络请求 ({len(api_requests)} 个) ===")
        for r in api_requests:
            print(f"  [{r['status']}] {r['type']:10s} {r['url']}")

        # 检查页面是否有隐藏数据
        hidden_data = await page.evaluate("""() => {
            const results = {};

            // Check for JSON in script tags
            const scripts = document.querySelectorAll('script');
            scripts.forEach((s, i) => {
                const text = s.textContent || '';
                if (text.includes('teacher') || text.includes('email') || text.includes('@')) {
                    results['script_' + i] = text.substring(0, 300);
                }
            });

            // Check for data attributes
            const dataAttrs = [];
            document.querySelectorAll('[data-*]').forEach(el => {
                const attrs = el.getAttributeNames().filter(n => n.startsWith('data-'));
                if (attrs.length > 0) {
                    const vals = {};
                    attrs.forEach(a => vals[a] = el.getAttribute(a));
                    dataAttrs.push(vals);
                }
            });
            if (dataAttrs.length > 0) results['data_attrs'] = dataAttrs.slice(0, 10);

            // Check input fields
            const inputs = [];
            document.querySelectorAll('input[type="hidden"]').forEach(inp => {
                inputs.push({name: inp.name, value: inp.value.substring(0, 100)});
            });
            if (inputs.length > 0) results['hidden_inputs'] = inputs.slice(0, 20);

            return results;
        }""")

        print(f"\n=== 隐藏数据 ===")
        for key, val in hidden_data.items():
            print(f"\n[{key}]")
            if isinstance(val, list):
                for v in val[:5]:
                    print(f"  {v}")
            else:
                print(f"  {val}")

        # 检查页面源代码中的邮箱（包括HTML属性中的）
        html = await page.content()
        import re
        emails_in_html = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
        emails_in_html = list(set(emails_in_html))
        if emails_in_html:
            print(f"\n=== HTML源码中的邮箱 ({len(emails_in_html)}) ===")
            for e in emails_in_html:
                print(f"  {e}")

        # 现在用同样的方法测试 food 学院 - 它已经有教师链接
        print("\n\n=== 测试食品学院 ===")
        await page.goto('https://food.njau.edu.cn/szdw/zrjs1/azcfl.htm',
                       wait_until='networkidle', timeout=30000)
        await asyncio.sleep(2)

        # 提取所有教师名和链接
        teachers = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href;
                if (text && href && /^[\\u4e00-\\u9fff]{2,4}$/.test(text) && href.includes('faculty.njau.edu.cn')) {
                    results.push({name: text, href: href});
                }
            });

            // 如果没找到，试试在div.jshg中的内容
            if (results.length === 0) {
                document.querySelectorAll('div.jshg').forEach(div => {
                    const text = div.textContent.trim();
                    const name = text.replace(/\\(.*?\\)/g, '').trim();
                    const link = div.querySelector('a');
                    if (name && /^[\\u4e00-\\u9fff]{2,4}$/.test(name)) {
                        results.push({name: name, href: link ? link.href : ''});
                    }
                });
            }
            return results;
        }""")

        print(f"找到 {len(teachers)} 个教师 (食品学院)")
        for t in teachers[:5]:
            print(f"  {t['name']:10s} -> {t['href']}")

        # 尝试访问一个 faculty 页面（可能部分能用）
        if teachers:
            test_url = teachers[0]['href']
            print(f"\n尝试访问: {test_url}")
            await page.goto(test_url, wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(2)
            body = await page.evaluate("() => document.body.innerText")
            print(f"页面内容:\n{body[:500]}")

        await browser.close()

asyncio.run(check_api())
