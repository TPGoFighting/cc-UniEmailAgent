"""
南京大学全学院教师邮箱深度爬取 — 高速并行版
策略：
  1. 访问各学院师资列表页 => 提取教师详情页链接
  2. 用固定 page 池并行访问教师详情页 => 提取邮箱
  3. 合并到现有数据
"""
import asyncio, csv, os, re
from datetime import datetime
from playwright.async_api import async_playwright
from collections import defaultdict

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
ANTI_SPAM = [(r'\[at\]', '@'), (r'\(at\)', '@'), (r'#@', '@'),
             (r'\[@\]', '@'), (r'\(@\)', '@'), (r'\s*at\s*', '@')]
NAME_RE = re.compile(r'[一-鿿]{2,4}')

def restore_email(t):
    if not t: return None
    for p, r in ANTI_SPAM:
        t = re.sub(p, r, t, flags=re.IGNORECASE)
    m = EMAIL_RE.search(t)
    return m.group(0) if m else None

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
TASK_DIR = os.path.join(OUTPUT_DIR, "nju_email_deep")
os.makedirs(TASK_DIR, exist_ok=True)

COLLEGE_CONFIG = [
    ("文学院", "https://chin.nju.edu.cn/szdw/xrjs/index.html"),
    ("历史学院", "https://history.nju.edu.cn/28475/list.htm"),
    ("哲学学院", "https://philo.nju.edu.cn/4712/list.htm"),
    ("新闻传播学院", "https://jc.nju.edu.cn/jzyg/zzjs.htm"),
    ("法学院", "https://law.nju.edu.cn/szdw/zzjs1/js.htm"),
    ("商学院", "https://nubs.nju.edu.cn/8878/list.htm"),
    ("外国语学院", "https://sfs.nju.edu.cn/szdw/index.html"),
    ("政府管理学院", "https://public.nju.edu.cn/szdw"),
    ("国际关系学院", "https://sis.nju.edu.cn/jsrk/list.htm"),
    ("信息管理学院", "https://im.nju.edu.cn/szll/zzjs.htm"),
    ("社会学院", "https://sociology.nju.edu.cn/szdw/list.htm"),
    ("数学学院", "https://math.nju.edu.cn/jzyg/index.html"),
    ("物理学院", "https://physics.nju.edu.cn/szdw/qbmd/index.html"),
    ("天文与空间科学学院", "https://astronomy.nju.edu.cn/szll/index.html"),
    ("化学化工学院", "https://chem.nju.edu.cn/szll/list.htm"),
    ("计算机学院", "https://cs.nju.edu.cn/1651/list.htm"),
    ("软件学院", "https://software.nju.edu.cn/szll/szdw/index.html"),
    ("人工智能学院", "https://ai.nju.edu.cn/people/list.htm"),
    ("电子科学与工程学院", "https://ese.nju.edu.cn/22542/list.htm"),
    ("现代工程与应用科学学院", "https://eng.nju.edu.cn/43271/list.htm"),
    ("环境学院", "http://hjxy.nju.edu.cn/szdw/index.html"),
    ("地球科学与工程学院", "https://es.nju.edu.cn/25235/list.htm"),
    ("地理与海洋科学学院", "http://sgos.nju.edu.cn/62681/list.htm"),
    ("大气科学学院", "http://as.nju.edu.cn/js/list.htm"),
    ("生命科学学院", "https://life.nju.edu.cn/szdw/list.htm"),
    ("医学院", "https://med.nju.edu.cn/10649/list.htm"),
    ("工程管理学院", "https://sme.nju.edu.cn/xssz/list.htm"),
    ("匡亚明学院", "https://dii.nju.edu.cn/kyds/list.htm"),
    ("建筑与城市规划学院", "http://arch.nju.edu.cn/szdw/index.html"),
    ("马克思主义学院", "https://marxism.nju.edu.cn/szdw/js.htm"),
    ("艺术学院", "https://art.nju.edu.cn/55208/list.htm"),
    ("智能科学与技术学院", "https://is.nju.edu.cn/57159/list.htm"),
    ("智能软件与工程学院", "https://ise.nju.edu.cn/szll/zjzjs.htm"),
    ("集成电路学院", "https://ic.nju.edu.cn/56606/list.htm"),
    ("数字经济与管理学院", "https://sdem.nju.edu.cn/56976/list.htm"),
    ("能源与资源学院", "https://sser.nju.edu.cn/szll.htm"),
    ("机器人与自动化学院", "https://ra.nju.edu.cn/szll/index.html"),
    ("前沿科学学院", "http://frontier.nju.edu.cn/zrjs/list.htm"),
    ("生物医学工程学院", "https://bme.nju.edu.cn/szll/index.html"),
    ("教育研究院·陶行知教师教育学院", "https://edu.nju.edu.cn/8746/list.htm"),
    ("海外教育学院", "https://hwxy.nju.edu.cn/szdw/index.html"),
    ("大学外语部", "https://dafls.nju.edu.cn/07/dd/c13168a460765/page.htm"),
    ("南京赫尔辛基大气与地球系统科学学院", "https://nh.nju.edu.cn/xyzl/szdw/nhjs.htm"),
    ("体育部", "http://tyb.nju.edu.cn/"),
]

async def get_all_links(page, list_url):
    """从列表页及子列表页提取教师详情页链接"""
    all_links = []
    direct_emails = set()
    visited = set()

    async def scrape(url):
        if url in visited: return [], []
        visited.add(url)
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(2000)
        except:
            return [], []

        raw = await page.evaluate('''() => {
            const ex = new Set();
            'nav,header,footer,.nav,.header,.footer,.menu,.sidebar,#nav,#header,#footer'
                .split(',').forEach(s => document.querySelectorAll(s).forEach(e =>
                    e.querySelectorAll('a').forEach(a => ex.add(a))));
            return Array.from(document.querySelectorAll('a[href]'))
                .filter(a => !ex.has(a) && a.href.startsWith('http'))
                .map(a => ({ text: a.innerText.trim().substring(0,60), href: a.href }));
        }''')

        links, subs = [], []
        for item in raw:
            h, t = item['href'], item['text']
            if '/list.htm' in h and h != url:
                subs.append(h)
                continue
            names = NAME_RE.findall(t)
            if names and len(t) < 50:
                for n in names:
                    if len(n) >= 2:
                        links.append({"name": n, "url": h})
                        break

        html = await page.content()
        for m in EMAIL_RE.finditer(html):
            e = m.group(0)
            if 'nju.edu.cn' in e and not any(p in e.split('@')[0].lower()
               for p in ['webmaster','admin','office','info','master','root',
                          'postmaster','bgs','dangzheng']):
                direct_emails.add(e)
        return links, subs

    links, subs = await scrape(list_url)
    all_links.extend(links)
    for su in subs[:20]:
        sl, _ = await scrape(su)
        existing = {l['name'] for l in all_links}
        for l in sl:
            if l['name'] not in existing:
                all_links.append(l)
                existing.add(l['name'])

    # 去重
    seen = {}
    unique = []
    for l in all_links:
        if l['name'] not in seen:
            seen[l['name']] = True
            unique.append(l)
    return unique, direct_emails


async def process_college(config, page_pool, detail_sem):
    """处理一个学院"""
    cname, list_url = config
    print(f"\n▶ {cname}")

    page = page_pool[0]  # 从池中拿一个page
    links, direct_emails = await get_all_links(page, list_url)
    if not links:
        print(f"  ⚠️ 未找到教师链接")
        return cname, [], {}

    # 过滤出真正的详情页链接
    skip_patterns = ['list.htm', 'list.htm?', '/index.html', '/main.htm',
        'zsjy', 'kxyj', 'rcpy', 'xygk', '/szdw/', '/szll/', '/jzyg/',
        '.github.io', 'scholat.com']
    detail_targets = [l for l in links if not any(kw in l['url'] for kw in skip_patterns)]

    # 只取前N个详情页（平衡时间和覆盖率）
    max_visit = min(len(detail_targets), 80)
    detail_targets = detail_targets[:max_visit]

    # 用page池并行访问详情页
    name_email = {}

    async def crawl_one(idx):
        async with detail_sem:
            t = detail_targets[idx]
            p = page_pool[idx % len(page_pool)] if idx > 0 else page_pool[0]
            try:
                await p.goto(t['url'], wait_until='domcontentloaded', timeout=15000)
                await p.wait_for_timeout(600)
                text = await p.evaluate('() => document.body.innerText')
                html = await p.content()
                email = restore_email(text + '\n' + html)
                if email and not any(pfx in email.split('@')[0].lower()
                   for pfx in ['webmaster','admin','office','info','master','root',
                               'postmaster','bgs','dangzheng']):
                    name_email[t['name']] = email
            except:
                pass

    if detail_targets:
        tasks = [crawl_one(i) for i in range(len(detail_targets))]
        await asyncio.gather(*tasks)

    print(f"  ✅ {len(links)} 教师, {len(name_email)} 邮箱")
    return cname, links, name_email


async def main():
    # 读现有CSV
    existing_path = os.path.join(OUTPUT_DIR, "nju_final", "南京大学_全部教师邮箱_V1.0.0.csv")
    existing = []
    if os.path.exists(existing_path):
        with open(existing_path, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                existing.append({
                    "name": row.get("姓名","").strip(),
                    "email": row.get("邮箱","").strip(),
                    "department": row.get("学院","").strip(),
                    "title": row.get("职称","").strip(),
                    "url": row.get("主页链接","").strip()
                })
    print(f"现有数据: {len(existing)} 条, 有邮箱: {sum(1 for r in existing if EMAIL_RE.match(r['email']))}")

    college_data = {}
    detail_sem = asyncio.Semaphore(8)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        # 创建 page 池(4个永久page，避免频繁open/close)
        page_pool = [await ctx.new_page() for _ in range(4)]

        for config in COLLEGE_CONFIG:
            try:
                cname, links, name_email = await process_college(config, page_pool, detail_sem)
                college_data[cname] = {"links": links, "emails": name_email}
            except Exception as ex:
                print(f"  ❌ {config[0]}: {ex}")
                college_data[config[0]] = {"links": [], "emails": {}}

        # 关闭page池
        for p in page_pool:
            await p.close()
        await browser.close()

    # === 合并到现有数据 ===
    dept_email_map = {c: d["emails"] for c, d in college_data.items()}

    newly_added = 0
    for rec in existing:
        dept = rec["department"]
        name = rec["name"]
        if dept in dept_email_map and name in dept_email_map[dept]:
            new_email = dept_email_map[dept][name]
            if not rec['email'] and new_email:
                rec['email'] = new_email
                newly_added += 1

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_csv = os.path.join(TASK_DIR, f"南京大学_邮箱补充_{ts}.csv")
    with open(final_csv, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(["姓名","邮箱","学院","职称","主页链接"])
        for r in existing:
            w.writerow([r["name"], r["email"], r["department"], r["title"], r["url"]])

    total_with_email = sum(1 for r in existing if EMAIL_RE.match(r['email']))
    total_clean_email = sum(1 for r in existing if r['email'] and '@' in r['email']
        and not any(p in r['email'].split('@')[0].lower()
            for p in ['webmaster','admin','office','info','master','root','postmaster','bgs','dangzheng']))

    print(f"\n{'='*55}")
    print(f"📊 结果汇总")
    print(f"{'='*55}")
    for cname, data in sorted(college_data.items(), key=lambda x: -len(x[1]['emails'])):
        if data['emails']:
            print(f"  {cname:<22} {len(data['links']):>4} 教师, {len(data['emails']):>4} 邮箱")
    print(f"\n新发现邮箱总数: {sum(len(d['emails']) for d in college_data.values())}")
    print(f"补充到现有数据: {newly_added}")
    print(f"最终有邮箱教师: {total_with_email}")
    print(f"最终有效邮箱: {total_clean_email}")
    print(f"\n文件: {final_csv}")

    return final_csv, college_data


if __name__ == "__main__":
    asyncio.run(main())
