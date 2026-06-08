#!/usr/bin/env python3
"""深入查找教师名在 DOM 中的位置"""
import asyncio
from playwright.async_api import async_playwright

URLS = [
    ("植保-教师目录", "https://plant.njau.edu.cn/zwbhxy_all.jsp?urltype=tree.TreeTempUrl&wbtreeid=1192"),
    ("农学院-师资", "https://nx.njau.edu.cn/jsfc_nxx.jsp?urltype=tree.TreeTempUrl&wbtreeid=1227"),
    ("园艺-果树学科", "https://yyxy.njau.edu.cn/szdw/gsxk.htm"),
    ("园艺-蔬菜学科", "https://yyxy.njau.edu.cn/szdw/scxk.htm"),
    ("食品-专任教师", "https://food.njau.edu.cn/szdw/zrjs1/azcfl.htm"),
]

async def explore(context, label, url):
    page = await context.new_page()
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        print(f"\n{'='*70}")
        print(f"【{label}】{url}")

        # Check main content area for teacher names
        main_content = await page.evaluate("""() => {
            // Find the main content container
            const containers = [];
            // Get all elements that contain 2-4 Chinese char names
            const allElements = document.querySelectorAll('*');
            const nameMap = new Map();

            allElements.forEach(el => {
                // Skip script, style elements
                if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE') return;
                const text = (el.textContent || '').trim();
                // Check if this is a leaf or near-leaf element
                if (text.length < 10 && text.length > 0) {
                    if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text)) {
                        const tag = el.tagName.toLowerCase();
                        const cls = el.className || '';
                        const parentTag = el.parentElement ? el.parentElement.tagName.toLowerCase() : '';
                        const parentCls = el.parentElement ? (el.parentElement.className || '') : '';
                        const href = el.tagName === 'A' ? el.href : (el.querySelector('a') ? el.querySelector('a').href : '');
                        const key = tag + '|' + cls;
                        if (!nameMap.has(key)) nameMap.set(key, []);
                        const arr = nameMap.get(key);
                        if (arr.length < 5) arr.push({name: text, href: href.substring(0, 120)});
                    }
                }
            });

            // Get all text blocks that look like teacher lists
            const mainCon = document.querySelector('.mainCon, .mainContent, .con, .txt, .articleList, .right, #main, .content, .dpzwy');
            const mainText = mainCon ? mainCon.innerText : '';

            return {
                containers: Array.from(nameMap.entries()).slice(0, 15).map(([k, v]) => ({key: k, samples: v})),
                mainText: mainText.substring(0, 1000)
            };
        }""")

        if main_content.get('containers'):
            print(f"\n教师名在 DOM 中的位置:")
            for c in main_content['containers']:
                print(f"  标签/类名: {c['key']}")
                for s in c['samples'][:4]:
                    print(f"    - {s['name']:6s} -> {s['href'][:80]}")
        else:
            print("\n未找到教师名")

        # Print full main content text
        if main_content.get('mainText'):
            print(f"\n主内容区文本:\n{main_content['mainText'][:800]}")

    except Exception as e:
        print(f"❌ {label}: {e}")
    finally:
        await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})
        for label, url in URLS:
            await explore(context, label, url)
        await browser.close()

asyncio.run(main())
