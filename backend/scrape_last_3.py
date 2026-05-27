"""快速爬取最后3个院系：环境学院、地理与海洋科学学院、大气科学学院"""
import asyncio
import re
import csv
import json
import random
from datetime import datetime
from pathlib import Path
from collections import Counter

TARGET_DEPTS = {
    "环境学院": "https://hjxy.nju.edu.cn",
    "大气科学学院": "https://as.nju.edu.cn",
    "地理与海洋科学学院": "https://sgos.nju.edu.cn",
}

OUTPUT_DIR = Path(__file__).parent / "outputs"
PAGE_TIMEOUT = 25000
PROFILE_TIMEOUT = 12000
MAX_TEACHERS = 50

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

NAV_BLACKLIST = {
    "首页", "返回", "学院概况", "学院简介", "院况概览", "历史沿革", "组织机构",
    "师资队伍", "教师名录", "现任教师", "在职教师", "退休教师", "专任教师",
    "教授", "副教授", "讲师", "研究员", "两院院士", "研究系列",
    "人才培养", "本科生", "研究生", "博士生", "硕士生", "博士后",
    "科学研究", "学术研究", "科研成果", "科研项目", "科研奖励",
    "新闻动态", "通知公告", "学术交流", "国际合作", "招生就业",
    "党建工作", "党群工作", "学生工作", "学工园地", "校友天地",
    "下载中心", "联系我们", "English", "中文",
}

def is_person_name(name):
    name = name.strip()
    if name in NAV_BLACKLIST:
        return False
    if not re.match(r'^[一-鿿]{2,4}$', name):
        return False
    nav_chars = set('首页学院系院教学科研学术师资教师学生校友新闻通知公告招生培养'
                    '学位管理就业党建党群党委工会团委行政下载资源资料国际交流'
                    '合作招聘财务网络安全采购联系登录注册简介概况介绍设置导航'
                    '地图链接友情版权中心项目论坛讲座动态公报布告公示规章制度细则'
                    '方案计划大纲课程精品培育创新实践实验基地平台实验室机构专栏'
                    '展览年鉴论文成果奖励基金办公部门组织队伍名录主页主题办事指南'
                    '监督信箱教研职工作党团大学')
    for ch in name:
        if ch in nav_chars:
            return False
    return True

def is_bad_email(email):
    if not email:
        return False
    bad_prefixes = {"wxyxz", "xwcb", "bgs", "office", "yuanban", "webmaster",
                    "admin", "info", "master", "root", "postmaster", "njudz"}
    local = email.lower().split("@")[0]
    if any(local.startswith(p) for p in bad_prefixes):
        return True
    if len(local) <= 2 and local.isalpha() and "@nju.edu.cn" in email.lower():
        return True
    return False


async def scrape_one(page, context, dept_name, dept_url):
    print(f"\n[{datetime.now():%H:%M:%S}] 🏫 {dept_name}")
    try:
        await page.goto(dept_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
    except:
        print(f"  ❌ 无法访问")
        return []
    await asyncio.sleep(1.5 + random.random())

    # 找师资入口
    flinks = await page.evaluate("""() => {
        const r = [];
        const kw = ['师资','教师','faculty','staff','人员','名录','szdw','js','person'];
        document.querySelectorAll('a').forEach(a => {
            const t = a.textContent.trim(), h = (a.href||'').toLowerCase();
            for (const k of kw) if (t.includes(k)||h.includes(k)) {
                r.push({text:t, href:a.href}); break;
            }
        });
        return r.slice(0, 6);
    }""")

    results = []
    for fl in flinks[:4]:
        target = fl["href"]
        print(f"  尝试: {fl['text']}")

        try:
            await page.goto(target, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        except:
            continue
        await asyncio.sleep(1.5)

        # 提取教师条目
        entries = await page.evaluate("""() => {
            const navSet = new Set(['首页','返回','学院概况','学院简介','学院概况',
                '院况概览','历史沿革','组织机构','师资队伍','教师名录','现任教师',
                '在职教师','退休教师','专任教师','教授','副教授','讲师','研究员',
                '两院院士','研究系列','人才培养','本科生','研究生','博士生','硕士生',
                '博士后','科学研究','学术研究','科研成果','科研项目','科研奖励',
                '新闻动态','通知公告','学术交流','国际合作','招生就业','党建工作',
                '党群工作','学生工作','学工园地','校友天地','下载中心','联系我们',
                'English','中文']);
            const entries = [], seen = new Set();

            // 在表格中查找
            document.querySelectorAll('table tr').forEach(row => {
                const links = row.querySelectorAll('a');
                const cells = row.querySelectorAll('td, th');
                if (links.length >= 1 && cells.length >= 2) {
                    const a = links[0];
                    const text = (a.textContent||'').trim();
                    const href = a.href||'';
                    if (!href||seen.has(href)||navSet.has(text)) return;
                    if (!/^[\\u4e00-\\u9fff]{2,4}$/.test(text)) return;
                    seen.add(href);
                    let title = '';
                    for (let i=1;i<Math.min(cells.length,5);i++) {
                        const m = (cells[i].textContent||'').match(/(教授|副教授|助理教授|讲师|研究员|副研究员|助理研究员|工程师|院士)/);
                        if (m) {title=m[1]; break;}
                    }
                    entries.push({name:text, url:href, title});
                }
            });

            // li列表
            if (entries.length <= 2) {
                document.querySelectorAll('div.teacher-list li, ul.teacher-list li, div.member, div.faculty-member').forEach(item => {
                    const a = item.querySelector('a');
                    if (!a||!a.href||seen.has(a.href)) return;
                    const text = (a.textContent||'').trim();
                    if (!/^[\\u4e00-\\u9fff]{2,4}$/.test(text)||navSet.has(text)) return;
                    seen.add(a.href);
                    const m = (item.textContent||'').match(/(教授|副教授|讲师|研究员|工程师|院士)/);
                    entries.push({name:text, url:a.href, title: m?m[1]:''});
                });
            }
            return entries.slice(0, 60);
        }""")

        if len(entries) < 3:
            continue

        print(f"    找到 {len(entries)} 个条目")

        for i, entry in enumerate(entries[:MAX_TEACHERS]):
            try:
                p2 = await context.new_page()
                try:
                    await p2.goto(entry["url"], wait_until="domcontentloaded", timeout=PROFILE_TIMEOUT)
                    await asyncio.sleep(0.5)
                    text = await p2.evaluate("() => document.body.innerText || ''")
                    mails = set(EMAIL_RE.findall(text))
                    # 也检查mailto
                    mtos = await p2.evaluate("""() => {
                        const e=[]; document.querySelectorAll('a[href^="mailto:"]').forEach(a => {
                            const m=a.getAttribute('href').replace('mailto:','').split('?')[0].trim();
                            if(m) e.push(m);
                        }); return e;
                    }""")
                    mails.update(mtos)
                    valid = [e for e in mails if EMAIL_RE.match(e) and not is_bad_email(e)]
                    title = entry.get("title","")
                    if not title:
                        tm = re.search(r'(教授|副教授|助理教授|讲师|研究员|副研究员|工程师|院士|博导|硕导)', text)
                        if tm: title = tm.group(1)

                    results.append({
                        "name": entry["name"], "email": valid[0] if valid else "",
                        "department": dept_name, "title": title, "url": entry["url"]
                    })
                    print(f"    [{i+1:2d}] {entry['name']:4s} {'✅' if valid else '❌'}")
                finally:
                    await p2.close()
            except:
                pass

        if len(results) >= 10:
            break

    return results


async def main():
    all_results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        for name, url in TARGET_DEPTS.items():
            results = await scrape_one(page, context, name, url)
            all_results.extend(results)
            print(f"  📊 {name}: {len(results)}人, {sum(1 for r in results if r['email'])}邮箱")

        await context.close()
        await browser.close()

    # 过滤非人名
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
    for d in TARGET_DEPTS:
        cnt = sum(1 for r in all_results if r["department"] == d)
        ecnt = sum(1 for r in all_results if r["department"] == d and r["email"])
        print(f"  {d}: {cnt}人, {ecnt}邮箱")

if __name__ == "__main__":
    from playwright.async_api import async_playwright
    asyncio.run(main())
