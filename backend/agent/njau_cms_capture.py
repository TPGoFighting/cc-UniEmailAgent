#!/usr/bin/env python3
"""捕获 NJAU CMS 加载后的完整渲染数据"""
import asyncio, re
from playwright.async_api import async_playwright

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

async def capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})
        page = await context.new_page()

        await page.goto('https://plant.njau.edu.cn/zwbhxy_all.jsp?urltype=tree.TreeTempUrl&wbtreeid=1192',
                       wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(5)

        # 查看 CMS 渲染后的 mainCon 区域
        full_html = await page.evaluate("""() => {
            const mc = document.querySelector('.mainCon');
            if (!mc) return 'NO MAINCON';
            return mc.innerHTML.substring(0, 10000);
        }""")

        print("=== CMS 渲染后的 HTML ===")
        print(full_html[:5000])

        # 查找所有可能的 teacher 数据容器
        teacher_elements = await page.evaluate("""() => {
            const results = [];
            // Try various selectors to find teacher entries
            const selectors = [
                '.mainCon a', '.mainCon span', '.mainCon div',
                '.mainR a', '.mainR span', '.mainR div',
                '[class*="teacher"]', '[class*="teacher"] a',
                '[class*="teacher"] span', '[class*="teacher"] div',
                '.mainCon li', '.mainR li',
                '.sz_l a', '.sz_l span', '.sz_l div',
                '#vsb_content a', '#vsb_content span',
            ];
            selectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                if (els.length > 0 && els.length < 500) {
                    const texts = Array.from(els).slice(0, 5).map(e => e.textContent.trim().substring(0, 50));
                    const sampleHref = els[0].tagName === 'A' ? els[0].href.substring(0, 100) : '';
                    results.push({
                        selector: sel,
                        count: els.length,
                        sampleText: texts,
                        sampleHref: sampleHref
                    });
                }
            });
            return results;
        }""")

        print(f"\n=== 选择器匹配结果 ===")
        for r in teacher_elements:
            print(f"  {r['selector']:35s} x{r['count']:3d} 样本: {r['sampleText'][:2]}")

        # 提取 mainCon 中的邮箱
        body_text = await page.evaluate("() => document.body.innerText")
        # Find emails near teacher names
        cleaned = body_text.replace('[at]','@').replace('(at)','@').replace('#@','@')
        all_emails = list(set(EMAIL_RE.findall(cleaned)))
        # Filter out public
        teacher_emails = [e for e in all_emails if not any(e.startswith(p) for p in ['zhibao','cyxy','webmaster','admin','office','info','master','root'])]
        print(f"\n=== 页面邮箱 ({len(teacher_emails)}) ===")
        for e in teacher_emails:
            print(f"  {e}")

        await browser.close()

asyncio.run(capture())
