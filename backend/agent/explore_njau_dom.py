#!/usr/bin/env python3
"""深入检查南京农业大学师资页面 DOM 结构"""
import asyncio
from playwright.async_api import async_playwright

SAMPLE_URLS = [
    ("植物保护学院", "https://plant.njau.edu.cn/zwbhxy_all.jsp?urltype=tree.TreeTempUrl&wbtreeid=1192"),
    ("食品学院", "https://food.njau.edu.cn/szdw.htm"),
    ("前沿交叉", "https://aais.njau.edu.cn/szll.htm"),
    ("园艺学院", "https://yyxy.njau.edu.cn/szdw/szgk.htm"),
]

async def explore_dom(context, label, url):
    page = await context.new_page()
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        print(f"\n{'='*70}")
        print(f"【{label}】{url}")

        # 获取页面结构
        structure = await page.evaluate("""() => {
            function getStructure(el, depth) {
                if (depth > 4) return '';
                let result = '';
                const tag = el.tagName.toLowerCase();
                const id = el.id ? '#' + el.id : '';
                const cls = el.className && typeof el.className === 'string' ? '.' + el.className.split(/\\s+/).filter(Boolean).join('.') : '';
                const childCount = el.children.length;
                const textLen = (el.textContent || '').trim().length;
                result += '  '.repeat(depth) + '<' + tag + id + cls + '> (' + childCount + ' children, ' + textLen + ' chars)\\n';
                for (let child of el.children) {
                    result += getStructure(child, depth + 1);
                }
                return result;
            }
            return getStructure(document.body, 0);
        }""")
        # Print first 3000 chars of structure
        print(f"DOM结构(前3000字):\n{structure[:3000]}")

        # 查找所有包含链接的容器
        containers = await page.evaluate("""() => {
            const results = [];
            // Try to find teacher containers - look for elements that have multiple links with Chinese names
            const allLinks = document.querySelectorAll('a');
            const chineseNameLinks = [];
            allLinks.forEach(a => {
                const text = a.textContent.replace(/\\s+/g, ' ').trim();
                if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text) && a.href && !a.href.startsWith('javascript') && a.href !== '#') {
                    chineseNameLinks.push({name: text, href: a.href});
                }
            });

            // Try to find specific teacher listings
            // Look for common teacher list patterns
            const patterns = ['.teacher', '.faculty', '.staff', '#teacher', '#faculty',
                             '[class*="teacher"]', '[class*="faculty"]', '[class*="staff"]',
                             '[class*="jsfc"]', '[class*="教工"]', '[class*="教师"]',
                             'ul', 'ol', '.list', '.item', '.wp_entry'];
            for (let sel of patterns) {
                try {
                    const els = document.querySelectorAll(sel);
                    if (els.length > 0 && els.length < 50) {
                        results.push({selector: sel, count: els.length, sample: els[0].textContent.trim().substring(0, 100)});
                    }
                } catch(e) {}
            }
            return {chineseNameLinks: chineseNameLinks.slice(0, 10), containers: results.slice(0, 20)};
        }""")

        print(f"\n中文名链接(2-4字):")
        for t in containers.get('chineseNameLinks', [])[:10]:
            print(f"  {t['name']:8s} -> {t['href']}")

        if containers.get('containers'):
            print(f"\n布局容器:")
            for c in containers['containers'][:15]:
                print(f"  {c['selector']:30s} x{c['count']:3d} 样本: {c['sample'][:60]}")

        # 获取页面全部文本
        text = await page.evaluate("() => document.body.innerText")
        print(f"\n页面文本(前500字):\n{text[:500]}")

    except Exception as e:
        print(f"\n❌ {label}: {e}")
    finally:
        await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})
        for label, url in SAMPLE_URLS:
            await explore_dom(context, label, url)
        await browser.close()

asyncio.run(main())
