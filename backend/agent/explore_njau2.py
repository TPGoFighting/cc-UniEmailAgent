#!/usr/bin/env python3
"""探索南京农业大学教师主页平台"""
import asyncio
from playwright.async_api import async_playwright

async def explore():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})
        page = await context.new_page()

        # 访问教师主页平台
        await page.goto('https://faculty.njau.edu.cn/', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        title = await page.title()
        print(f'标题: {title}')
        print(f'URL: {page.url}')
        print()

        # 获取页面文本内容
        text = await page.evaluate("() => document.body.innerText")
        print('=== 页面文本 ===')
        print(text[:3000])
        print()

        # 提取所有链接
        links = await page.evaluate("""() => {
            const links = [];
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href;
                if (text && href && text.length < 50 && !href.startsWith('javascript')) {
                    links.push({text: text.substring(0, 40), href: href.substring(0, 120)});
                }
            });
            return links;
        }""")

        print('=== 所有链接 ===')
        for l in links:
            print(f'  {l["text"]:30s} -> {l["href"]}')

        # 尝试找学院筛选/分类
        html = await page.content()
        if '学院' in text or '学院' in html:
            print('\n=== 页面结构关键词搜索 ===')
            # Find department selection
            selectors = await page.evaluate("""() => {
                const results = [];
                // Check select elements
                document.querySelectorAll('select').forEach(s => {
                    const name = s.name || s.id || 'unknown';
                    const options = Array.from(s.querySelectorAll('option')).map(o => o.textContent.trim() + ':' + o.value);
                    results.push({type: 'select', name: name, options: options.slice(0, 20)});
                });
                // Check for department/college related divs/ul
                document.querySelectorAll('[class*="dept"], [class*="college"], [class*="colle"], [class*="学院"], [class*="院系"], [class*="depart"], [class*="faculty"], [class*="teacher"]').forEach(el => {
                    results.push({type: 'class', tag: el.tagName, class: el.className, text: (el.textContent || '').trim().substring(0, 100)});
                });
                return results;
            }""")
            for s in selectors:
                print(f'  [{s.get("type", "")}] {s.get("name", s.get("tag", ""))}: {s.get("class", "")}')
                if 'options' in s:
                    for opt in s['options'][:15]:
                        print(f'    - {opt}')

        await browser.close()

asyncio.run(explore())
