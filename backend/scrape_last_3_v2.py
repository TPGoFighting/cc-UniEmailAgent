"""爬取最后3个院系 v2 — 在内容区域搜索教师姓名链接"""
import asyncio
import re
import csv
import random
from datetime import datetime
from pathlib import Path
from collections import Counter

# 每个院系的子页面
DEPT_PAGES = {
    "环境学院": [
        ("院士", "http://hjxy.nju.edu.cn/szdw/ys/index.html"),
        ("环境科学系", "http://hjxy.nju.edu.cn/szdw/hjkxx/index.html"),
        ("环境工程系", "http://hjxy.nju.edu.cn/szdw/hjgcx/index.html"),
        ("环境规划与管理系", "http://hjxy.nju.edu.cn/szdw/hjghyglx/index.html"),
        ("研究系列人员", "http://hjxy.nju.edu.cn/szdw/yjxl/index.html"),
    ],
    "大气科学学院": [
        ("师资队伍", "https://as.nju.edu.cn/szdw/list.htm"),
        ("教授", "https://as.nju.edu.cn/js/list.htm"),
        ("副教授", "https://as.nju.edu.cn/fjs/list.htm"),
    ],
    "地理与海洋科学学院": [
        ("师资队伍", "https://sgos.nju.edu.cn/szdw/list.htm"),
    ],
}

OUTPUT_DIR = Path(__file__).parent / "outputs"
PAGE_TIMEOUT = 25000
PROFILE_TIMEOUT = 12000
MAX_PER_PAGE = 60

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

NAV_BLACKLIST = {
    "首页","返回","后退","前进","学院概况","学院简介","学院介绍","学院首页",
    "历史沿革","组织机构","组织架构","现任领导","院长致辞","院系领导",
    "师资队伍","教师名录","现任教师","在职教师","退休教师","荣休教师","荣休教工",
    "院士","教授","副教授","讲师","研究员","研究系列","准聘副教授","准聘助理教授",
    "人才队伍","跨学科博导","研究系列人员","行政与实验技术人员",
    "人才培养","本科教育","研究生教育","博士生","硕士生","留学生",
    "科学研究","学术研究","科研团队","研究方向","科技进展","获奖成果",
    "党建工会","党建动态","通知公告","规章制度","学习园地",
    "学工园地","学生工作","就业信息",
    "国际交流","国际合作","国际环境科学中心",
    "平台基地","全国重点实验室","国家级实验教学中心",
    "诚聘英才","招聘信息","校友天地","校友之窗",
    "English","中文","英文",
    "下载中心","联系我们","院内办公","绩效系统",
    "EEH期刊","BECT亚洲编辑部","RES期刊",
    "南京大学","环境学院","大气科学","地理与海洋",
    "环境科学系","环境工程系","环境规划与管理系",
    "相关链接","版权所有",
}

BAD_EMAIL_PREFIXES = {
    "wxyxz","xwcb","bgs","office","yuanban","webmaster",
    "admin","info","master","root","postmaster","njudz","bnhy",
}

def is_person_name(name):
    name = name.strip()
    if name in NAV_BLACKLIST:
        return False
    if not re.match(r'^[一-鿿]{2,4}$', name):
        return False
    # 额外检查：包含典型导航字
    nav = set('首页院系部教学科研学术师资教师学生校友新闻通知公告招生培养'
              '学位管理就业党建党群党委工会团委行政下载资源资料国际'
              '交流合作招聘财务网络安全采购联系登录注册简介概况介绍'
              '设置导航地图链接友情版权中心项目论坛讲座动态公报布告'
              '公示规章制度细则方案计划大纲课程精品培育创新实践实验'
              '基地平台实验室机构专栏展览年鉴论文成果奖励基金办公部门'
              '队伍名录主页主题办事指南监督信箱教研职工作党团大学'
              '绩效办公环境大气科学地理海洋')
    for ch in name:
        if ch in nav:
            return False
    return True

def is_bad_email(email):
    if not email: return False
    local = email.lower().split("@")[0]
    if any(local.startswith(p) for p in BAD_EMAIL_PREFIXES):
        return True
    if len(local) <= 2 and local.isalpha():
        return True
    return False


async def scrape_page(page, context, dept_name, sub_name, url):
    """爬取单个子页面上的教师。"""
    results = []
    try:
        await page.goto(url, wait_until="networkidle", timeout=PAGE_TIMEOUT)
    except:
        print(f"    无法访问 {url}")
        return results
    await asyncio.sleep(2)

    # 在内容区域查找教师姓名链接
    entries = await page.evaluate("""() => {
        const navSet = new Set(['首页','返回','后退','前进','学院概况','学院简介','学院介绍',
            '学院首页','历史沿革','组织机构','组织架构','现任领导','院长致辞','院系领导',
            '师资队伍','教师名录','现任教师','在职教师','退休教师','荣休教师','荣休教工',
            '院士','教授','副教授','讲师','研究员','研究系列','准聘副教授','准聘助理教授',
            '人才队伍','跨学科博导','研究系列人员','行政与实验技术人员','人才培养','本科教育',
            '研究生教育','博士生','硕士生','留学生','科学研究','学术研究','科研团队',
            '研究方向','科技进展','获奖成果','党建工会','党建动态','通知公告','规章制度',
            '学习园地','学工园地','学生工作','就业信息','国际交流','国际合作',
            '国际环境科学中心','平台基地','全国重点实验室','国家级实验教学中心',
            '诚聘英才','招聘信息','校友天地','校友之窗','English','中文','英文',
            '下载中心','联系我们','院内办公','绩效系统','EEH期刊','BECT亚洲编辑部',
            'RES期刊','南京大学','环境学院','大气科学','地理与海洋','环境科学系',
            '环境工程系','环境规划与管理系','相关链接','版权所有',
            '培养方案','硕博连读','创新实践','实践活动','学位论文','答辩公告',
            '教务通知','学籍管理','课程表','考试安排','教学大纲','教学成果',
            '学科建设','重点学科','双一流','985','211',
        ]);

        const entries = [];
        const seen = new Set();

        // 查找所有a标签中的人名
        document.querySelectorAll('a').forEach(a => {
            const text = (a.textContent || '').trim();
            const href = a.href || '';
            if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;
            if (seen.has(href)) return;
            if (href.includes('beian.miit.gov.cn')) return;
            if (href.endsWith('.pdf') || href.endsWith('.doc')) return;

            // 必须是2-4个汉字的人名
            if (!/^[\\u4e00-\\u9fff]{2,4}$/.test(text)) return;
            if (navSet.has(text)) return;

            seen.add(href);
            entries.push({name: text, url: href});
        });

        return entries.slice(0, 60);
    }""")

    if not entries:
        return results

    print(f"    {sub_name}: 找到{len(entries)}个教师链接")

    # 去重（可能同名不同人，按URL去重）
    seen_urls = set()
    unique = []
    for e in entries:
        if e["url"] not in seen_urls:
            seen_urls.add(e["url"])
            unique.append(e)
    entries = unique

    # 访问每个教师详情页
    for i, entry in enumerate(entries[:MAX_PER_PAGE]):
        try:
            p2 = await context.new_page()
            try:
                await p2.goto(entry["url"], wait_until="domcontentloaded", timeout=PROFILE_TIMEOUT)
                await asyncio.sleep(0.5)
                text = await p2.evaluate("() => document.body.innerText || ''")

                # 提取邮箱
                mails = set(EMAIL_RE.findall(text))
                mtos = await p2.evaluate("""() => {
                    const e=[];
                    document.querySelectorAll('a[href^="mailto:"]').forEach(a => {
                        const m = a.getAttribute('href').replace('mailto:','').split('?')[0].trim();
                        if (m) e.push(m);
                    });
                    return e;
                }""")
                mails.update(mtos)

                valid = [e for e in mails if EMAIL_RE.match(e) and not is_bad_email(e)]

                # 提取职称
                title = ""
                for t in ["教授", "副教授", "助理教授", "准聘副教授", "准聘助理教授",
                          "讲师", "研究员", "副研究员", "助理研究员",
                          "工程师", "高级工程师", "院士", "博导", "硕导",
                          "长江学者", "杰青", "优青", "青年学者"]:
                    if t in text and not title:
                        title = t
                        break

                results.append({
                    "name": entry["name"],
                    "email": valid[0] if valid else "",
                    "department": dept_name,
                    "title": title,
                    "url": entry["url"],
                })
                status = "✅" if valid else "❌"
                print(f"    [{i+1:2d}] {entry['name']:4s} {status}")

            finally:
                await p2.close()
        except Exception as e:
            print(f"    [{i+1:2d}] {entry['name']:4s} ❌异常: {str(e)[:40]}")
            results.append({
                "name": entry["name"],
                "email": "",
                "department": dept_name,
                "title": "",
                "url": entry["url"],
            })

    return results


async def main():
    print(f"[{datetime.now():%H:%M:%S}] 🚀 最后3院系 v2")

    all_results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        for dept_name, sub_pages in DEPT_PAGES.items():
            print(f"\n{'='*50}")
            print(f"[{datetime.now():%H:%M:%S}] 🏫 {dept_name}")
            dept_results = []

            for sub_name, sub_url in sub_pages:
                results = await scrape_page(page, context, dept_name, sub_name, sub_url)
                dept_results.extend(results)

            # 去重
            seen = set()
            unique = []
            for r in dept_results:
                if r["url"] not in seen:
                    seen.add(r["url"])
                    unique.append(r)

            em = sum(1 for r in unique if r["email"])
            print(f"  📊 {dept_name}: {len(unique)}位教师, {em}有邮箱")
            all_results.extend(unique)

        await context.close()
        await browser.close()

    # 最终过滤
    before = len(all_results)
    all_results = [r for r in all_results if is_person_name(r["name"])]
    print(f"\n过滤: {before} → {len(all_results)}")

    # 保存
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"南京大学_最后3院系_{ts}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["序号", "姓名", "邮箱", "学院", "职称", "主页链接"])
        for i, r in enumerate(all_results, 1):
            w.writerow([i, r["name"], r["email"], r["department"], r["title"], r["url"]])

    print(f"CSV: {csv_path}")
    for d in DEPT_PAGES:
        cnt = sum(1 for r in all_results if r["department"] == d)
        ec = sum(1 for r in all_results if r["department"] == d and r["email"])
        print(f"  {d}: {cnt}人, {ec}邮箱")


if __name__ == "__main__":
    from playwright.async_api import async_playwright
    asyncio.run(main())
