"""
南京大学全校教师邮箱爬取 v3 - 最终版
- 使用已验证的URL模式
- 针对不同学院使用不同的提取策略
- 先收集所有教师条目，再并行访问详情页
"""

import asyncio, csv, re, os
from datetime import datetime
from collections import Counter
from playwright.async_api import async_playwright

TASK_DIR = r"D:\Work\test\UniEmailAgent\backend\outputs\d73dcbad-a0ca-4034-9c67-d4e6c0966cbf"
PUBLIC_EMAIL_PREFIXES = ['webmaster','admin','office','info','master','root','postmaster']
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

def extract_emails(text):
    text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
    text = text.replace('#@', '@')
    return [e.lower() for e in EMAIL_RE.findall(text)
            if not any(e.lower().startswith(p) for p in PUBLIC_EMAIL_PREFIXES)]

# ============ 每个学院配置：名称+列表页URL+提取策略 ============
# type: 'page.htm'=找page.htm链接, 'info'=找info/链接, 'text'=从长文本解析
DEPT_CONFIG = [
    # === page.htm 类型 ===
    ("计算机学院-教授", "cs.nju.edu.cn", "https://cs.nju.edu.cn/2639/list.htm"),
    ("计算机学院-副教授", "cs.nju.edu.cn", "https://cs.nju.edu.cn/2640/list.htm"),
    ("计算机学院-准长聘", "cs.nju.edu.cn", "https://cs.nju.edu.cn/zzp/list.htm"),
    ("计算机学院-跨学科博导", "cs.nju.edu.cn", "https://cs.nju.edu.cn/kxkbd/list.htm"),
    ("计算机学院-高工", "cs.nju.edu.cn", "https://cs.nju.edu.cn/2642/list.htm"),
    ("计算机学院-技术人员", "cs.nju.edu.cn", "https://cs.nju.edu.cn/2643/list.htm"),
    ("哲学学院", "philo.nju.edu.cn", "https://philo.nju.edu.cn/4712/list.htm"),
    ("社会学院", "sociology.nju.edu.cn", "https://sociology.nju.edu.cn/qzjs/list.htm"),
    ("医学院", "med.nju.edu.cn", "https://med.nju.edu.cn/10649/list.htm"),
    ("人工智能学院", "ai.nju.edu.cn", "https://ai.nju.edu.cn/people/list.htm"),
    ("医学院-院士", "med.nju.edu.cn", "https://med.nju.edu.cn/10871/list.htm"),
    ("地理与海洋科学学院", "sgos.nju.edu.cn", "https://sgos.nju.edu.cn/62681/list.htm"),

    # === info/ 类型 ===
    ("新闻传播学院", "jc.nju.edu.cn", "https://jc.nju.edu.cn/jzyg/zzjs.htm"),

    # === 解析长文本型（数学学院） ===
    ("数学学院", "math.nju.edu.cn", "https://math.nju.edu.cn/jzyg/apypl/index.html"),

    # === 物理学院 - 全部名单（index.html带教师照片链接） ===
    ("物理学院", "physics.nju.edu.cn", "https://physics.nju.edu.cn/szdw/qbmd/index.html"),
    ("天文与空间科学学院", "astronomy.nju.edu.cn", "https://astronomy.nju.edu.cn/szll/szgk/index.html"),

    # === 教育研究院 - 特殊list.htm ===
    ("教育研究院", "edu.nju.edu.cn", "https://edu.nju.edu.cn/8746/list.htm"),

    # === 其他使用page.htm或通用模式的学院 ===
    ("文学院", "chin.nju.edu.cn", "https://chin.nju.edu.cn/szdw/xrjs/index.html"),
    ("历史学院", "history.nju.edu.cn", "https://history.nju.edu.cn/28475/list.htm"),
    ("外国语学院", "sfs.nju.edu.cn", "https://sfs.nju.edu.cn/szdw/index.html"),
    ("政府管理学院", "public.nju.edu.cn", "https://public.nju.edu.cn/szdw/qzjs/index.html"),
    ("国际关系学院", "sis.nju.edu.cn", "https://sis.nju.edu.cn/jsrk/list.htm"),
    ("信息管理学院", "im.nju.edu.cn", "https://im.nju.edu.cn/szll/zzjs.htm"),
    ("马克思主义学院", "marxism.nju.edu.cn", "https://marxism.nju.edu.cn/szdw/js.htm"),
    ("化学学院", "chem.nju.edu.cn", "https://chem.nju.edu.cn/szll/list.htm"),
    ("软件学院", "software.nju.edu.cn", "https://software.nju.edu.cn/szll/szdw/index.html"),
    ("电子科学与工程学院", "ese.nju.edu.cn", "https://ese.nju.edu.cn/kxkbsszdjs/list.htm"),
    ("现代工程与应用科学学院", "eng.nju.edu.cn", "https://eng.nju.edu.cn/43271/list.htm"),
    ("环境学院", "hjxy.nju.edu.cn", "https://hjxy.nju.edu.cn/szdw/index.html"),
    ("地球科学与工程学院", "es.nju.edu.cn", "https://es.nju.edu.cn/25235/list.htm"),
    ("大气科学学院", "as.nju.edu.cn", "https://as.nju.edu.cn/js/list.htm"),
    ("南京赫尔辛基大气学院", "nh.nju.edu.cn", "https://nh.nju.edu.cn/xyzl/szdw/nhjs.htm"),
    ("生命科学学院", "life.nju.edu.cn", "https://life.nju.edu.cn/szdw/list.htm"),
    ("工程管理学院", "sme.nju.edu.cn", "https://sme.nju.edu.cn/rxjs/list.htm"),
    ("匡亚明学院", "dii.nju.edu.cn", "https://dii.nju.edu.cn/lsjs/list.htm"),
    ("建筑与城市规划学院", "arch.nju.edu.cn", "https://arch.nju.edu.cn/szdw/index.html"),
    ("艺术学院", "art.nju.edu.cn", "https://art.nju.edu.cn/55208/list.htm"),
    ("智能科学与技术学院", "is.nju.edu.cn", "https://is.nju.edu.cn/57159/list.htm"),
    ("智能软件与工程学院", "ise.nju.edu.cn", "https://ise.nju.edu.cn/szll/zjzjs.htm"),
    ("集成电路学院", "ic.nju.edu.cn", "https://ic.nju.edu.cn/zzjs/list.htm"),
    ("数字经济与管理学院", "sdem.nju.edu.cn", "https://sdem.nju.edu.cn/56976/list.htm"),
    ("能源与资源学院", "sser.nju.edu.cn", "https://sser.nju.edu.cn/szll.htm"),
    ("机器人与自动化学院", "ra.nju.edu.cn", "https://ra.nju.edu.cn/szll/zzjs/index.html"),
    ("前沿科学学院", "frontier.nju.edu.cn", "https://frontier.nju.edu.cn/zrjs/list.htm"),
    ("生物医学工程学院", "bme.nju.edu.cn", "https://bme.nju.edu.cn/szll/zzjs/index.html"),
    ("海外教育学院", "hwxy.nju.edu.cn", "https://hwxy.nju.edu.cn/szdw/zc/yyjs/index.html"),
    ("体育部", "tyb.nju.edu.cn", "https://tyb.nju.edu.cn/jbgk/szdw/index.html"),
    ("人文社会科学高级研究院", "ias.nju.edu.cn", "https://ias.nju.edu.cn/13109/list.htm"),
    ("现代生物研究院", "imb.nju.edu.cn", "https://imb.nju.edu.cn/"),
    ("地球系统科学研究所", "essi.nju.edu.cn", "https://essi.nju.edu.cn/main.htm"),

    # 补充列表
    ("社会学院(心理学系)", "sociology.nju.edu.cn", "https://sociology.nju.edu.cn/xlxx/list.htm"),
    ("政府管理学院(兼职)", "public.nju.edu.cn", "https://public.nju.edu.cn/szdw/jzjs/jzjs/index.html"),
]

async def extract_teachers(page, dept_name, domain, url):
    """从列表页提取教师"""
    await page.goto(url, wait_until='domcontentloaded', timeout=30000)
    await asyncio.sleep(2.5)
    teachers = []

    # 数学学院特殊处理
    if "数学" in dept_name:
        entries = await page.evaluate('''() => {
            const items = [];
            document.querySelectorAll('a[href*="apypl/"]').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href;
                if (href.includes('.html') && text.length > 0) {
                    const m = text.match(/^[\\u4e00-\\u9fff]{2,4}/);
                    if (m) {
                        let title = '';
                        const tm = text.match(/(教授|副教授|助理教授|讲师|博士后)/);
                        if (tm) title = tm[1];
                        items.push({name: m[0], title, url: href});
                    }
                }
            });
            return items;
        }''')
        return entries

    # 新闻传播学院 - info/链接
    if "新闻" in dept_name:
        entries = await page.evaluate('''() => {
            const items = [];
            document.querySelectorAll('a[href*="info/"]').forEach(a => {
                const t = a.textContent.trim();
                if (/^[\\u4e00-\\u9fff]{2,4}$/.test(t)) {
                    items.push({name: t, url: a.href, title: ''});
                }
            });
            return items;
        }''')
        return entries

    # 物理学院 - 全部名单页面有很多照片列表
    if "物理" in dept_name or "天文" in dept_name:
        entries = await page.evaluate('''() => {
            const items = [];
            const navKW = new Set(['概况','新闻','通知','公告','科研','学术','党建','工会',
                '校友','联系','首页','返回','更多','下载','搜索','登录','招生','培养',
                '就业','课程','教学','学生','国际','诚聘','规章','制度','活动','实践',
                '基金','奖励','服务','系统','师资','队伍','研究','机构','项目','成果',
                '荣誉','招聘','安全','学院','系所','重点','基地','平台','中心','大学']);
            document.querySelectorAll('a').forEach(a => {
                const t = a.textContent.trim();
                const href = a.href;
                if (/^[\\u4e00-\\u9fff]{2,4}$/.test(t) && href && !href.startsWith('javascript:')
                    && !href.includes('list.htm') && !navKW.has(t)
                    && !t.includes('/') && !t.includes('.')) {
                    items.push({name: t, url: href, title: ''});
                }
            });
            return items;
        }''')
        return entries

    # 教育研究院 - 专用处理（教师以拼音缩写/list.htm形式展现）
    if "教育研究" in dept_name:
        entries = await page.evaluate('''() => {
            const items = [];
            document.querySelectorAll('a').forEach(a => {
                const t = a.textContent.trim();
                const href = a.href;
                if (/^[\\u4e00-\\u9fff]{2,4}$/.test(t) && href && href.includes('edu.nju.edu.cn')
                    && href.includes('list.htm') && !href.endsWith('main.htm')
                    && !t.includes('概况') && !t.includes('简介') && !t.includes('通知')
                    && !t.includes('招生') && !t.includes('培养') && !t.includes('学生')) {
                    let title = '';
                    const tm = t.match(/(教授|副教授|讲师|研究员)/);
                    if (tm) title = tm[1];
                    items.push({name: t, title, url: href});
                }
            });
            return items;
        }''')
        return entries

    # page.htm 通用策略
    page_links = await page.evaluate('''() => {
        const items = [];
        const navKW = new Set(['概况','简介','历史','沿革','通知','新闻','公告','科研','学术',
            '党建','工会','校友','捐赠','联系','成果','基地','培养','招生','就业','学位',
            '本科','研究','机构','项目','合作','交流','人才','招聘','规章','制度','委员',
            '领导','联系','在线','投稿','系统','登录','师德','奖励','基金','课程','教室',
            '实践','国际','诚聘','相关','办事','安全','下载','活动','荣誉','加入','返回',
            '更多','参观','培训','继续','教育','学生','天地','记录','记忆','奖助','奖学',
            '服务','科技','组织','纪检','巡察','申报','评估','督导','专栏','百年','院庆',
            '系庆','重点','技术','平台','基地','合作','交流','成果','荣誉','项目','机构',
            '学科','方向','培养','方案','指南','经费','财务','资产','文档','公开','人事',
            '动态','招聘','登录','师德','监督','信箱','团建','党群','工会','委员会',
            '财务','资产','安全','文档','下载','学校主页','首页信息','学院概况','学院简介',
            '联系方式','相关下载','师资队伍','教职员工','行政教辅','退休人员','访问学者',
            '荣休教师','在职教师','组织机构','诚聘英才','人才培养','学术研究','学生工作',
            '党团建设','学科介绍','研究方向']);
        document.querySelectorAll('a[href*="page.htm"]').forEach(a => {
            const text = a.textContent.trim();
            const href = a.href;
            if (text.length > 0 && text.length < 40 && !href.includes('javascript:')) {
                if (navKW.has(text)) return;
                for (let kw of navKW) {
                    if (text.includes(kw)) return;
                }
                items.push({text, href});
            }
        });
        return items;
    }''')

    for link in page_links:
        name = re.sub(r'[（(].*?[）)]', '', link['text']).strip().replace(' ', '')
        if re.match(r'^[一-鿿]{2,4}$', name):
            title = ''
            tm = re.search(r'[（(]([^）)]+)[）)]', link['text'])
            if tm:
                t = tm.group(1)
                for kw in ['教授','副教授','助理教授','讲师','研究员','副研究员','工程师','博士后','博导','硕导']:
                    if kw in t: title = kw; break
                if not title: title = t
            teachers.append({'name': name, 'title': title, 'url': link['href'], 'dept': dept_name})

    # 如果没有page.htm链接，尝试通用方法
    if not teachers:
        all_links = await page.evaluate('''() => {
            const items = [];
            const navKW = new Set(['概况','简介','通知','新闻','公告','招生','联系','返回','首页',
                '更多','下载','搜索','登录','党建','工会','校友','科研','学术','教学',
                '培养','就业','课程','师资','队伍','教育','学生','国际','交流','合作',
                '研究','机构','项目','成果','荣誉','招聘','诚聘','规章','制度','安全',
                '活动','实践','基金','奖励','服务','系统','在线','投稿','学院','系所',
                '重点','基地','平台','实验室','中心','大学','南大','南京','学校主页',
                '加入收藏','用户登录','内网入口']);
            document.querySelectorAll('a').forEach(a => {
                const t = a.textContent.trim();
                const href = a.href;
                if (/^[\\u4e00-\\u9fff]{2,4}$/.test(t) && href && !href.startsWith('javascript:')
                    && !href.includes('list.htm') && !navKW.has(t)) {
                    items.push({name: t, url: href, title: ''});
                }
            });
            return items;
        }''')
        teachers = all_links

    # 去重
    seen = set()
    unique = []
    for t in teachers:
        if t['url'] not in seen and not t['url'].endswith(url.rstrip('/')):
            seen.add(t['url'])
            unique.append(t)
    return unique


async def crawl_details(sem, browser, teacher):
    """爬取单个教师详情页"""
    async with sem:
        page = await browser.new_page()
        try:
            await page.goto(teacher['url'], wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(0.8)
            body = await page.evaluate('() => document.body.innerText')
            emails = extract_emails(body)

            if not teacher.get('title'):
                for kw in ['教授','副教授','助理教授','讲师','研究员','副研究员','工程师','博士后','博导','硕导']:
                    if kw in body[:3000]:
                        teacher['title'] = kw
                        break

            await page.close()
            return {**teacher, 'email': emails[0] if emails else ''}
        except:
            await page.close()
            return {**teacher, 'email': ''}


async def main():
    print(f"南京大学全校教师邮箱爬取 v3 - {len(DEPT_CONFIG)}个学院")
    print("=" * 60)

    all_teachers = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

        # Phase 1: 提取教师条目
        print("\nPhase 1: 提取教师条目")
        for i, (dept_name, domain, url) in enumerate(DEPT_CONFIG, 1):
            try:
                page = await context.new_page()
                teachers = await extract_teachers(page, dept_name, domain, url)
                await page.close()
                for t in teachers:
                    t['dept'] = dept_name
                all_teachers.extend(teachers)
                print(f"  [{i:2d}] {dept_name:20s} → {len(teachers):3d} 教师")
            except Exception as e:
                print(f"  [{i:2d}] {dept_name:20s} → 失败: {e}")

        # URL去重
        seen_urls = set()
        deduped = []
        for t in all_teachers:
            if t['url'] not in seen_urls:
                seen_urls.add(t['url'])
                deduped.append(t)
        all_teachers = deduped
        print(f"\nPhase 1 完成: 总计{len(all_teachers)}位教师")

        # Phase 2: 并行提取邮箱
        print("\nPhase 2: 提取邮箱")
        sem = asyncio.Semaphore(12)
        results = []
        batch_size = 30
        for bs in range(0, len(all_teachers), batch_size):
            batch = all_teachers[bs:bs+batch_size]
            tasks = [crawl_details(sem, browser, t) for t in batch]
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
            ec = len([r for r in results if r['email']])
            print(f"  进度: {len(results)}/{len(all_teachers)} | 邮箱: {ec}")

        await browser.close()

    # 去除学院名中的括号分类（如"计算机学院-教授"→"计算机学院"）
    def normalize_dept(d):
        d = re.sub(r'[-(（].*?[)）]', '', d).strip()
        d = re.sub(r'计算机学院.*', '计算机学院', d)
        return d

    for r in results:
        r['dept'] = normalize_dept(r['dept'])

    # 去重
    seen_emails, seen_urls, final = set(), set(), []
    for r in results:
        if r['email']:
            if r['email'] not in seen_emails:
                seen_emails.add(r['email'])
                final.append(r)
        else:
            if r['url'] not in seen_urls:
                seen_urls.add(r['url'])
                final.append(r)

    # 移除导航假条目
    NAV_NAMES = set(['院系领导','专业设置','文艺学','语言学及应用语言学','汉语言文字学',
        '中国古典文献学','中国古代文学','中国现当代文学','比较文学与世界文学',
        '戏剧与影视学','行政管理','本科生','研究生','博士后','暑期班','培训班',
        '海外班','退休教师'])
    final = [r for r in final if r['name'] not in NAV_NAMES]

    # 写入CSV
    csv_path = os.path.join(TASK_DIR, "南京大学_全校教师邮箱_V1.0.0.csv")
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['序号','姓名','邮箱','学院','职称','主页链接'])
        for i, r in enumerate(final, 1):
            writer.writerow([i, r['name'], r['email'], r['dept'], r['title'], r['url']])

    print(f"\n{'='*60}")
    print(f"完成! 总计{len(final)}位教师, 有邮箱{len([r for r in final if r['email']])}人")
    print(f"CSV: {csv_path}")

    dept_count = Counter(r['dept'] for r in final)
    print("\n各学院教师数:")
    for d, c in sorted(dept_count.items(), key=lambda x: -x[1]):
        ec = len([r for r in final if r['dept']==d and r['email']])
        print(f"  {d}: {c}人 (邮箱:{ec})")


if __name__ == '__main__':
    asyncio.run(main())
