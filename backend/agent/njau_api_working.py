#!/usr/bin/env python3
"""用正确参数调用 NJAU CMS API"""
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

        # 用正确的配置调用 API
        result = await page.evaluate("""async () => {
            const url = '/system/resource/tsites/portal/queryteacher.jsp';
            const params = {
                collegeid: 1200,
                isshowpage: 'false',
                rankid: 0,
                isbd: 0,
                pageindex: 1,
                pagesize: 500,
                viewmode: 10,
                siteOwner: 1344680794,
                viewUniqueId: 'u10',
                viewId: 1094620,
                atschool: 0,
                actiontype: 'advancesearch',
                showlang: 'zh_CN',
                login: '',
                profilelen: 100,
                ellipsis: '...',
                honorid: 0,
                pinyin: '',
                teacherName: '',
                searchDirection: '',
                facultyid: 0,
                disciplineid: '',
                rankcode: '',
                ranklevel: '',
                jobtypecode: '',
                enrollid: 0,
                postdutyid: 0,
                postdutyname: '',
                viewOwner: ''
            };
            const paramStr = Object.entries(params).map(([k,v]) => k+'='+encodeURIComponent(v)).join('&');
            const resp = await fetch(url + '?' + paramStr);
            return await resp.json();
        }""")

        print(f"总记录: {result.get('totalnum', 0)}, 总页数: {result.get('totalpage', 0)}")
        teachers = result.get('teacherData', [])
        print(f"教师数: {len(teachers)}")
        if teachers:
            print(f"\n教师数据结构键: {list(teachers[0].keys())}")
            print(f"\n前5个教师:")
            for t in teachers[:5]:
                print(json.dumps(t, ensure_ascii=False, indent=2)[:500])

        await browser.close()

asyncio.run(main())
