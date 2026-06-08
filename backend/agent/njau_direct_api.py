#!/usr/bin/env python3
"""直接调用 NJAU CMS AJAX 端点获取教师数据"""
import asyncio
import json
from playwright.async_api import async_playwright

async def call_api():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})
        page = await context.new_page()

        # 先访问页面，建立cookies/session
        await page.goto('https://plant.njau.edu.cn/zwbhxy_all.jsp?urltype=tree.TreeTempUrl&wbtreeid=1192',
                       wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        # 调用 queryteacher.jsp 获取教师数据
        try:
            # 先查看完整的 queryteacher.js - 寻找loadData方法
            js_text = await page.evaluate("""async () => {
                const resp = await fetch('/system/resource/tsites/portal/queryteacher.js');
                return await resp.text();
            }""")

            # 找 loadData 方法
            loaddata_idx = js_text.find('loadData')
            if loaddata_idx > 0:
                print("=== loadData 方法 ===")
                print(js_text[loaddata_idx:loaddata_idx+2000])
        except Exception as e:
            print(f"获取JS失败: {e}")

        # 尝试直接调用 queryteacher.jsp
        print("\n\n=== 直接调用 queryteacher.jsp ===")
        result = await page.evaluate("""async () => {
            try {
                const params = new URLSearchParams({
                    'viewMode': '8',
                    'showlang': '',
                    'p.teacherName': '',
                    'p.teacherPinyin': '',
                    'p.rankId': '0',
                    'p.collegeId': '1200',
                    'p.disciplineId': '',
                    'p.facultyId': '0',
                    'p.isbd': '0',
                    'p.dutyname': '',
                    'p.dutyid': '0',
                    'p.atschool': '0',
                    'p.pageNum': '1',
                    'p.pageSize': '200',
                    'currpage': '1',
                    'p.sort': '',
                    'p.order': '',
                    'siteOwner': '0',
                    'viewUniqueId': '0'
                });
                const resp = await fetch('/system/resource/tsites/portal/queryteacher.jsp', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'},
                    body: params.toString()
                });
                return await resp.text();
            } catch(e) {
                return 'ERROR: ' + e.toString();
            }
        }""")

        print(result[:3000])

        await browser.close()

asyncio.run(call_api())
