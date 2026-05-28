"""Debug v3 — 截图 + 等待更长时间 + 检查实际渲染 DOM。"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        url = "https://cs.nju.edu.cn/2639/list.htm"
        print(f"打开: {url}")
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)  # 等待 JS 渲染

        # 截图
        out_dir = Path(__file__).parent.parent / "outputs" / "a468ea4c-1347-4a08-adc8-696eb43df27c"
        await page.screenshot(path=str(out_dir / "debug_screenshot.png"), full_page=True)
        print("截图已保存")

        # 检查是否有 iframe
        iframes = await page.evaluate("""() => {
            return document.querySelectorAll('iframe').length;
        }""")
        print(f"iframe 数量: {iframes}")

        # 检查 Article_Title
        article_titles = await page.evaluate("""() => {
            const els = document.querySelectorAll('.Article_Title');
            const results = [];
            els.forEach(el => {
                const a = el.closest('a');
                results.push({
                    text: el.textContent.trim().substring(0, 30),
                    href: a ? a.href : 'no parent a'
                });
            });
            return {count: els.length, first: results.slice(0, 5)};
        }""")
        print(f"Article_Title: {article_titles}")

        # 检查所有可能的 class 名
        all_classes = await page.evaluate("""() => {
            const classes = new Set();
            document.querySelectorAll('*').forEach(el => {
                if (el.className && typeof el.className === 'string') {
                    el.className.split(/\\s+/).forEach(c => {
                        if (c && c.length > 1) classes.add(c);
                    });
                }
            });
            return [...classes].sort();
        }""")
        # 找包含 "title" "article" "list" "teacher" "name" 的 class
        relevant = [c for c in all_classes if any(kw in c.lower() for kw in
                    ['title', 'article', 'list', 'teacher', 'name', 'faculty', 'member', 'person'])]
        print(f"\n相关 class 名 ({len(relevant)}):")
        for c in relevant:
            # 统计使用次数
            count = await page.evaluate(f"() => document.querySelectorAll('.{c}').length")
            print(f"  .{c} → {count} 个元素")

        # 检查 body 内的 HTML 结构（找教师列表区域）
        list_area = await page.evaluate("""() => {
            const body = document.body;
            const allSpans = body.querySelectorAll('span');
            // 查找包含中文名+括号的 span
            const nameEls = [];
            allSpans.forEach(s => {
                const t = s.textContent.trim();
                if (/^[\\u4e00-\\u9fff]{2,3}[\\s（(]/.test(t) && t.length < 40) {
                    const a = s.closest('a');
                    nameEls.push({
                        tag: s.tagName,
                        class: s.className || '',
                        text: t,
                        hasLink: !!a,
                        href: a ? a.href.substring(0, 80) : ''
                    });
                }
            });
            return nameEls.slice(0, 10);
        }""")
        print(f"\n教师名 span ({len(list_area)}):")
        for el in list_area:
            print(f"  <{el['tag']}> class='{el['class']}' link={el['hasLink']}")
            print(f"    text: {el['text']}")
            if el['href']:
                print(f"    href: {el['href']}")

        await browser.close()

asyncio.run(main())
