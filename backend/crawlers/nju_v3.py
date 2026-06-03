"""
南京大学全学院深度爬虫 v3 — 智能师资页面解析
策略：根据不同网站模板类型，提取教师信息
"""

import asyncio, csv, os, re, sys
from datetime import datetime
from playwright.async_api import async_playwright
from collections import Counter, defaultdict

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
ANTI_SPAM = [(r'\[at\]', '@'), (r'\(at\)', '@'), (r'#@', '@'),
             (r'\[@\]', '@'), (r'\(@\)', '@'), (r'\s*at\s*', '@')]
NAME_RE = re.compile(r'[一-鿿]{2,4}')

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
TASK_ID = os.environ.get("TASK_ID", "nju_v3")
TASK_DIR = os.path.join(OUTPUT_DIR, TASK_ID)
os.makedirs(TASK_DIR, exist_ok=True)

PUBLIC_PREFIXES = ['webmaster', 'admin', 'office', 'info', 'master', 'root',
                   'postmaster', 'bgs', 'dangzheng', 'yuanban', 'wxyxz', 'xwcb', 'yanju']

def restore_email(t):
    if not t: return None
    for p, r in ANTI_SPAM:
        t = re.sub(p, r, t, flags=re.IGNORECASE)
    m = EMAIL_RE.search(t)
    return m.group(0) if m else None

def is_public(e):
    if not e: return True
    return any(p in e.split('@')[0].lower() for p in PUBLIC_PREFIXES)

TITLES = ['教授/博导', '副教授/硕导', '教授级高级工程师',
          '教授', '副教授', '讲师', '助教', '助理教授',
          '研究员', '副研究员', '助理研究员',
          '高级工程师', '工程师', '助理工程师',
          '博士后', '准聘助理教授', '准聘副教授',
          '主任医师', '副主任医师', '主治医师',
          '高级实验师', '实验师',
          '教授级高级实验师', '副编审', '编审']

def extract_title(t):
    if not t: return None
    for tl in TITLES:
        if tl in t: return tl
    return None

COLLEGE_FACULTY = [
    # (学院名, 师资页URL)
    ("文学院", "https://chin.nju.edu.cn/szdw/xrjs/index.html", "http://chin.nju.edu.cn/"),
    ("历史学院", "https://history.nju.edu.cn/28475/list.htm", "http://history.nju.edu.cn/"),
    ("哲学学院", "https://philo.nju.edu.cn/4712/list.htm", "http://philo.nju.edu.cn/"),
    ("新闻传播学院", "https://jc.nju.edu.cn/jzyg/zzjs.htm", "http://jc.nju.edu.cn/"),
    ("法学院", "https://law.nju.edu.cn/szdw/zzjs1/js.htm", "https://law.nju.edu.cn/"),
    ("商学院", "https://nubs.nju.edu.cn/8878/list.htm", "https://nubs.nju.edu.cn/"),
    ("外国语学院", "https://sfs.nju.edu.cn/szdw/index.html", "http://sfs.nju.edu.cn/"),
    ("政府管理学院", "https://public.nju.edu.cn/szdw", "http://public.nju.edu.cn/"),
    ("国际关系学院", "https://sis.nju.edu.cn/jsrk/list.htm", "https://sis.nju.edu.cn/"),
    ("信息管理学院", "https://im.nju.edu.cn/szll/zzjs.htm", "http://im.nju.edu.cn/"),
    ("社会学院", "https://sociology.nju.edu.cn/szdw/list.htm", "http://sociology.nju.edu.cn/"),
    ("数学学院", "https://math.nju.edu.cn/jzyg/index.html", "http://math.nju.edu.cn/"),
    ("物理学院", "https://physics.nju.edu.cn/szdw/qbmd/index.html", "http://physics.nju.edu.cn/"),
    ("天文与空间科学学院", "https://astronomy.nju.edu.cn/szll/index.html", "http://astronomy.nju.edu.cn/"),
    ("化学化工学院", "https://chem.nju.edu.cn/szll/list.htm", "http://chem.nju.edu.cn/"),
    ("计算机学院", "https://cs.nju.edu.cn/1651/list.htm", "http://cs.nju.edu.cn/"),
    ("软件学院", "https://software.nju.edu.cn/szll/szdw/index.html", "http://software.nju.edu.cn/"),
    ("人工智能学院", "https://ai.nju.edu.cn/people/list.htm", "http://ai.nju.edu.cn/"),
    ("电子科学与工程学院", "https://ese.nju.edu.cn/22542/list.htm", "http://ese.nju.edu.cn/"),
    ("现代工程与应用科学学院", "https://eng.nju.edu.cn/43271/list.htm", "http://eng.nju.edu.cn/"),
    ("环境学院", "http://hjxy.nju.edu.cn/szdw/index.html", "http://hjxy.nju.edu.cn/"),
    ("地球科学与工程学院", "https://es.nju.edu.cn/25235/list.htm", "http://es.nju.edu.cn/"),
    ("地理与海洋科学学院", "http://sgos.nju.edu.cn/62681/list.htm", "http://sgos.nju.edu.cn/"),
    ("大气科学学院", "http://as.nju.edu.cn/js/list.htm", "http://as.nju.edu.cn/"),
    ("生命科学学院", "https://life.nju.edu.cn/szdw/list.htm", "http://life.nju.edu.cn/"),
    ("医学院", "https://med.nju.edu.cn/10649/list.htm", "http://med.nju.edu.cn/"),
    ("工程管理学院", "https://sme.nju.edu.cn/xssz/list.htm", "http://sme.nju.edu.cn/"),
    ("匡亚明学院", "https://dii.nju.edu.cn/kyds/list.htm", "http://dii.nju.edu.cn/"),
    ("建筑与城市规划学院", "http://arch.nju.edu.cn/szdw/index.html", "http://arch.nju.edu.cn/"),
    ("马克思主义学院", "https://marxism.nju.edu.cn/szdw/js.htm", "http://marxism.nju.edu.cn/"),
    ("艺术学院", "https://art.nju.edu.cn/55208/list.htm", "http://art.nju.edu.cn/"),
    ("智能科学与技术学院", "https://is.nju.edu.cn/57159/list.htm", "https://is.nju.edu.cn/main.htm"),
    ("智能软件与工程学院", "https://ise.nju.edu.cn/szll/zjzjs.htm", "https://ise.nju.edu.cn/"),
    ("集成电路学院", "https://ic.nju.edu.cn/56606/list.htm", "https://ic.nju.edu.cn/main.htm"),
    ("数字经济与管理学院", "https://sdem.nju.edu.cn/56976/list.htm", "https://sdem.nju.edu.cn/main.htm"),
    ("能源与资源学院", "https://sser.nju.edu.cn/szll.htm", "https://sser.nju.edu.cn/"),
    ("机器人与自动化学院", "https://ra.nju.edu.cn/szll/index.html", "https://ra.nju.edu.cn/"),
    ("前沿科学学院", "http://frontier.nju.edu.cn/zrjs/list.htm", "https://frontier.nju.edu.cn/main.htm"),
    ("生物医学工程学院", "https://bme.nju.edu.cn/szll/index.html", "https://bme.nju.edu.cn/"),
    ("教育研究院·陶行知教师教育学院", "https://edu.nju.edu.cn/8746/list.htm", "http://edu.nju.edu.cn/"),
    ("海外教育学院", "https://hwxy.nju.edu.cn/szdw/index.html", "http://hwxy.nju.edu.cn/"),
    ("大学外语部", "https://dafls.nju.edu.cn/07/dd/c13168a460765/page.htm", "http://dafls.nju.edu.cn/"),
    ("南京赫尔辛基大气与地球系统科学学院", "https://nh.nju.edu.cn/xyzl/szdw/nhjs.htm", "http://nh.nju.edu.cn/"),
    ("体育部", "http://tyb.nju.edu.cn/", "http://tyb.nju.edu.cn/"),
]


async def extract_teacher_names_from_list(page, url):
    """从教师列表页提取所有教师姓名和可能的信息"""
    teachers = []
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=20000)
        await page.wait_for_timeout(2000)

        body_text = await page.evaluate('() => document.body.innerText')
        lines = body_text.split('\n')

        # 方法1: 提取所有文本行中的姓名+职称模式
        for line in lines:
            line = line.strip()
            if not line or len(line) > 60:
                continue

            # 查找姓名 (2-4 汉字)
            names = NAME_RE.findall(line)
            if not names:
                continue

            title = extract_title(line)
            email = restore_email(line)

            for name in names:
                if len(name) >= 2:
                    teachers.append({
                        "name": name,
                        "title": title or "",
                        "email": email or "",
                        "url": url,
                        "_parent_url": url
                    })

        # 方法2: 提取所有链接中的教师
        links = await page.evaluate('''() => {
            return Array.from(document.querySelectorAll('a')).map(a => ({
                text: a.innerText.trim().substring(0, 40),
                href: a.href
            })).filter(x => x.text.length > 0 && x.href.startsWith('http'));
        }''')

        seen_names = set()
        for l in links:
            names_in_link = NAME_RE.findall(l['text'])
            for n in names_in_link:
                if n not in seen_names and len(n) >= 2:
                    seen_names.add(n)
                    # 检查是否已存在同名师
                    exists = any(t['name'] == n for t in teachers)
                    if not exists:
                        title = extract_title(l['text'])
                        teachers.append({
                            "name": n,
                            "title": title or "",
                            "email": "",
                            "url": l['href'],
                            "_parent_url": url
                        })

        # 方法3: 从页面HTML中提取所有邮箱
        page_html = await page.content()
        html_emails = EMAIL_RE.findall(page_html)
        for e in set(html_emails):
            if '.edu.cn' in e and not is_public(e):
                exists = any(t['email'] == e for t in teachers)
                if not exists:
                    teachers.append({
                        "name": e.split('@')[0],
                        "email": e,
                        "title": "",
                        "url": url,
                        "_parent_url": url
                    })

    except Exception as ex:
        print(f"  [错误] {url}: {str(ex)[:80]}")

    return teachers


async def crawl_teacher_detail(page, teacher):
    """访问教师详情页提取邮箱"""
    url = teacher.get("url", "")
    name = teacher.get("name", "")
    if not url or not url.startswith("http"):
        return teacher
    if teacher.get("email"):
        return teacher  # 已有邮箱

    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=15000)
        await page.wait_for_timeout(1000)
        text = await page.evaluate('() => document.body.innerText')
        html = await page.content()
        email = restore_email(text)
        if not email:
            email = restore_email(html)
        if email and not is_public(email):
            teacher["email"] = email
            print(f"    ✓ {name}: {email}")
        else:
            print(f"    ✗ {name}: 无邮箱")
    except Exception as e:
        print(f"    ✗ {name}: 访问失败 - {str(e)[:60]}")

    return teacher


async def process_college(browser, config, sem):
    """处理一个学院的教师信息"""
    cname, furl, homepage = config
    all_teachers = []

    async with sem:
        print(f"\n▶ {cname}")
        print(f"  URL: {furl}")

        page = await browser.new_page()

        # 第1步：从列表页提取教师
        teachers = await extract_teacher_names_from_list(page, furl)
        print(f"  列表页提取: {len(teachers)} 名教师/邮箱")

        # 第2步：如果有教师详情页链接（没有邮箱的），尝试访问详情页
        need_detail = [t for t in teachers if not t.get("email") and t.get("url", "").startswith("http") and t["url"] != furl and "nju.edu.cn" in t["url"]]
        no_detail_link = [t for t in teachers if not t.get("email") and (not t.get("url") or t["url"] == furl or "nju.edu.cn" not in t.get("url",""))]
        has_email = [t for t in teachers if t.get("email")]

        print(f"  有邮箱: {len(has_email)}, 需访问详情页: {len(need_detail)}, 无链接: {len(no_detail_link)}")

        # 对每个教师访问详情页（限制前10个学院最多访问20个详情页）
        detail_limit = min(len(need_detail), 20) if furl else 0
        for i in range(detail_limit):
            t = need_detail[i]
            t = await crawl_teacher_detail(page, t)

        # 合并结果去重
        seen = set()
        for t in teachers:
            key = f"{t['name']}|{t.get('email','')}"
            if key not in seen:
                seen.add(key)
                t["department"] = cname
                all_teachers.append(t)

        await page.close()

    has_email_count = sum(1 for t in all_teachers if t.get("email"))
    print(f"  => {cname}: {len(all_teachers)} 教师, {has_email_count} 有邮箱")
    return all_teachers


async def main():
    sem = asyncio.Semaphore(4)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        tasks = [process_college(browser, cfg, sem) for cfg in COLLEGE_FACULTY]
        all_results = await asyncio.gather(*tasks)
        await browser.close()

    return all_results


def save(results):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_t = []
    for rt in results:
        all_t.extend(rt)

    # 去重
    seen = set()
    unique = []
    for t in all_t:
        key = f"{t['name']}|{t.get('email','')}|{t.get('department','')}"
        if key not in seen:
            seen.add(key)
            unique.append(t)

    # 统计
    dept_cnt = Counter()
    dept_email = Counter()
    dept_data = defaultdict(list)
    for t in unique:
        d = t.get("department", "未知")
        dept_cnt[d] += 1
        dept_data[d].append(t)
        if t.get("email"):
            dept_email[d] += 1

    csv_path = os.path.join(TASK_DIR, f"南京大学_全部教师邮箱_v3_{ts}.csv")
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(["姓名", "邮箱", "学院", "职称", "主页链接"])
        for t in unique:
            w.writerow([t.get("name",""), t.get("email",""),
                       t.get("department",""), t.get("title",""), t.get("url","")])

    print(f"\n{'='*60}")
    print("南京大学全学院爬取统计")
    print(f"{'='*60}")
    print(f"{'学院':<25} {'教师':<6} {'有邮箱':<6}")
    print(f"{'-'*60}")
    small = []
    for d, c in sorted(dept_cnt.items(), key=lambda x: -x[1]):
        ec = dept_email.get(d, 0)
        f = " ⚠️" if c < 50 else ""
        if c < 50: small.append((d, c, ec))
        print(f"{d:<22} {c:<4} {ec:<4}{f}")

    print(f"{'-'*60}")
    print(f"总计: {sum(dept_cnt.values())} 教师, {sum(dept_email.values())} 有邮箱")

    if small:
        print(f"\n⚠️ 教师数 < 50 的学院:")
        for d, c, ec in small:
            print(f"  {d}: {c} ({ec} 有邮箱)")
    print(f"\nCSV: {csv_path}")
    return csv_path, unique, small


if __name__ == "__main__":
    rs = asyncio.run(main())
    save(rs)
