#!/usr/bin/env python3
"""批量探索南京农业大学各学院 - 查找师资入口"""
import asyncio
from playwright.async_api import async_playwright

DEPTS = [
    ("农学院", "http://nx.njau.edu.cn/"),
    ("植物保护学院", "http://plant.njau.edu.cn/"),
    ("园艺学院", "http://yyxy.njau.edu.cn/"),
    ("动物医学院", "http://cvm.njau.edu.cn/"),
    ("动物科技学院", "http://dky.njau.edu.cn/"),
    ("草业学院", "http://cyxy.njau.edu.cn/"),
    ("资源与环境科学学院", "http://re.njau.edu.cn/"),
    ("生命科学学院", "http://lfc.njau.edu.cn/"),
    ("理学院", "http://cos.njau.edu.cn/"),
    ("食品科学技术学院", "http://food.njau.edu.cn/"),
    ("工学院", "http://coe.njau.edu.cn/index.htm"),
    ("信息管理学院", "http://info.njau.edu.cn/"),
    ("智慧农业学院", "http://ai.njau.edu.cn/"),
    ("经济管理学院", "http://economy.njau.edu.cn/"),
    ("公共管理学院", "http://clm.njau.edu.cn/"),
    ("人文与社会发展学院", "http://xrw.njau.edu.cn/"),
    ("外国语学院", "http://foreign.njau.edu.cn/"),
    ("金融学院", "http://finance.njau.edu.cn/"),
    ("马克思主义学院", "http://szb.njau.edu.cn/"),
    ("体育部", "http://sports.njau.edu.cn/"),
    ("前沿交叉研究院", "http://aais.njau.edu.cn/"),
]

async def explore_dept(context, dept_name, dept_url):
    """探索单个学院"""
    page = await context.new_page()
    result = {"name": dept_name, "url": dept_url, "sz_links": [], "title": "", "error": None}

    try:
        await page.goto(dept_url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        result["title"] = await page.title()

        # 提取所有链接文本
        links = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.replace(/\\s+/g, ' ').trim();
                const href = a.href;
                if (text && href && text.length < 40 && !href.startsWith('javascript') && !href.startsWith('#')) {
                    results.push([text, href.substring(0, 150)]);
                }
            });
            return results;
        }""")

        # 找师资相关链接 - 放宽匹配条件
        teacher_kw = ['师资', '导师', '教工', '教师', '队伍', '员工', 'faculty', 'staff', 'teacher',
                     'szdw', 'szll', 'dsdw', 'jzyg', 'teacher']
        for text, href in links:
            if any(kw in text.lower() for kw in teacher_kw):
                result["sz_links"].append((text, href))
            elif any(kw in href.lower() for kw in ['szdw', 'szll', 'jzyg', 'teacher', 'faculty']):
                result["sz_links"].append((text, href))

    except Exception as e:
        result["error"] = str(e)
    finally:
        await page.close()
        return result

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})

        # 并发探索
        tasks = [explore_dept(context, name, url) for name, url in DEPTS]
        results = await asyncio.gather(*tasks)

        print(f"{'学院名称':20s} {'页面标题':30s} {'师资链接数':10s} {'状态'}")
        print("-"*80)
        for r in results:
            title_short = r['title'][:28] if r['title'] else 'N/A'
            status = '❌ ' + (r['error'][:30] if r['error'] else '') if r['error'] else '✅'
            sz_count = len(r['sz_links'])
            print(f"{r['name']:20s} {title_short:30s} {str(sz_count):10s} {status}")

        # 输出有师资链接的详情
        print("\n\n=== 各学院师资链接详情 ===")
        for r in results:
            if r['sz_links']:
                print(f"\n【{r['name']}】")
                for text, href in r['sz_links'][:8]:
                    print(f"  {text:25s} -> {href}")

        await browser.close()

asyncio.run(main())
