#!/usr/bin/env python3
"""探索南京农业大学官网结构"""
import asyncio
from playwright.async_api import async_playwright

async def explore():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})
        page = await context.new_page()

        # 访问南京农业大学官网
        await page.goto('https://www.njau.edu.cn', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        title = await page.title()
        print(f'标题: {title}')
        print(f'URL: {page.url}')
        print()

        # 提取所有导航链接
        links = await page.evaluate("""() => {
            const links = [];
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href;
                if (text && href && text.length < 30 && !href.startsWith('javascript')) {
                    links.push({text: text.substring(0, 30), href: href.substring(0, 120)});
                }
            });
            return links;
        }""")

        print('=== 全部导航链接 ===')
        for l in links:
            print(f'  {l["text"]:25s} -> {l["href"]}')

        # 查找师资/学院相关链接
        print('\n=== 查找师资/学院相关链接 ===')
        for l in links:
            t = l['text']
            if any(kw in t for kw in ['师资', '教师', '学院', '教学', '院系', '机构', ' faculty', 'staff', '教研', '导师', '教授']):
                print(f'  {t:25s} -> {l["href"]}')

        await browser.close()

asyncio.run(explore())
