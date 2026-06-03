"""
南大低覆盖率学院批量邮箱提取 - 使用正确的列表页和详情页
"""
import asyncio, csv, os, re, sys
from datetime import datetime
from playwright.async_api import async_playwright

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
ANTI_SPAM = [(r'\[at\]', '@'), (r'\(at\)', '@'), (r'#@', '@')]
def restore_email(t):
    if not t: return None
    for p, r in ANTI_SPAM:
        t = re.sub(p, r, t, flags=re.IGNORECASE)
    m = EMAIL_RE.search(t)
    return m.group(0) if m else None

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
TASK_DIR = os.path.join(OUTPUT_DIR, "nju_email_deep")

# 低覆盖率学院（修正后的URL，只选邮箱率<5%的学院）
COLLEGES = [
    # (学院名, 列表页URL)
    ("数学学院", "https://math.nju.edu.cn/jzyg/apypl/index.html"),
    ("物理学院", "https://physics.nju.edu.cn/szdw/qbmd/index.html"),
    ("软件学院", "https://software.nju.edu.cn/szll/szdw/index.html"),
    ("天文与空间科学学院", "https://astronomy.nju.edu.cn/szll/index.html"),
    ("化学化工学院", "https://chem.nju.edu.cn/szll/list.htm"),
    ("现代工程与应用科学学院", "https://eng.nju.edu.cn/43271/list.htm"),
    ("外国语学院", "https://sfs.nju.edu.cn/szdw/index.html"),
    ("环境学院", "http://hjxy.nju.edu.cn/szdw/index.html"),
    ("地球科学与工程学院", "https://es.nju.edu.cn/25235/list.htm"),
    ("地理与海洋科学学院", "http://sgos.nju.edu.cn/62681/list.htm"),
    ("体育部", "http://tyb.nju.edu.cn/"),
    ("文学院", "https://chin.nju.edu.cn/szdw/xrjs/index.html"),
    ("电子科学与工程学院", "https://ese.nju.edu.cn/22542/list.htm"),
    ("匡亚明学院", "https://dii.nju.edu.cn/kyds/list.htm"),
    ("建筑与城市规划学院", "http://arch.nju.edu.cn/szdw/index.html"),
    ("教育研究院·陶行知教师教育学院", "https://edu.nju.edu.cn/8746/list.htm"),
    ("大气科学学院", "http://as.nju.edu.cn/js/list.htm"),
    ("艺术学院", "https://art.nju.edu.cn/55208/list.htm"),
    ("哲学学院", "https://philo.nju.edu.cn/4712/list.htm"),
    ("新闻传播学院", "https://jc.nju.edu.cn/jzyg/zzjs.htm"),
]

async def get_teacher_pages(page, url):
    """从列表页提取所有教师详情页链接"""
    detail_urls = {}  # name -> url
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # 提取所有链接
        links = await page.evaluate("""() => {
            const ex = new Set();
            'nav,header,footer,.nav,.header,.footer,.menu,.sidebar,#nav,#header,#footer,.pagination,.top-bar'
                .split(',').forEach(s => document.querySelectorAll(s).forEach(e =>
                    e.querySelectorAll('a').forEach(a => ex.add(a))));
            return Array.from(document.querySelectorAll('a[href]'))
                .filter(a => !ex.has(a) && a.href.startsWith('http'))
                .map(a => ({ text: a.innerText.trim().substring(0,40), href: a.href }));
        }""")

        # 方法1: 通过链接文本中的中文名识别教师链接
        for l in links:
            h = l['href']
            if '/index.html' in h or '/main.htm' in h or '/list.htm' in h:
                continue
            names = re.findall(r'[一-鿿]{2,4}', l['text'])
            if names and len(l['text']) < 50:
                for n in names:
                    if len(n) >= 2:
                        detail_urls.setdefault(n, h)

        # 方法2: 也找所有带 /i*.html 或 /page.htm 的链接（即使文本不包含中文名，可能是JS渲染的链接）
        for l in links:
            h, t = l['href'], l['text']
            if '/i' in h and '.html' in h:
                names = re.findall(r'[一-鿿]{2,4}', t)
                if names:
                    for n in names:
                        if len(n) >= 2:
                            detail_urls.setdefault(n, h)

        # 方法3: 从页面HTML中直接提取可能的教师页面链接
        html = await page.content()
        # 找 /i*.html 或 /page.htm 模式的URL，并尝试提取关联的教师名
        for m in re.finditer(r'(/[a-f0-9]{2}/[a-f0-9]{2}/c\d+a\d+/page\.htm)', html):
            full_url = url.split('/')[0] + '//' + url.split('/')[2] + m.group(1)
            # 找到此链接附近的文本
            context = html[max(0, m.start()-200):m.end()+200]
            names = re.findall(r'[一-鿿]{2,4}', context)
            for n in names:
                if len(n) >= 2:
                    detail_urls.setdefault(n, full_url)

    except Exception as e:
        print(f"  [错误] {url}: {e}")

    return detail_urls


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        sem = asyncio.Semaphore(15)

        all_new_emails = {}  # name -> (email, college)

        for cname, list_url in COLLEGES:
            print(f"\n▶ {cname}")
            page = await browser.new_page()
            try:
                teacher_pages = await get_teacher_pages(page, list_url)
                print(f"  教师链接: {len(teacher_pages)}")

                if not teacher_pages:
                    await page.close()
                    continue

                # 访问详情页
                found = 0
                async def visit(name, url):
                    nonlocal found
                    async with sem:
                        p = await browser.new_page()
                        try:
                            await p.goto(url, wait_until="domcontentloaded", timeout=15000)
                            await p.wait_for_timeout(600)
                            text = await p.evaluate("() => document.body.innerText")
                            html = await p.content()
                            email = restore_email(text + "\n" + html)
                            if email and not any(pfx in email.split('@')[0].lower()
                               for pfx in ['webmaster','admin','office','info','master','root',
                                           'postmaster','bgs','dangzheng']):
                                all_new_emails[name] = (email, cname)
                                found += 1
                        except:
                            pass
                        finally:
                            await p.close()

                tasks = [visit(n, u) for n, u in teacher_pages.items()]
                await asyncio.gather(*tasks)
                print(f"  发现 {found} 个邮箱")
            except Exception as e:
                print(f"  ❌ {e}")
            finally:
                await page.close()

        await browser.close()

    # 保存
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = os.path.join(TASK_DIR, f"南大_补充邮箱_{ts}.csv")
    with open(out_csv, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(["姓名", "邮箱", "学院"])
        for name, (email, dept) in sorted(all_new_emails.items()):
            w.writerow([name, email, dept])
    print(f"\n✅ 总计发现 {len(all_new_emails)} 个新邮箱")
    print(f"保存: {out_csv}")

    return out_csv, all_new_emails

if __name__ == "__main__":
    asyncio.run(main())
