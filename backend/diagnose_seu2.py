"""深度诊断v2：检查问题学院教师详情页为何提取不到邮箱"""
import asyncio
import re
import sys
import json
from playwright.async_api import async_playwright

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

TEST_DEPTS = [
    ("机械工程学院", "https://me.seu.edu.cn/szll/list.htm"),
    ("能源与环境学院", "http://power.seu.edu.cn/9216/list.htm"),
    ("生物科学与医学工程学院", "https://bme.seu.edu.cn/499/list.htm"),
    ("外国语学院", "https://sfl.seu.edu.cn/9851/list.htm"),
    ("化学化工学院", "https://chem.seu.edu.cn/js/list.htm"),
    ("法学院", "https://law.seu.edu.cn/9121/list.htm"),
    ("艺术学院", "https://arts.seu.edu.cn/szdw_25730/list.htm"),
    ("医学院", "https://med.seu.edu.cn/8693/list.htm"),
]

async def diagnose_dept(context, dept_name, list_url):
    print(f"\n{'='*60}")
    print(f"【{dept_name}】{list_url}")
    page = await context.new_page()

    try:
        await page.goto(list_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

        # Get raw links without filtering
        raw_data = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('a').forEach(a => {
                let text = a.textContent.trim().replace(/\\u200b/g, '').replace(/\\u200c/g, '').replace(/\\u200d/g, '').trim();
                const href = (a.href || '').replace(/^http:/, 'https:');
                if (!href || href.startsWith('javascript:') || href === '#') return;

                const cleaned = text.replace(/\\s/g, '');
                if (/^[\\u4e00-\\u9fff]{2,4}$/.test(cleaned)) {
                    results.push({name: cleaned, url: href});
                }
            });
            return results;
        }""")

        print(f"  所有2-4字中文链接: {len(raw_data)}")

        # Filter in Python
        nav_words = {'首页','概况','新闻','通知','公告','招生','培养','就业','学位','学科','科研','学术',
            '党建','工会','校友','捐赠','图书馆','校园','地图','网站','登录','邮箱','联系我们','欢迎',
            '返回','更多','详情','查看','下载','学院','大学','管理','后台','English','人才引进','人才招聘',
            '院长书记','信箱','相关链接','联系方式','学校首页','学校主页','收藏本站','旧版入口','暑期学校',
            '平湖芳草','下载专区','捐赠通道','院长邮箱','院内文档','日本語','标识系统','院系设置','教师教学',
            '技术转移','海外教育','仪器设备','化工时刊','尾页','网站首页','招生信息','教师登录','现任领导',
            '历任领导','办公电话','院长寄语','组织机构','学科建设','历史沿革','学院简介','学院介绍','组织框架',
            '系所设置','学科组织','本院概况','本院简介','学院简况','学院概述','学院架构','快捷入口','深入贯彻',
            '江苏省','学术论文','专利成果','获奖成果','课程改革','牵头学科','学位管理','出国交流','答辩公示',
            '本科生','研究生','学生工作','党群工作','人才培养','科学研究','人才引进','校友天地','合作交流',
            '诚聘英才','拔尖基地','教学管理','本科生培','研究生培','鲁汶国际','项目介绍','电子信息','规章制度',
            '学生自我','教职工','教师教学','发展中心','教师查询','教师风采','专任教师','院士','客座教授',
            '教师简介','兼职教授','离退休','荣休','知名专家','知名学者','全体教师','硕博导师','各系名单',
            '国家高层次','人才','各系名单','管理入口','师资维护','师资修改','个人中心','师资概况','师资力量',
            '师资队伍','师资概览','师资骨干','教师队伍','杰出人才','人才工程','人才职称','教授风采','教授',
            '副教授','讲师','助教','研究员','副研究员','助理教授','助理研究员','高级工程师','工程师','博士后',
            '博士生导师','硕士生导师','博士导师','硕士导师','博导','硕导','在职教师','退休教师','访问学者',
            '实验室','研究中心','学院部门','联系我们','教务系统','中文','关闭此页','学院主页','艺术学院',
            '标识系统','校内办公','网络教学','校园信息','校园卡','电子邮件','图书馆主页','一卡通','财务查询',
            '校园门户','信息服务','网络服务','VPN服务','正版软件','软件下载','校园网','无线网','邮箱系统',
            '信息门户','网上办事','办事大厅','服务大厅','统一身份','认证','一网通办'}
        teacher_links = [l for l in raw_data if l["name"] not in nav_words]

        print(f"  过滤导航词后: {len(teacher_links)}")
        if teacher_links:
            print(f"  前8个: {teacher_links[:8]}")

        # Also check for specific teacher-related sub-list URLs
        sub_lists = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href || '';
                if (href && (text.includes('教授') || text.includes('讲师') || text.includes('研究员') ||
                    text.includes('导师') || text.includes('教师') || text.includes('师资'))) {
                    results.push({text, href});
                }
            });
            return results;
        }""")
        if sub_lists:
            print(f"  子分类链接: {sub_lists[:10]}")

        # Visit first 5 teacher profile pages
        profile_page = await context.new_page()
        for i, entry in enumerate(teacher_links[:5]):
            url = entry["url"]
            name = entry["name"]
            print(f"\n  [{i+1}] 访问: {name} -> {url[:120]}")

            try:
                resp = await profile_page.goto(url, wait_until="domcontentloaded", timeout=12000)
                await asyncio.sleep(1)

                body = await profile_page.evaluate("() => document.body.innerText")
                emails = EMAIL_RE.findall(body)
                has_title = "职称" in body or "教授" in body or "研究员" in body
                preview = body[:400].replace('\n', ' ')

                print(f"    邮箱: {emails if emails else '❌ 无'}, 含职称: {has_title}")
                print(f"    预览: {preview[:250]}")

            except Exception as e:
                print(f"    错误: {e}")

        await profile_page.close()

    except Exception as e:
        print(f"  列表页错误: {e}")
    finally:
        await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        )
        for dept_name, url in TEST_DEPTS:
            await diagnose_dept(context, dept_name, url)
        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
