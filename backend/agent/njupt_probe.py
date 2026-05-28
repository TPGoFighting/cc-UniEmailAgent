"""
快速探测 yjs.njupt.edu.cn 导师系统的 URL 结构
"""
import asyncio
import re
import logging
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

async def probe_yjs():
    """探测研究生导师系统的页面结构"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=ua)
        page = await ctx.new_page()

        # 访问导师系统首页
        urls_to_try = [
            "https://yjs.njupt.edu.cn/dsgl/nocontrol/college/",
            "https://yjs.njupt.edu.cn/dsgl/",
            "https://yjs.njupt.edu.cn/",
        ]

        for url in urls_to_try:
            logger.info(f"\n🔍 尝试: {url}")
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                status = resp.status if resp else "N/A"
                logger.info(f"  状态: {status}")

                title = await page.evaluate("() => document.title || '(无标题)'")
                logger.info(f"  标题: {title[:100]}")

                # 收集所有链接
                links = await page.evaluate("""() => {
                    const ls = [];
                    document.querySelectorAll('a[href]').forEach(a => {
                        const t = (a.textContent || '').trim().substring(0, 80);
                        const h = a.href;
                        if (h && !h.startsWith('javascript:')) ls.push({t, h});
                    });
                    return ls;
                }""")

                # 分析链接模式
                college_links = [l for l in links if "college" in l["h"].lower()]
                teacher_links = [l for l in links if any(k in l["h"] for k in ["dsfcxq", "dsJbxxId", "page.htm"])]
                list_links = [l for l in links if "list.htm" in l["h"]]

                logger.info(f"  链接: 总{len(links)}, college相关{len(college_links)}, 教师{len(teacher_links)}, list{len(list_links)}")

                if college_links:
                    logger.info("  📋 College链接:")
                    for l in college_links[:10]:
                        logger.info(f"    {l['t'][:40]} → {l['h'][:100]}")

                if teacher_links:
                    logger.info("  📋 教师链接:")
                    for l in teacher_links[:5]:
                        logger.info(f"    {l['t'][:40]} → {l['h'][:100]}")

                if list_links:
                    logger.info("  📋 List链接:")
                    for l in list_links[:5]:
                        logger.info(f"    {l['t'][:40]} → {l['h'][:100]}")

            except Exception as e:
                logger.warning(f"  ❌ 失败: {str(e)[:80]}")

        # 尝试具体的college导师列表页
        college_list_urls = [
            "https://yjs.njupt.edu.cn/dsgl/nocontrol/college/dsgrrdcollege.htm",  # 学院导师列表可能
            "https://yjs.njupt.edu.cn/dsgl/nocontrol/college/dsfc.htm",  # 导师风采
        ]

        for url in college_list_urls:
            logger.info(f"\n🔍 尝试: {url}")
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                logger.info(f"  状态: {resp.status if resp else 'N/A'}")

                # 检查页面是否返回有意义的JSON/JS
                content = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 1000) : ''")
                logger.info(f"  内容片段: {content[:200]}")

                links = await page.evaluate("""() => {
                    const ls = [];
                    document.querySelectorAll('a[href]').forEach(a => {
                        ls.push({t: a.textContent.trim().substring(0,60), h: a.href});
                    });
                    return ls;
                }""")
                logger.info(f"  链接数: {len(links)}")
                for l in links[:10]:
                    logger.info(f"    {l['t'][:40]} → {l['h'][:100]}")
            except Exception as e:
                logger.warning(f"  ❌ 失败: {str(e)[:80]}")

        await ctx.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(probe_yjs())
