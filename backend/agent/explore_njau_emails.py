#!/usr/bin/env python3
"""全面检查 NJAU 各学院页面中的邮箱"""
import asyncio
import re
from playwright.async_api import async_playwright

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# 所有学院的师资页面
ALL_DEPTS = [
    ("农学院", "https://nx.njau.edu.cn/jsfc_nxx.jsp?urltype=tree.TreeTempUrl&wbtreeid=1227"),
    ("植保学院", "https://plant.njau.edu.cn/zwbhxy_all.jsp?urltype=tree.TreeTempUrl&wbtreeid=1192"),
    ("园艺-果树", "https://yyxy.njau.edu.cn/szdw/gsxk.htm"),
    ("园艺-蔬菜", "https://yyxy.njau.edu.cn/szdw/scxk.htm"),
    ("园艺-茶学", "https://yyxy.njau.edu.cn/szdw/cxxk.htm"),
    ("园艺-观赏园艺", "https://yyxy.njau.edu.cn/szdw/gsyyxk.htm"),
    ("园艺-中药", "https://yyxy.njau.edu.cn/szdw/zyxk.htm"),
    ("园艺-设施园艺", "https://yyxy.njau.edu.cn/szdw/ssyyxk.htm"),
    ("园艺-风景园林", "https://yyxy.njau.edu.cn/szdw/fjylxk.htm"),
    ("动物医学院", "https://cvm.njau.edu.cn/xksz/szdw.htm"),
    ("动物科技学院", "https://dky.njau.edu.cn/xksz/jsml.htm"),
    ("草业学院", "https://cyxy.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1348"),
    ("资环学院", "https://re.njau.edu.cn/jsfc2.jsp?urltype=tree.TreeTempUrl&wbtreeid=1325"),
    ("生命科学学院", "https://lfc.njau.edu.cn/szdw.htm"),
    ("理学院", "https://cos.njau.edu.cn/szdw3/szdw2/js.htm"),
    ("食品学院", "https://food.njau.edu.cn/szdw/zrjs1/azcfl.htm"),
    ("工学院", "https://coe.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1140"),
    ("信息管理", "https://info.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1076"),
    ("智慧农业", "https://ai.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1164"),
    ("经济管理学院", "https://economy.njau.edu.cn/xksz/szdw1/nyjjxx.htm"),
    ("公共管理学院", "https://clm.njau.edu.cn/2022/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1480"),
    ("人文学院", "https://xrw.njau.edu.cn/szdw/kxjssx.htm"),
    ("外国语学院", "https://foreign.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1124"),
    ("金融学院", "https://finance.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1230"),
    ("马克思主义", "https://szb.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1143"),
    ("体育部", "https://sports.njau.edu.cn/szdw/szdw.htm"),
    ("前沿交叉", "https://aais.njau.edu.cn/szll.htm"),
]

async def check_page(context, label, url):
    page = await context.new_page()
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        text = await page.evaluate("() => document.body.innerText")

        # 提取邮箱
        emails = EMAIL_RE.findall(text)
        # 去重
        unique_emails = list(set(emails))

        # 过滤掉明显非教师的邮箱
        student_emails = [e for e in unique_emails if 'stu.' in e or 'student' in e]
        teacher_emails = [e for e in unique_emails if e not in student_emails]

        # 查找教师名
        teacher_names = re.findall(r'(?:(?:^|\n)\s*([一-鿿]{2,4})\s*(?:\n|$))', text)
        # 过滤导航词
        NAV_KW = {'首页','学院概况','简介','领导','机构','联系','师资队伍','学科','研究',
                  '通知','公告','新闻','招生','就业','搜索','English','收藏','登录','注册',
                  '返回','更多','详情','查看','下载','硕士','本科','行政','管理','教职',
                  '荣休','访问','党建','工会','校友','捐赠','网站','地图','人才培养',
                  '科学研究','合作交流','社会服务','学校概况','学科建设','全部','导师',
                  '在职','兼职','专任','离退休','教工','队伍','博士后','实验','教辅',
                  '当前位置','设置','学院','首页','首页','首页','师资队伍'}
        real_names = [n for n in teacher_names if n not in NAV_KW and n not in '师资队伍']

        await page.close()
        return {"label": label, "url": url, "emails": unique_emails, "teacher_emails": teacher_emails, "names_found": len(real_names)}

    except Exception as e:
        await page.close()
        return {"label": label, "url": url, "emails": [], "error": str(e)}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})

        tasks = [check_page(context, label, url) for label, url in ALL_DEPTS]
        results = await asyncio.gather(*tasks)

        print(f"{'学院':20s} {'教师名数':8s} {'邮箱数':6s} {'教师邮箱':10s}")
        print("-"*60)
        total_emails = 0
        for r in results:
            email_str = str(len(r.get('emails', [])))
            teacher_email_str = str(len(r.get('teacher_emails', [])))
            print(f"{r['label']:20s} {str(r.get('names_found', 0)):8s} {email_str:6s} {teacher_email_str:10s}")
            total_emails += len(r.get('emails', []))

        # 输出具体邮箱
        print("\n\n=== 各学院邮箱详情 ===")
        for r in results:
            if r.get('emails'):
                print(f"\n【{r['label']}】({r['url']})")
                for e in r['emails'][:10]:
                    print(f"  {e}")
                if len(r['emails']) > 10:
                    print(f"  ... 还有 {len(r['emails'])-10} 个")

        print(f"\n总计: {total_emails} 邮箱")

        await browser.close()

asyncio.run(main())
