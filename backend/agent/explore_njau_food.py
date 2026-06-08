#!/usr/bin/env python3
"""深入探索食品学院教师页面结构 - 包含 faculty.njau.edu.cn 链接"""
import asyncio
from playwright.async_api import async_playwright

async def explore():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})
        page = await context.new_page()

        # 食品学院专任教师页
        await page.goto('https://food.njau.edu.cn/szdw/zrjs1/azcfl.htm', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        # 提取所有教师及其链接
        teachers_data = await page.evaluate("""() => {
            const results = [];
            // 教师名通常在 panel 结构中
            const panels = document.querySelectorAll('.panel, .panel-heading, .panel-body, [class*="jshg"], .jshg');
            panels.forEach(p => {
                const text = p.textContent.trim();
                // Find the h4/panel-title which contains category (教授, 副教授 etc)
            });

            // 从 div.jshg 提取
            document.querySelectorAll('div.jshg').forEach(div => {
                const name = div.textContent.trim();
                const link = div.querySelector('a');
                results.push({
                    name: name,
                    href: link ? link.href : '',
                    html: div.innerHTML.substring(0, 200)
                });
            });

            // 如果 jshg 没有，搜索所有含 faculty.njau.edu.cn 的链接
            if (results.length === 0) {
                document.querySelectorAll('a').forEach(a => {
                    if (a.href && a.href.includes('faculty.njau.edu.cn')) {
                        const parent = a.parentElement;
                        const text = a.textContent.trim() || (parent ? parent.textContent.trim() : '');
                        results.push({
                            name: text.substring(0, 20),
                            href: a.href,
                            parentTag: parent ? parent.tagName : '',
                            parentClass: parent ? (parent.className || '') : ''
                        });
                    }
                });
            }

            return results;
        }""")

        print(f"找到 {len(teachers_data)} 个教师:")
        for t in teachers_data[:30]:
            print(f"  {t.get('name', ''):15s} -> {t.get('href', '')[:100]}")

        # 检查页面整体结构
        structure = await page.evaluate("""() => {
            const panels = document.querySelectorAll('.panel, .panel-default, [class*="panel"]');
            const results = [];
            panels.forEach(p => {
                const heading = p.querySelector('.panel-heading, .panel-title');
                const body = p.querySelector('.panel-body, .panel-collapse');
                results.push({
                    heading: heading ? heading.textContent.trim() : '',
                    body_len: body ? body.textContent.length : 0,
                    class: p.className
                });
            });
            return results.slice(0, 20);
        }""")

        print(f"\n面板结构 ({len(structure)} 个):")
        for s in structure[:10]:
            print(f"  [{s['class']}] {s['heading']} (body:{s['body_len']}chars)")

        # 看看第一个教师的详情页
        if teachers_data and teachers_data[0].get('href'):
            teacher_url = teachers_data[0]['href']
            print(f"\n\n访问第一个教师页面: {teacher_url}")
            detail = await context.new_page()
            try:
                await detail.goto(teacher_url, wait_until='domcontentloaded', timeout=15000)
                await asyncio.sleep(2)
                detail_text = await detail.evaluate("() => document.body.innerText")
                print(f"详情页文本(前800字):\n{detail_text[:800]}")
                # 提取邮箱
                import re
                emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', detail_text)
                print(f"\n找到邮箱: {emails}")
            except Exception as e:
                print(f"访问教师详情页失败: {e}")
            finally:
                await detail.close()

        await browser.close()

asyncio.run(explore())
