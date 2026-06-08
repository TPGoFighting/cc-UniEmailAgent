#!/usr/bin/env python3
"""探索南京农业大学部分学院师资列表页结构"""
import asyncio
from playwright.async_api import async_playwright

# 选择不同模式的页面进行探索
TEST_URLS = [
    # JSP动态列表
    ("农学院-师资队伍(JSP)", "https://nx.njau.edu.cn/jsfc_nxx.jsp?urltype=tree.TreeTempUrl&wbtreeid=1227"),
    ("植物保护学院-教师目录(JSP)", "https://plant.njau.edu.cn/zwbhxy_all.jsp?urltype=tree.TreeTempUrl&wbtreeid=1192"),
    ("草业学院-师资队伍(JSP)", "https://cyxy.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1348"),
    ("资源与环境-师资力量(JSP)", "https://re.njau.edu.cn/jsfc2.jsp?urltype=tree.TreeTempUrl&wbtreeid=1325"),
    ("工学院-师资队伍(JSP)", "https://coe.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1140"),
    ("金融学院-师资队伍(JSP)", "https://finance.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1230"),
    # 静态HTML页面
    ("园艺学院-师资概况(HTML)", "https://yyxy.njau.edu.cn/szdw/szgk.htm"),
    ("动物医学院-师资队伍(HTML)", "https://cvm.njau.edu.cn/xksz/szdw.htm"),
    ("生命科学学院-师资队伍(HTML)", "https://lfc.njau.edu.cn/szdw.htm"),
    ("理学院-师资队伍(HTML)", "https://cos.njau.edu.cn/szdw3/szdw2/js.htm"),
    ("食品学院-师资队伍(HTML)", "https://food.njau.edu.cn/szdw.htm"),
    ("人文学院-师资队伍(HTML)", "https://xrw.njau.edu.cn/szdw/kxjssx.htm"),
    ("前沿交叉-师资力量(HTML)", "https://aais.njau.edu.cn/szll.htm"),
    ("体育部-师资队伍(HTML)", "https://sports.njau.edu.cn/szdw/szdw.htm"),
]

async def explore_page(context, label, url):
    """探索单个师资页面"""
    page = await context.new_page()
    result = {"label": label, "url": url, "teacher_count": 0, "sample_links": [], "text_sample": "", "error": None, "email_count": 0}

    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        title = await page.title()
        text = await page.evaluate("() => document.body.innerText")
        result["text_sample"] = text[:300]

        # 提取教师名（2-4个汉字的链接）
        teacher_info = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.replace(/\\s+/g, ' ').trim();
                const href = a.href;
                if (text && href && /^[\\u4e00-\\u9fff]{2,4}$/.test(text) && href !== '#' && !href.startsWith('javascript')) {
                    results.push({name: text, href: href.substring(0, 150)});
                }
            });
            return results;
        }""")

        result["teacher_count"] = len(teacher_info)
        result["sample_links"] = teacher_info[:8]

        # 提取页面中所有邮箱
        emails = await page.evaluate("""() => {
            const text = document.body.innerText;
            const re = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/g;
            return [...new Set(text.match(re) || [])];
        }""")
        result["email_count"] = len(emails)

        # 检查是否有iframe
        iframes = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('iframe')).map(f => f.src);
        }""")
        result["iframes"] = iframes

    except Exception as e:
        result["error"] = str(e)
    finally:
        await page.close()
        return result

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})

        tasks = [explore_page(context, label, url) for label, url in TEST_URLS]
        results = await asyncio.gather(*tasks)

        for r in results:
            status = '❌ ' + (r['error'][:40] if r['error'] else '') if r['error'] else '✅'
            print(f"\n{'='*80}")
            print(f"【{r['label']}】")
            print(f"  URL: {r['url']}")
            print(f"  状态: {status}")
            print(f"  教师链接数: {r['teacher_count']} | 直接邮箱数: {r['email_count']}")
            if r.get('iframes'):
                print(f"  iframes: {r['iframes']}")
            if r['sample_links']:
                print(f"  教师样本:")
                for t in r['sample_links'][:5]:
                    print(f"    {t['name']:8s} -> {t['href']}")
            if r['teacher_count'] == 0:
                print(f"  页面文本(前300): {r['text_sample']}")

        await browser.close()

asyncio.run(main())
