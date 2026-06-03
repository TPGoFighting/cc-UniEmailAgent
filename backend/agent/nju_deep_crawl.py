"""
南京大学全学院深度爬虫 v2
策略：访问各个学院的师资队伍页面 -> 提取教师列表 -> 访问详情页提取邮箱
"""

import asyncio
import csv
import os
import re
import sys
from datetime import datetime
from playwright.async_api import async_playwright

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
ANTI_SPAM = [(r'\[at\]', '@'), (r'\(at\)', '@'), (r'#@', '@'),
             (r'\[@\]', '@'), (r'\(@\)', '@'), (r'\s*at\s*', '@')]
NAME_RE = re.compile(r'^[一-鿿]{2,4}$')

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
TASK_ID = os.environ.get("TASK_ID", "nju_deep_crawl")
TASK_DIR = os.path.join(OUTPUT_DIR, TASK_ID)
os.makedirs(TASK_DIR, exist_ok=True)

PUBLIC_EMAIL_PREFIXES = ['webmaster', 'admin', 'office', 'info', 'master', 'root',
                        'postmaster', 'bgs', 'dangzheng', 'yuanban', 'wxyxz', 'xwcb']

def restore_email(text):
    if not text: return None
    for p, r in ANTI_SPAM:
        text = re.sub(p, r, text, flags=re.IGNORECASE)
    m = EMAIL_RE.search(text)
    return m.group(0) if m else None

def is_public_email(email):
    if not email: return True
    prefix = email.split('@')[0].lower()
    for p in PUBLIC_EMAIL_PREFIXES:
        if p in prefix: return True
    return False

def extract_name(text):
    if not text: return None
    text = text.strip()
    if NAME_RE.match(text): return text
    m = re.search(r'[一-鿿]{2,4}', text)
    return m.group(0) if m else None

def extract_title(text):
    if not text: return None
    titles = ['教授/博导', '副教授/硕导', '教授级高级工程师',
              '教授', '副教授', '讲师', '助教',
              '研究员', '副研究员', '助理研究员',
              '高级工程师', '工程师',
              '博士后', '助理教授', '准聘助理教授', '准聘副教授',
              '主任医师', '副主任医师', '主治医师',
              '高级实验师', '实验师',
              '馆员', '副研究馆员', '研究馆员',
              '编辑', '副编审', '编审']
    for t in titles:
        if t in text: return t
    return None

# 学院配置：从探测结果提取的师资页面入口
COLLEGE_CONFIG = [
    # (学院名, 师资页URL列表, 首页URL)
    ("文学院", [
        "https://chin.nju.edu.cn/szdw/index.html",
        "https://chin.nju.edu.cn/szdw/xrjs/index.html",
        "https://chin.nju.edu.cn/szdw/txjs/index.html",
    ], "http://chin.nju.edu.cn/"),
    ("历史学院", [
        "https://history.nju.edu.cn/28475/list.htm",
        "https://history.nju.edu.cn/28476/list.htm",
    ], "http://history.nju.edu.cn/"),
    ("哲学学院", [
        "https://philo.nju.edu.cn/4712/list.htm",
        "https://philo.nju.edu.cn/4684/list.htm",
    ], "http://philo.nju.edu.cn/"),
    ("新闻传播学院", [
        "https://jc.nju.edu.cn/jzyg/zzjs.htm",
        "https://jc.nju.edu.cn/jzyg/rxjs.htm",
    ], "http://jc.nju.edu.cn/"),
    ("法学院", [
        "https://law.nju.edu.cn/szdw/zzjs1/js.htm",
        "https://law.nju.edu.cn/szdw/rxjs.htm",
    ], "https://law.nju.edu.cn/"),
    ("商学院", [
        "https://nubs.nju.edu.cn/8878/list.htm",
        "https://nubs.nju.edu.cn/8879/list.htm",
        "https://nubs.nju.edu.cn/8880/list.htm",
        "https://nubs.nju.edu.cn/8881/list.htm",
    ], "https://nubs.nju.edu.cn/"),
    ("外国语学院", [
        "https://sfs.nju.edu.cn/szdw/index.html",
    ], "http://sfs.nju.edu.cn/"),
    ("政府管理学院", [
        "https://public.nju.edu.cn/szdw",
    ], "http://public.nju.edu.cn/"),
    ("国际关系学院", [
        "https://sis.nju.edu.cn/jsrk/list.htm",
    ], "https://sis.nju.edu.cn/"),
    ("信息管理学院", [
        "https://im.nju.edu.cn/szll/zzjs.htm",
        "https://im.nju.edu.cn/szll/rxry.htm",
    ], "http://im.nju.edu.cn/"),
    ("社会学院", [
        "https://sociology.nju.edu.cn/xsjs/list.htm",
        "https://sociology.nju.edu.cn/szdw/list.htm",
        "https://sociology.nju.edu.cn/qzjs/list.htm",
    ], "http://sociology.nju.edu.cn/"),
    ("数学学院", [
        "https://math.nju.edu.cn/jzyg/index.html",
    ], "http://math.nju.edu.cn/"),
    ("物理学院", [
        "https://physics.nju.edu.cn/szdw/index.html",
        "https://physics.nju.edu.cn/szdw/qbmd/index.html",
    ], "http://physics.nju.edu.cn/"),
    ("天文与空间科学学院", [
        "https://astronomy.nju.edu.cn/szll/szgk/index.html",
        "https://astronomy.nju.edu.cn/szll/index.html",
    ], "http://astronomy.nju.edu.cn/"),
    ("化学化工学院", [
        "https://chem.nju.edu.cn/szll/list.htm",
        "https://chem.nju.edu.cn/12552/list.htm",
    ], "http://chem.nju.edu.cn/"),
    ("计算机学院", [
        "https://cs.nju.edu.cn/1651/list.htm",
        "https://cs.nju.edu.cn/2639/list.htm",
        "https://cs.nju.edu.cn/2640/list.htm",
    ], "http://cs.nju.edu.cn/"),
    ("软件学院", [
        "https://software.nju.edu.cn/szll/szdw/index.html",
        "https://software.nju.edu.cn/szll/index.html",
    ], "http://software.nju.edu.cn/"),
    ("人工智能学院", [
        "https://ai.nju.edu.cn/people/list.htm",
        "https://ai.nju.edu.cn/17804/list.htm",
    ], "http://ai.nju.edu.cn/"),
    ("电子科学与工程学院", [
        "https://ese.nju.edu.cn/22542/list.htm",
        "http://ese.nju.edu.cn/22542/list.htm",
    ], "http://ese.nju.edu.cn/"),
    ("现代工程与应用科学学院", [
        "https://eng.nju.edu.cn/43271/list.htm",
        "https://eng.nju.edu.cn/4911/list.htm",
    ], "http://eng.nju.edu.cn/"),
    ("环境学院", [
        "http://hjxy.nju.edu.cn/szdw/index.html",
        "http://hjxy.nju.edu.cn/szdw/rcdw/index.html",
    ], "http://hjxy.nju.edu.cn/"),
    ("地球科学与工程学院", [
        "https://es.nju.edu.cn/25235/list.htm",
        "https://es.nju.edu.cn/35665/list.htm",
        "https://es.nju.edu.cn/35666/list.htm",
    ], "http://es.nju.edu.cn/"),
    ("地理与海洋科学学院", [
        "http://sgos.nju.edu.cn/62681/list.htm",
        "https://sgos.nju.edu.cn/rxjs/list.htm",
    ], "http://sgos.nju.edu.cn/"),
    ("大气科学学院", [
        "http://as.nju.edu.cn/js/list.htm",
    ], "http://as.nju.edu.cn/"),
    ("生命科学学院", [
        "https://life.nju.edu.cn/szdw/list.htm",
    ], "http://life.nju.edu.cn/"),
    ("医学院", [
        "https://med.nju.edu.cn/10649/list.htm",
        "https://med.nju.edu.cn/10872/list.htm",
    ], "http://med.nju.edu.cn/"),
    ("工程管理学院", [
        "https://sme.nju.edu.cn/xssz/list.htm",
        "https://sme.nju.edu.cn/2003/list.htm",
    ], "http://sme.nju.edu.cn/"),
    ("匡亚明学院", [
        "https://dii.nju.edu.cn/rcpy/list.htm",
        "https://dii.nju.edu.cn/kyds/list.htm",
    ], "http://dii.nju.edu.cn/"),
    ("建筑与城市规划学院", [
        "http://arch.nju.edu.cn/szdw/index.html",
        "http://arch.nju.edu.cn/szdw/js/index.html",
        "http://arch.nju.edu.cn/szdw/fjs/index.html",
    ], "http://arch.nju.edu.cn/"),
    ("马克思主义学院", [
        "https://marxism.nju.edu.cn/szdw.htm",
        "https://marxism.nju.edu.cn/szdw/js.htm",
    ], "http://marxism.nju.edu.cn/"),
    ("艺术学院", [
        "https://art.nju.edu.cn/55208/list.htm",
        "https://art.nju.edu.cn/zzjs/list.htm",
        "https://art.nju.edu.cn/jzjs/list.htm",
    ], "http://art.nju.edu.cn/"),
    ("智能科学与技术学院", [
        "https://is.nju.edu.cn/57159/list.htm",
    ], "https://is.nju.edu.cn/main.htm"),
    ("智能软件与工程学院", [
        "https://ise.nju.edu.cn/szll/zjzjs.htm",
    ], "https://ise.nju.edu.cn/"),
    ("集成电路学院", [
        "https://ic.nju.edu.cn/56606/list.htm",
        "https://ic.nju.edu.cn/zzjs/list.htm",
    ], "https://ic.nju.edu.cn/main.htm"),
    ("数字经济与管理学院", [
        "https://sdem.nju.edu.cn/56976/list.htm",
        "https://sdem.nju.edu.cn/56977/list.htm",
    ], "https://sdem.nju.edu.cn/main.htm"),
    ("能源与资源学院", [
        "https://sser.nju.edu.cn/xygk1/xzdw.htm",
        "https://sser.nju.edu.cn/szll.htm",
    ], "https://sser.nju.edu.cn/"),
    ("机器人与自动化学院", [
        "https://ra.nju.edu.cn/szll/index.html",
        "https://ra.nju.edu.cn/szll/zzjs/index.html",
    ], "https://ra.nju.edu.cn/"),
    ("前沿科学学院", [
        "http://frontier.nju.edu.cn/zrjs/list.htm",
    ], "https://frontier.nju.edu.cn/main.htm"),
    ("生物医学工程学院", [
        "https://bme.nju.edu.cn/szll/index.html",
        "https://bme.nju.edu.cn/szll/zzjs/index.html",
    ], "https://bme.nju.edu.cn/"),
    ("教育研究院·陶行知教师教育学院", [
        "https://edu.nju.edu.cn/8746/list.htm",
        "https://edu.nju.edu.cn/ds/list.htm",
    ], "http://edu.nju.edu.cn/"),
    ("海外教育学院", [
        "https://hwxy.nju.edu.cn/szdw/index.html",
    ], "http://hwxy.nju.edu.cn/"),
    ("大学外语部", [
        "https://dafls.nju.edu.cn/07/dd/c13168a460765/page.htm",
    ], "http://dafls.nju.edu.cn/"),
    ("南京赫尔辛基大气与地球系统科学学院", [
        "https://nh.nju.edu.cn/xyzl/szdw/nhjs.htm",
    ], "http://nh.nju.edu.cn/"),
]


async def extract_faculty_from_page(page, faculty_url, college_name):
    """从一个师资页面提取教师信息"""
    teachers = []
    try:
        await page.goto(faculty_url, wait_until='domcontentloaded', timeout=20000)
        await page.wait_for_timeout(2000)

        # 获取页面文本
        page_text = await page.evaluate('() => document.body.innerText')
        lines = page_text.split('\n')

        # 提取所有邮箱
        all_emails = EMAIL_RE.findall(page_text)
        valid_emails = [e for e in all_emails if '.edu.cn' in e or '.edu' in e.split('.')[-2]]
        valid_emails = [e for e in valid_emails if not is_public_email(e)]

        # 提取所有链接（教师详情页）
        links = await page.evaluate('''() => {
            return Array.from(document.querySelectorAll('a')).map(a => ({
                text: a.innerText.trim().substring(0, 30),
                href: a.href
            })).filter(x => x.text.length > 0 && x.href.startsWith('http'));
        }''')

        # 提取教师详情页链接（通常是 /xxx/list.htm 或 /xxx/xxx/page.htm 格式）
        teacher_urls = []
        for l in links:
            txt = l['text']
            href = l['href']
            # 检查是否是教师链接
            name = extract_name(txt)
            if name and ('nju.edu.cn' in href):
                teacher_urls.append((name, href))

        # 如果在页面上直接有邮箱，提取教师信息
        if valid_emails:
            print(f"  [直接] {college_name}: {faculty_url} 发现 {len(valid_emails)} 个邮箱")
            for email in valid_emails:
                # 尝试关联姓名
                name = ""
                for line in lines:
                    if email in line:
                        possible_name = extract_name(line.split(email)[0].strip())
                        if possible_name:
                            name = possible_name
                            break
                title = ""
                # 找职称
                for line in lines:
                    if email in line:
                        t = extract_title(line)
                        if t:
                            title = t
                            break
                teachers.append({
                    "name": name or email.split('@')[0],
                    "email": email,
                    "title": title,
                    "url": faculty_url
                })
        elif teacher_urls:
            print(f"  [链接] {college_name}: {faculty_url} 发现 {len(teacher_urls)} 个教师链接")
            # 尝试访问前几个教师的详情页
            for tname, thref in teacher_urls[:3]:
                try:
                    await page.goto(thref, wait_until='domcontentloaded', timeout=15000)
                    await page.wait_for_timeout(1000)
                    detail_text = await page.evaluate('() => document.body.innerText')
                    detail_html = await page.content()
                    email = restore_email(detail_text)
                    title = extract_title(detail_text)
                    if not title:
                        title = extract_title(thref)
                    teachers.append({
                        "name": tname,
                        "email": email or "",
                        "title": title or "",
                        "url": thref
                    })
                    if email:
                        print(f"    {tname}: {email}")
                    else:
                        print(f"    {tname}: 无邮箱")
                except:
                    teachers.append({"name": tname, "email": "", "title": "", "url": thref})
        else:
            print(f"  [无] {college_name}: {faculty_url} 无邮箱无教师链接")

        # 尝试从HTML中提取内联教师数据
        page_html = await page.content()
        html_emails = EMAIL_RE.findall(page_html)
        for e in html_emails:
            if '.edu.cn' in e and not is_public_email(e):
                if e not in [t["email"] for t in teachers]:
                    # 尝试从周围提取姓名
                    name = ""
                    idx = page_html.find(e)
                    if idx > 0:
                        context = page_html[max(0,idx-100):idx+len(e)]
                        possible_name = extract_name(context)
                        if possible_name:
                            name = possible_name
                    teachers.append({"name": name or e.split('@')[0], "email": e, "title": "", "url": faculty_url})

    except Exception as ex:
        print(f"  [错误] {college_name}: {faculty_url} - {str(ex)[:80]}")

    return teachers


async def crawl_college(browser, config, sem):
    """爬取一个学院的教师信息"""
    college_name, faculty_urls, homepage = config
    all_teachers = []
    seen_keys = set()

    async with sem:
        print(f"\n{'='*40}")
        print(f"开始爬取: {college_name}")
        print(f"师资链接: {faculty_urls}")

        page = await browser.new_page()

        for furl in faculty_urls:
            teachers = await extract_faculty_from_page(page, furl, college_name)
            for t in teachers:
                key = f"{t['name']}|{t['email']}|{t['title']}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    t["department"] = college_name
                    all_teachers.append(t)

        await page.close()

        has_email_count = sum(1 for t in all_teachers if t.get("email"))
        print(f"{college_name}: 共 {len(all_teachers)} 教师, {has_email_count} 有邮箱")
        return all_teachers


async def deep_crawl():
    """主函数"""
    sem = asyncio.Semaphore(4)  # 并发4个学院

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        tasks = []
        for cfg in COLLEGE_CONFIG:
            tasks.append(crawl_college(browser, cfg, sem))

        all_results = await asyncio.gather(*tasks)
        await browser.close()

    return all_results


def save_results(all_results):
    """保存结果"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_teachers = []
    for college_teachers in all_results:
        all_teachers.extend(college_teachers)

    # 去重
    seen = set()
    unique_teachers = []
    for t in all_teachers:
        key = f"{t.get('name','')}|{t.get('email','')}|{t.get('department','')}"
        if key not in seen:
            seen.add(key)
            unique_teachers.append(t)

    # 按学院统计
    from collections import Counter, defaultdict
    dept_counts = Counter()
    dept_email_counts = Counter()
    dept_teachers = defaultdict(list)
    for t in unique_teachers:
        dept = t.get("department", "未知")
        dept_counts[dept] += 1
        dept_teachers[dept].append(t)
        if t.get("email"):
            dept_email_counts[dept] += 1

    # CSV输出
    csv_path = os.path.join(TASK_DIR, f"南京大学_全部教师邮箱_{timestamp}.csv")
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(["姓名", "邮箱", "学院", "职称", "主页链接"])
        for t in unique_teachers:
            w.writerow([t.get("name",""), t.get("email",""),
                       t.get("department",""), t.get("title",""), t.get("url","")])

    # 打印统计
    print(f"\n{'='*60}")
    print(f"南京大学全学院爬取结果")
    print(f"{'='*60}")
    print(f"{'学院':<25} {'教师':<6} {'有邮箱':<6}")
    print(f"{'-'*60}")
    small_colleges = []
    for dept, count in sorted(dept_counts.items(), key=lambda x: -x[1]):
        ec = dept_email_counts.get(dept, 0)
        flag = " ⚠️ <50" if count < 50 else ""
        if count < 50:
            small_colleges.append((dept, count, ec))
        print(f"{dept:<22} {count:<4} {ec:<4}{flag}")

    print(f"{'-'*60}")
    total = sum(dept_counts.values())
    total_email = sum(dept_email_counts.values())
    print(f"总计: {total} 教师, {total_email} 有邮箱")

    if small_colleges:
        print(f"\n{'='*60}")
        print(f"⚠️ 教师数 < 50 的学院（需替代策略补充爬取）：")
        for dept, cnt, ec in small_colleges:
            print(f"  {dept}: {cnt} 教师 ({ec} 有邮箱)")

    print(f"\nCSV: {csv_path}")
    return csv_path, unique_teachers, small_colleges


if __name__ == "__main__":
    print("开始南京大学全学院深度爬取...")
    print(f"共 {len(COLLEGE_CONFIG)} 个学院")
    results = asyncio.run(deep_crawl())
    csv_path, teachers, small_colleges = save_results(results)
    print(f"\n完成！")
