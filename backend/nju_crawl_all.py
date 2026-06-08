"""
南京大学全校教师邮箱爬取 - V3 精确版本
策略：多阶段提取 + 纯 Python 端过滤 + 智能详情页识别
"""
import asyncio
import re
import csv
import os
from datetime import datetime
from collections import Counter
from playwright.async_api import async_playwright

OUTPUT_DIR = r'D:\Work\test\UniEmailAgent\backend\outputs\d73dcbad-a0ca-4034-9c67-d4e6c0966cbf'
ALL_RESULTS = []
VISITED_URLS = set()
ALL_VISITED_DETAIL_URLS = set()

# 邮箱提取正则
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# 导航关键词黑名单
NAV_KW = {
    '概况','简介','新闻','通知','公告','招生','培养','就业','学位',
    '学科','科研','学术','党建','工会','校友','捐赠','图书馆','校园',
    '地图','网站','登录','邮箱','联系','欢迎','首页','返回','更多',
    '详情','查看','下载','师资','教师','硕士','本科','研究','行政',
    '管理','教职','荣休','访问','系科','教研','诚聘','师德','监督',
    '信箱','机构','设置','领导','人才','学校','学院','搜索','服务',
    '导航','English','加入','收藏','成果','转化','奖励','项目','专利',
    '交流','合作','国际化','中科院','院士','博士后','实验','技术',
    '党群','团学','学生','活动','实践','基地','平台','基金','信息',
    '公开','奖助','出国','留学','考试','课程','教学',
    '杰出','方向','机构','队伍','全部','名单','导师','在职','兼职',
    '专任','离退休','人才队伍','按岗位','按系别','教工','人事','财务',
    '外事','资产','安全','简报','部门','委员会','职能','标志','学位',
    '报名','注册','系统','平台','空间','预约','教师登录','书记','院长',
    '监督','举报','师德师风','学术型','专业型','研究生导师','跨学科',
    '联系方式','院务信箱','学院概览','一代哲人','规章制度','党群工作',
    '学生工作','行政事务','财务管理','科研管理','人才培养','国际合作',
    '学院概况','新闻公告','教职员工','招生培训','教学培养','科学研究',
    '实践平台','党群建设','学生活动','校友天地','社会培训','南京大学',
    '学校主页','首页信息','历史沿革','组织机构','学科介绍','成果速递',
    '科技奖励','成果转化','学术交流','国际合作','校友与发展','终身教育',
    '法科百年','中德所','继续教育','相关下载','教研室','学术研究',
    '本科生招生','研究生招生','本科生教育','研究生教育','教学成果',
    '学工园地','最新通知','研究方向','研究机构','仪器共享',
    '办事指南','安全园地','校友工作','部门简介','返校服务','时光印记',
    '捐赠项目','我要捐赠','学院标志','诚聘英才','师德监督','院长信箱',
    '学院简介','科系设置','师资队伍','新闻动态','学术活动',
    '出境公示','简报','杰出人才','全部名单','学术型研究生导师',
    '专业型研究生导师','离退休人员','人才招聘','本科生','研究生',
    '留学生','非学历教育','远程教育','学生交流','科技动态','社科动态',
    '科研机构','学术期刊','校园地图','南大校历','图书馆','档案馆',
    '信息化服务','心理健康教育','后勤服务','在线支付','超算服务',
    '加入收藏','教师登录入口','院内办公','绩效系统',
    '团建工作','工会工作','党建工作',
    '人事工作','科研工作','财务工作','外事工作','资产管理','会议室预约',
    '电子大屏','我要捐赠','鸣谢','本科生教育','研究生教育',
    '实践教学','交流合作','党建工作','团学动态','国情教育','教工之家',
    '微服务','教务处','研究生院','财务处',
}

# 职称关键词
TITLE_KW = ['教授','副教授','助理教授','讲师','研究员','副研究员','助理研究员',
            '工程师','高级工程师','院士','博导','硕导','长江学者','杰青','优青',
            '院长','副院长','系主任','副主任','所长','副所长','博士后',
            '高级实验师','实验师','主任','秘书','教务员','辅导员',
            '准聘副教授','准聘助理教授','长聘教授','长聘副教授',
            '助理教授','助理研究员','实验师','工程师']


def anti_spam_recover(text):
    text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\[@\]\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(@\)\s*', '@', text, flags=re.IGNORECASE)
    return text.replace('#@', '@')


def extract_emails(text):
    return EMAIL_RE.findall(anti_spam_recover(text))


def is_public_email(email):
    prefix = email.split('@')[0].lower()
    for p in ['webmaster','admin','office','info','master','root','postmaster',
              'wxyxz','xwcb','bgs','dangzheng','yuanban','dangban','renshi',
              'jiaowu','xuegong','tuanwei','yanjiusheng','gysj','gyyz','glxb',
              'history','library','nic','support','help']:
        if prefix == p or prefix.startswith(p + '_'):
            return True
    return False


def extract_title(text):
    """从页面文本中提取职称"""
    found = set()
    for kw in TITLE_KW:
        if kw in text:
            found.add(kw)
    return '、'.join(found) if found else ''


def clean_teacher_name(raw_text):
    """
    从链接文本中提取教师姓名
    处理格式: "吕建(院士、博导)" → "吕建", "张三" → "张三"
    """
    text = raw_text.strip().replace(' ', '').replace('　', '').replace(' ', '')
    if not text:
        return None

    # 先尝试直接匹配纯中文名
    if re.match(r'^[一-鿿]{2,4}$', text):
        return text

    # 尝试去掉括号内容（中英文括号）
    clean = re.sub(r'[（(][^）)]*[）)]', '', text).strip()
    if clean and re.match(r'^[一-鿿]{2,4}$', clean):
        return clean

    # 尝试取前2-4个中文字
    match = re.match(r'^([一-鿿]{2,4})', text)
    if match:
        return match.group(1)

    return None


def is_detail_url(url):
    """判断URL是否为教师详情页"""
    lower = url.lower()
    # 详情页特征：包含 /i数字.htm 或 8位数字日期 或 page.htm
    if re.search(r'/i\d+\.htm', lower):
        return True
    if re.search(r'/\d{8}/', lower):
        return True
    if 'page.htm' in lower:
        return True
    return False


def is_list_url(url):
    """判断URL是否为列表/导航页"""
    lower = url.lower()
    if re.search(r'/list\.htm', lower):
        return True
    if re.search(r'/index\.htm', lower):
        return True
    if 'main.htm' in lower or 'main.psp' in lower:
        return True
    return False


def is_nav_text(text):
    """判断文本是否为导航关键词"""
    if text in NAV_KW:
        return True
    for kw in NAV_KW:
        if kw in text and len(kw) >= 2:
            return True
    return False


def save_csv(filename, records):
    filepath = os.path.join(OUTPUT_DIR, filename)
    seen = set()
    unique = []
    for r in records:
        key = (r['name'], r.get('email', ''))
        if key not in seen:
            seen.add(key)
            unique.append(r)
    with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['序号', '姓名', '邮箱', '学院', '职称', '主页链接'])
        w.writeheader()
        for i, r in enumerate(unique, 1):
            w.writerow({'序号': i, '姓名': r['name'], '邮箱': r.get('email', ''),
                       '学院': r['department'], '职称': r.get('title', ''),
                       '主页链接': r.get('url', '')})
    return filepath


async def extract_teacher_links(page):
    """
    从当前页面提取教师候选链接（纯 Python 端过滤）
    """
    # 滚动以触发懒加载
    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    await asyncio.sleep(1)

    # 获取所有链接
    raw_links = await page.evaluate("""
        Array.from(document.querySelectorAll('a')).map(a => ({
            text: a.textContent.trim().replace(/\\s+/g, ''),
            href: a.href
        }))
    """)

    candidates = []
    for link in raw_links:
        href = link['href']
        raw_text = link['text']

        # 跳过无效链接
        if not href or 'javascript' in href or 'mailto' in href or href.startswith('#'):
            continue
        if not href.startswith('http'):
            continue

        # 提取姓名
        name = clean_teacher_name(raw_text)
        if not name:
            continue
        if is_nav_text(name):
            continue

        # 只保留 nju.edu.cn 站内链接 + 详情页特征
        if 'nju.edu.cn' not in href.lower():
            continue
        if is_list_url(href):
            continue
        if not is_detail_url(href):
            continue

        candidates.append({
            'name': name,
            'url': href,
        })

    return candidates


async def fetch_teacher_detail(browser, dept_name, entry):
    """访问教师详情页，提取邮箱和职称"""
    url = entry['url']
    if url in VISITED_URLS:
        return None
    VISITED_URLS.add(url)

    p = await browser.new_page()
    try:
        await p.goto(url, wait_until='domcontentloaded', timeout=20000)
        await asyncio.sleep(1)
        text = await p.evaluate('() => document.body.innerText')
        emails = [e.lower() for e in extract_emails(text) if not is_public_email(e)]

        name = entry['name']
        title = extract_title(text[:800])

        result = {'name': name, 'department': dept_name,
                 'title': title, 'url': url}
        result['email'] = emails[0] if emails else ''

        return result
    except Exception as e:
        return None
    finally:
        await p.close()


async def crawl_dept(context, browser, dept_name, list_urls):
    """爬取单个学院"""
    page = await context.new_page()
    all_candidates = []

    for url in list_urls:
        loaded = False
        for attempt in range(2):
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(2)
                loaded = True
                break
            except Exception as e:
                if attempt == 0:
                    await asyncio.sleep(3)
                else:
                    print(f'  [ERR] {dept_name}: {url[:50]} - {str(e)[:60]}')

        if not loaded:
            continue

        candidates = await extract_teacher_links(page)
        all_candidates.extend(candidates)

    await page.close()

    # 去重
    seen = set()
    unique = []
    for e in all_candidates:
        key = (e['name'], e['url'])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    print(f'  [列表] {dept_name}: {len(unique)} 个教师')
    return unique


async def process_teachers(browser, dept_name, entries):
    """处理教师详情页"""
    if not entries:
        return [], 0, 0

    sem = asyncio.Semaphore(5)
    results = []
    total_attempted = 0
    email_count = 0

    async def fetch_one(entry):
        async with sem:
            return await fetch_teacher_detail(browser, dept_name, entry)

    for i in range(0, len(entries), 30):
        batch = entries[i:i + 30]
        batch_results = await asyncio.gather(*[fetch_one(e) for e in batch])
        for r in batch_results:
            if r:
                results.append(r)
                ALL_RESULTS.append(r)
                if r.get('email'):
                    email_count += 1

        total_attempted += len(batch)

        # 每批保存
        if len(ALL_RESULTS) % 50 == 0 and len(ALL_RESULTS) > 0:
            save_csv('南京大学_临时保存.csv', ALL_RESULTS)

    print(f'  [完成] {dept_name}: {total_attempted} 条 ({email_count} 个邮箱)')
    return results, total_attempted, email_count


async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )

        depts = [
            ('文学院', ['https://chin.nju.edu.cn/szdw/xrjs/index.html']),
            ('历史学院', ['https://history.nju.edu.cn/28475/list.htm']),
            ('哲学学院', ['https://philo.nju.edu.cn/4712/list.htm']),
            ('新闻传播学院', ['https://jc.nju.edu.cn/jzyg/zzjs.htm',
                          'https://jc.nju.edu.cn/jzyg/zzjs/js.htm']),
            ('法学院', ['https://law.nju.edu.cn/szdw/zzjs1/js.htm',
                      'https://law.nju.edu.cn/szdw/zzjs1/fjs.htm',
                      'https://law.nju.edu.cn/szdw/zzjs1/zljs.htm']),
            ('外国语学院', ['https://sfs.nju.edu.cn/szdw/index.html']),
            ('政府管理学院', ['https://public.nju.edu.cn/szdw/qzjs/index.html']),
            ('国际关系学院', ['https://sis.nju.edu.cn/']),
            ('信息管理学院', ['https://im.nju.edu.cn/szll/zzjs.htm']),
            ('社会学院', ['https://sociology.nju.edu.cn/qzjs/list.htm']),
            ('数学学院', ['https://math.nju.edu.cn/jzyg/index.html']),
            ('物理学院', ['https://physics.nju.edu.cn/szdw/qbmd/index.html']),
            ('天文与空间科学学院', ['https://astronomy.nju.edu.cn/szll/szgk/index.html']),
            ('化学学院', ['https://chem.nju.edu.cn/szll/list.htm']),
            ('计算机科学与技术系', [
                'https://cs.nju.edu.cn/2639/list.htm',
                'https://cs.nju.edu.cn/2640/list.htm',
                'https://cs.nju.edu.cn/zzp/list.htm',
            ]),
            ('软件学院', ['https://software.nju.edu.cn/']),
            ('人工智能学院', ['http://ai.nju.edu.cn/people/list.htm']),
            ('智能科学与技术学院', ['https://is.nju.edu.cn/57159/list.htm']),
            ('集成电路学院', ['https://ic.nju.edu.cn/main.htm']),
            ('电子科学与工程学院', ['https://ese.nju.edu.cn/22542/list.htm']),
            ('现代工程与应用科学学院', ['https://eng.nju.edu.cn/zrjswyjxlwhbshwzp/list.htm']),
            ('环境学院', ['http://hjxy.nju.edu.cn/szdw/index.html']),
            ('地球科学与工程学院', ['https://es.nju.edu.cn/25235/list.htm']),
            ('地理与海洋科学学院', ['http://sgos.nju.edu.cn/62681/list.htm']),
            ('大气科学学院', ['http://as.nju.edu.cn/js/list.htm']),
            ('生命科学学院', ['https://life.nju.edu.cn/szdw/list.htm']),
            ('医学院', ['https://med.nju.edu.cn/10649/list.htm']),
            ('工程管理学院', ['https://sme.nju.edu.cn/2003/list.htm']),
            ('建筑与城市规划学院', ['http://arch.nju.edu.cn/szdw/index.html']),
            ('匡亚明学院', ['https://dii.nju.edu.cn/']),
            ('海外教育学院', ['http://hwxy.nju.edu.cn/szdw/index.html']),
            ('马克思主义学院', ['http://marxism.nju.edu.cn/szdw/js.htm']),
            ('艺术学院', ['https://art.nju.edu.cn/55208/list.htm']),
            ('教育研究院', ['https://edu.nju.edu.cn/8746/list.htm']),
            ('体育部', ['https://tyb.nju.edu.cn/jbgk/szdw/index.html']),
            ('智能软件与工程学院', ['https://ise.nju.edu.cn/']),
            ('能源与资源学院', ['https://sser.nju.edu.cn/']),
            ('机器人与自动化学院', ['https://ra.nju.edu.cn/']),
            ('生物医学工程学院', ['https://bme.nju.edu.cn/']),
            ('数字经济与管理学院', ['https://sdem.nju.edu.cn/main.htm']),
            ('前沿科学学院', ['https://frontier.nju.edu.cn/main.htm']),
            ('南京赫尔辛基大气学院', ['http://nh.nju.edu.cn/']),
            ('现代生物研究院', ['https://imb.nju.edu.cn/']),
            ('国际地球系统科学研究所', ['https://essi.nju.edu.cn/main.htm']),
            ('国家卓越工程师学院', ['https://gcee.nju.edu.cn/']),
            ('大学外语部', ['http://dafls.nju.edu.cn/']),
        ]

        batch_size = 3
        total_batches = (len(depts) - 1) // batch_size + 1

        for batch_start in range(0, len(depts), batch_size):
            batch = depts[batch_start:batch_start + batch_size]
            batch_num = batch_start // batch_size + 1
            print(f'\n--- 批次 {batch_num}/{total_batches} ---')

            # 并行抓取列表页
            entries_list = await asyncio.gather(*[
                crawl_dept(context, browser, dept_name, urls)
                for dept_name, urls in batch
            ])

            # 串行处理详情页
            for (dept_name, _), entries in zip(batch, entries_list):
                if entries:
                    await process_teachers(browser, dept_name, entries)

            # 进度报告
            ec = sum(1 for r in ALL_RESULTS if r.get('email'))
            print(f'[进度] {len(ALL_RESULTS)} 条, {ec} 个邮箱')
            save_csv('南京大学_临时保存.csv', ALL_RESULTS)

        await context.close()
        await browser.close()

    # 最终统计
    email_c = sum(1 for r in ALL_RESULTS if r.get('email'))
    no_email_c = sum(1 for r in ALL_RESULTS if not r.get('email'))
    print(f'\n完成! 总 {len(ALL_RESULTS)} 条 (含邮箱 {email_c}, 无邮箱 {no_email_c})')

    stats = {}
    for r in ALL_RESULTS:
        d = r['department']
        if d not in stats:
            stats[d] = {'t': 0, 'e': 0}
        stats[d]['t'] += 1
        if r.get('email'):
            stats[d]['e'] += 1
    for d, s in sorted(stats.items()):
        print(f'  {d:25s}: {s["t"]:4d} 条 ({s["e"]} 邮箱)')

    final = save_csv('南京大学_全校教师邮箱_V1.0.1.csv', ALL_RESULTS)
    print(f'\n最终文件: {final}')


if __name__ == '__main__':
    asyncio.run(main())
