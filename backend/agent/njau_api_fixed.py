#!/usr/bin/env python3
"""正确调用 NJAU CMS API 获取教师数据"""
import asyncio, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})
        page = await context.new_page()

        await page.goto('https://plant.njau.edu.cn/zwbhxy_all.jsp?urltype=tree.TreeTempUrl&wbtreeid=1192',
                       wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        # 使用页面JS上下文调用 queryteacher.jsp - 使用正确的参数格式
        result = await page.evaluate("""async () => {
            const url = '/system/resource/tsites/portal/queryteacher.jsp';
            const param = 'collegeid=1200&isshowpage=false&rankid=0&isbd=0&pageindex=1&pagesize=500&viewmode=8&siteOwner=0&viewUniqueId=0&atschool=0';
            const resp = await fetch(url + '?' + param);
            const data = await resp.json();
            return data;
        }""")

        print(f"总记录: {result.get('totalnum', 0)}, 总页数: {result.get('totalpage', 0)}")
        teachers = result.get('teacherData', [])
        print(f"教师数: {len(teachers)}")
        if teachers:
            print(f"\n教师数据结构键: {list(teachers[0].keys())}")
            print(f"\n前3个教师:")
            for t in teachers[:3]:
                print(json.dumps(t, ensure_ascii=False, indent=2)[:300])

        await browser.close()

asyncio.run(main())
