import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width":1280,"height":900})
        page = await ctx.new_page()

        await page.goto("https://chem.nju.edu.cn/szll/list.htm", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        # Check all teacher-list elements (including hidden ones)
        html = await page.evaluate("""() => {
            const lists = document.querySelectorAll('.teacher-list');
            return Array.from(lists).map(l => ({
                visible: l.offsetParent !== null,
                count: l.querySelectorAll('a').length,
                text: l.textContent.trim().substring(0, 100)
            }));
        }""")
        for h in html:
            print(f"teacher-list: visible={h['visible']}, links={h['count']}, text={h['text']}")

        # Check sidebar links
        sidebar_links = await page.evaluate("""() => {
            const all = document.querySelectorAll('.wp-menu a, .sub-menu a, .left-menu a, .sidebar a');
            return Array.from(all).map(a => ({
                text: (a.textContent || '').trim(),
                href: a.href,
                onclick: a.getAttribute('onclick') || ''
            }));
        }""")
        print("\nSidebar links:")
        for s in sidebar_links:
            if any(kw in s["text"] for kw in ["无机","分析","有机","物理","高分子","化工","生物","跨学科","实验","离退"]):
                print(f"  {s['text']} -> {s['href']} (onclick: {s['onclick'][:60]})")

        # Try to find all potential teacher page URLs in the page source
        all_links = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a')).map(a => a.href);
        }""")

        # Filter for teacher individual pages
        import re
        teacher_pattern = re.compile(r'chem\.nju\.edu\.cn/[a-z]{2,5}/list\.htm$')
        teacher_urls = set()
        for href in all_links:
            if teacher_pattern.search(href):
                teacher_urls.add(href)

        print(f"\nFound {len(teacher_urls)} potential teacher page URLs on page:")
        for u in sorted(teacher_urls):
            print(f"  {u}")

        await ctx.close()
        await browser.close()

asyncio.run(main())
