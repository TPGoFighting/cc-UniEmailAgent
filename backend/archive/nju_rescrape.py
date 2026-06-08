"""
南京大学教师邮箱 — 改进版增量爬虫

修复问题：
1. 邮箱正则过滤 CSS/JS 误提取（排除 .css, .js, 非邮件域名）
2. 检查 iframe 嵌套页面
3. 检查 meta 标签中的邮箱
4. 更好的反爬恢复
5. 并发 3-5 个学院，每个教师独立 page
"""

import asyncio
import re
import csv
import json
import logging
from pathlib import Path
from datetime import datetime
from collections import Counter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

# 输也目录
OUTPUT_DIR = Path(__file__).parent.parent / "outputs"

# 更严格的邮箱正则（排除 .css, .js 等）
STRICT_EMAIL_RE = re.compile(
    r'(?<![a-zA-Z0-9._%+-])[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9-]+\.'
    r'(?!(?:css|js|png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|eot|json|xml|zip|tar|gz|exe|dll|bin|map)\b)'
    r'(?:[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)'
)

# 宽松邮箱正则（用于扫描）
LOOSE_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# 反爬格式恢复
ANTI_CRAWL_REPLACEMENTS = [
    (re.compile(r'\s*\[at\]\s*', re.I), '@'),
    (re.compile(r'\s*\(at\)\s*', re.I), '@'),
    (re.compile(r'\s*\[@\]\s*'), '@'),
    (re.compile(r'\s*\(@\)\s*'), '@'),
    (re.compile(r'#@'), '@'),
]

# 导航链接黑名单
NAV_KEYWORDS = [
    '概况', '新闻', '通知', '公告', '招生', '培养', '就业', '学位', '学科',
    '科研', '学术', '党建', '工会', '校友', '捐赠', '图书馆', '校园', '地图',
    '网站', '登录', '邮箱', '联系我们', '欢迎', '首页', '返回', '更多', '详情',
    '查看', '下载', '师资', '教师', '博士', '硕士', '本科', '研究', '行政',
    '管理', '教职', '荣休', '访问', '系科', '教研', '诚聘', 'copyright',
    '书记信箱', '院长信箱', '师德师', '师资队', '现任教', '学院概', '管理架',
    '系科设', '教研机', '研究生', '学生工作', '党政', '党团', '学工',
    '专业建设', '实验教学', '实践教学', '双语课程', '教学成果', '精品课程',
    '资源库', '网络', '中心', '论坛', '博客', '微博', '微信', 'bbs',
]

# 公共邮箱前缀
PUBLIC_EMAIL_PREFIXES = [
    'webmaster', 'admin', 'office', 'info', 'master', 'root', 'postmaster',
    'wxyxz', 'xwcb', 'bgs', 'dangzheng', 'yuanban', 'dangban', 'renshi',
    'jiaowu', 'xuegong', 'tuanwei', 'yanjiusheng', 'gysj', 'gyyz', 'glxb',
    'support', 'service', 'contact', 'webadmin', 'sysadmin', 'notice',
    'job', 'career', 'hr', 'recruit', 'graduate', 'student', 'dean',
    'party', 'youth', 'library', 'president', 'secretary',
]

# 合法职称
VALID_TITLES = [
    '教授', '副教授', '助理教授', '讲师', '研究员', '副研究员', '助理研究员',
    '工程师', '高级工程师', '院士', '博导', '硕导', '长江学者', '杰青', '优青',
    '院长', '副院长', '系主任', '副主任', '所长', '副所长', '博士后',
    '高级实验师', '实验师', '教授级高工', '教授级高级工程师',
    '助理工程师', '研究实习员', '助理实验师', '实验员',
]

VALID_TITLE_RE = re.compile('|'.join(re.escape(t) for t in VALID_TITLES))

# 学院配置（名称, 列表页URL, 说明）
# 从 nju_v3.py 获取完整URL列表
COLLEGES = [
    ("文学院", "https://chin.nju.edu.cn/szdw/xrjs/index.html", "chin.nju.edu.cn"),
    ("历史学院", "https://history.nju.edu.cn/28475/list.htm", "history.nju.edu.cn"),
    ("哲学学院", "https://philo.nju.edu.cn/4712/list.htm", "philo.nju.edu.cn"),
    ("新闻传播学院", "https://jc.nju.edu.cn/jzyg/zzjs.htm", "jc.nju.edu.cn"),
    ("法学院", "https://law.nju.edu.cn/szdw/zzjs1/js.htm", "law.nju.edu.cn"),
    ("商学院", "https://nubs.nju.edu.cn/8878/list.htm", "nubs.nju.edu.cn"),
    ("外国语学院", "https://sfs.nju.edu.cn/szdw/index.html", "sfs.nju.edu.cn"),
    ("政府管理学院", "https://public.nju.edu.cn/szdw", "public.nju.edu.cn"),
    ("国际关系学院", "https://sis.nju.edu.cn/jsrk/list.htm", "sis.nju.edu.cn"),
    ("信息管理学院", "https://im.nju.edu.cn/szll/zzjs.htm", "im.nju.edu.cn"),
    ("社会学院", "https://sociology.nju.edu.cn/szdw/list.htm", "sociology.nju.edu.cn"),
    ("数学学院", "https://math.nju.edu.cn/jzyg/index.html", "math.nju.edu.cn"),
    ("物理学院", "https://physics.nju.edu.cn/szdw/qbmd/index.html", "physics.nju.edu.cn"),
    ("天文与空间科学学院", "https://astronomy.nju.edu.cn/szll/index.html", "astronomy.nju.edu.cn"),
    ("化学化工学院", "https://chem.nju.edu.cn/szll/list.htm", "chem.nju.edu.cn"),
    ("计算机学院", "https://cs.nju.edu.cn/1651/list.htm", "cs.nju.edu.cn"),
    ("软件学院", "https://software.nju.edu.cn/szll/szdw/index.html", "software.nju.edu.cn"),
    ("人工智能学院", "https://ai.nju.edu.cn/people/list.htm", "ai.nju.edu.cn"),
    ("电子科学与工程学院", "https://ese.nju.edu.cn/22542/list.htm", "ese.nju.edu.cn"),
    ("现代工程与应用科学学院", "https://eng.nju.edu.cn/43271/list.htm", "eng.nju.edu.cn"),
    ("环境学院", "http://hjxy.nju.edu.cn/szdw/index.html", "hjxy.nju.edu.cn"),
    ("地球科学与工程学院", "https://es.nju.edu.cn/25235/list.htm", "es.nju.edu.cn"),
    ("地理与海洋科学学院", "http://sgos.nju.edu.cn/62681/list.htm", "sgos.nju.edu.cn"),
    ("大气科学学院", "http://as.nju.edu.cn/js/list.htm", "as.nju.edu.cn"),
    ("生命科学学院", "https://life.nju.edu.cn/szdw/list.htm", "life.nju.edu.cn"),
    ("医学院", "https://med.nju.edu.cn/10649/list.htm", "med.nju.edu.cn"),
    ("工程管理学院", "https://sme.nju.edu.cn/xssz/list.htm", "sme.nju.edu.cn"),
    ("匡亚明学院", "https://dii.nju.edu.cn/kyds/list.htm", "dii.nju.edu.cn"),
    ("建筑与城市规划学院", "http://arch.nju.edu.cn/szdw/index.html", "arch.nju.edu.cn"),
    ("马克思主义学院", "https://marxism.nju.edu.cn/szdw/js.htm", "marxism.nju.edu.cn"),
    ("艺术学院", "https://art.nju.edu.cn/55208/list.htm", "art.nju.edu.cn"),
    ("智能科学与技术学院", "https://is.nju.edu.cn/57159/list.htm", "is.nju.edu.cn"),
    ("智能软件与工程学院", "https://ise.nju.edu.cn/szll/zjzjs.htm", "ise.nju.edu.cn"),
    ("集成电路学院", "https://ic.nju.edu.cn/56606/list.htm", "ic.nju.edu.cn"),
    ("数字经济与管理学院", "https://sdem.nju.edu.cn/56976/list.htm", "sdem.nju.edu.cn"),
    ("能源与资源学院", "https://sser.nju.edu.cn/szll.htm", "sser.nju.edu.cn"),
    ("机器人与自动化学院", "https://ra.nju.edu.cn/szll/index.html", "ra.nju.edu.cn"),
    ("前沿科学学院", "http://frontier.nju.edu.cn/zrjs/list.htm", "frontier.nju.edu.cn"),
    ("生物医学工程学院", "https://bme.nju.edu.cn/szll/index.html", "bme.nju.edu.cn"),
    ("教育研究院·陶行知教师教育学院", "https://edu.nju.edu.cn/8746/list.htm", "edu.nju.edu.cn"),
    ("海外教育学院", "https://hwxy.nju.edu.cn/szdw/index.html", "hwxy.nju.edu.cn"),
    ("大学外语部", "https://dafls.nju.edu.cn/07/dd/c13168a460765/page.htm", "dafls.nju.edu.cn"),
    ("南京赫尔辛基大气与地球系统科学学院", "https://nh.nju.edu.cn/xyzl/szdw/nhjs.htm", "nh.nju.edu.cn"),
    ("体育部", "http://tyb.nju.edu.cn/", "tyb.nju.edu.cn"),
]


def restore_anti_crawl(text: str) -> str:
    """恢复反爬邮箱格式。"""
    for pattern, replacement in ANTI_CRAWL_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return text


def is_valid_email(email: str) -> bool:
    """验证邮箱格式并排除误提取。"""
    email = email.strip().lower()
    if not email:
        return False
    # 排除明显不是邮箱的
    if re.search(r'\.(css|js|png|jpg|jpeg|gif|svg|ico|woff2?|ttf|eot|json|xml|zip|tar|gz|exe|dll|bin|map)$', email, re.I):
        return False
    if re.search(r'(Research|Education|userAgent|text\.is)', email, re.I):
        return False
    # 标准邮箱验证
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return False
    # 检查域名长度（太短可能是误提取）
    domain = email.split('@')[1]
    if len(domain) < 6 or len(domain) > 50:
        return False
    return True


def is_public_email(email: str) -> bool:
    """检查是否为公共邮箱。"""
    prefix = email.split('@')[0].lower()
    for p in PUBLIC_EMAIL_PREFIXES:
        if prefix == p or prefix.startswith(p):
            return True
    return False


def is_valid_name(text: str) -> bool:
    """验证是否为教师姓名。"""
    text = text.strip()
    if not text:
        return False
    if any(kw in text for kw in NAV_KEYWORDS):
        return False
    if re.fullmatch(r'[一-鿿]{2,4}', text):
        return True
    if re.fullmatch(r'[一-鿿]{2,6}', text):
        return True
    return False


def extract_title(text: str) -> str:
    """从页面文本中提取职称。"""
    # 在页面前 2000 字符中搜索
    head = text[:2000]
    for line in head.split('\n'):
        line = line.strip()
        if not line:
            continue
        # 找包含姓名的行
        if re.search(r'[一-鿿]{2,4}', line):
            found = VALID_TITLE_RE.findall(line)
            if found:
                return '/'.join(found)
    return ''


def extract_emails_from_html(html_text: str) -> set[str]:
    """从HTML文本中提取所有有效邮箱，排除CSS/JS路径。"""
    text = restore_anti_crawl(html_text)

    # 先用宽松正则找所有候选
    candidates = LOOSE_EMAIL_RE.findall(text)
    valid = set()
    for c in candidates:
        email = c.strip().lower()
        if is_valid_email(email) and not is_public_email(email):
            valid.add(email)
    return valid


def extract_teacher_info(page_text: str, page_url: str) -> dict:
    """从教师详情页提取信息。"""
    # 标题（找 h1-h3 中的姓名）
    name = ''
    title = ''
    emails = extract_emails_from_html(page_text)

    return {
        'name': name,
        'title': title,
        'emails': emails,
        'url': page_url,
    }


async def crawl_college(context, college_name: str, list_url: str, domain: str) -> list[dict]:
    """爬取单个学院的所有教师邮箱。"""
    records = []
    page = await context.new_page()

    try:
        logger.info(f"  开始爬取: {college_name} ({list_url or domain})")

        if list_url:
            await page.goto(list_url, timeout=30000, wait_until='domcontentloaded')
            await asyncio.sleep(2)
        else:
            await page.goto(f'https://www.nju.edu.cn/', timeout=30000, wait_until='domcontentloaded')
            await asyncio.sleep(1)
            logger.warning(f"  {college_name} 没有预设列表页URL，尝试搜索站点")
            records = []
            await page.close()
            return records

        # 提取教师链接
        teacher_links = await page.evaluate("""() => {
            const links = [];
            const seen = new Set();
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href;
                if (!text || !href || href.startsWith('javascript:') || href === '#') return;
                // 中文姓名 2-6 字
                if (/^[\\u4e00-\\u9fff]{2,6}$/.test(text) && !seen.has(href)) {
                    seen.add(href);
                    links.push({name: text, url: href});
                }
            });
            return links;
        }""")

        # 过滤导航链接
        teacher_links = [t for t in teacher_links if is_valid_name(t['name'])]

        logger.info(f"    {college_name}: 找到 {len(teacher_links)} 个教师链接")

        # 并发访问详情页（每个教师独立 page，3个并发）
        sem = asyncio.Semaphore(3)

        async def fetch_teacher(t):
            async with sem:
                tp = await context.new_page()
                try:
                    await tp.goto(t['url'], timeout=15000, wait_until='domcontentloaded')
                    await asyncio.sleep(0.5)

                    # 检查 iframe
                    iframe_srcs = await tp.evaluate("""() => {
                        return Array.from(document.querySelectorAll('iframe')).map(f => f.src).filter(s => s);
                    }""")

                    all_text = await tp.evaluate("""() => {
                        const meta = document.querySelector('meta[name="description"]');
                        const metaContent = meta ? meta.getAttribute('content') : '';
                        return document.body.innerText + '\\n' + metaContent;
                    }""")

                    # 也获取 HTML 源码（邮箱可能嵌在 HTML 属性中）
                    html = await tp.content()

                    # 合并文本
                    combined = all_text + '\n' + html

                    # 从 meta keywords 提取
                    meta_kw = await tp.evaluate("""() => {
                        const m = document.querySelector('meta[name="keywords"]');
                        return m ? m.getAttribute('content') : '';
                    }""")
                    if meta_kw:
                        combined += '\n' + meta_kw

                    # 也从 iframe 中提取
                    for src in iframe_srcs[:2]:  # 最多检查2个iframe
                        try:
                            await tp.goto(src, timeout=10000, wait_until='domcontentloaded')
                            await asyncio.sleep(0.5)
                            iframe_text = await tp.evaluate("() => document.body.innerText")
                            combined += '\n' + iframe_text
                        except:
                            pass

                    await tp.close()

                    emails = extract_emails_from_html(combined)
                    title = extract_title(combined)

                    if emails:
                        return {
                            '姓名': t['name'],
                            '邮箱': sorted(emails)[0],
                            '学院': college_name,
                            '职称': title,
                            '主页链接': t['url'],
                        }
                    else:
                        return {
                            '姓名': t['name'],
                            '邮箱': '',
                            '学院': college_name,
                            '职称': title,
                            '主页链接': t['url'],
                        }
                except Exception as e:
                    await tp.close()
                    return {
                        '姓名': t['name'],
                        '邮箱': '',
                        '学院': college_name,
                        '职称': '',
                        '主页链接': t['url'],
                    }

        tasks = [fetch_teacher(t) for t in teacher_links]
        batch_size = 5
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            batch_results = await asyncio.gather(*batch)
            records.extend(batch_results)
            if (i + batch_size) % 10 == 0 or i + batch_size >= len(tasks):
                email_count = sum(1 for r in records if r['邮箱'])
                logger.info(f"      {college_name}: {len(records)}/{len(teacher_links)} 完成, {email_count} 个邮箱")

    except Exception as e:
        logger.error(f"  {college_name} 爬取失败: {e}")
    finally:
        await page.close()

    email_count = sum(1 for r in records if r['邮箱'])
    logger.info(f"  ✅ {college_name}: {len(records)} 人, {email_count} 个邮箱")
    return records


async def main():
    """主函数。"""
    import sys

    # 目标学院：覆盖率低于30%的
    low_coverage = [
        "商学院", "生命科学学院", "大学外语部", "体育部", "现代工程与应用科学学院",
        "生物医学工程学院", "地理与海洋科学学院", "电子科学与工程学院", "环境学院",
        "匡亚明学院", "外国语学院", "文学院", "化学化工学院", "信息管理学院",
        "计算机学院", "国际关系学院", "地球科学与工程学院", "政府管理学院",
        "社会学院", "法学院", "新闻传播学院", "医学院", "工程管理学院",
        "哲学学院", "马克思主义学院", "历史学院", "海外教育学院", "艺术学院",
    ]

    target = sys.argv[1:] if len(sys.argv) > 1 else low_coverage
    logger.info(f"目标学院: {len(target)} 个: {target}")

    from playwright.async_api import async_playwright

    all_records = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # 过滤有URL的学院
        colleges_to_crawl = [c for c in COLLEGES if c[0] in target]

        # 并发 3 个学院
        sem = asyncio.Semaphore(3)

        async def crawl_one(college_cfg):
            name, url, domain = college_cfg
            ctx = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
            )
            async with sem:
                result = await crawl_college(ctx, name, url, domain)
            await ctx.close()
            return result

        for i in range(0, len(colleges_to_crawl), 3):
            batch = colleges_to_crawl[i:i+3]
            logger.info(f"\n===== 批量爬取 {i+1}-{i+len(batch)}: {[c[0] for c in batch]} =====")
            results = await asyncio.gather(*[crawl_one(c) for c in batch])
            for r in results:
                all_records.extend(r)

            # 每批后保存进度
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            progress = {
                'timestamp': ts,
                'colleges_done': [c[0] for c in batch],
                'total_records': len(all_records),
                'total_with_email': sum(1 for r in all_records if r['邮箱']),
                'all_results': all_records,
            }
            progress_path = OUTPUT_DIR / f"nju_rescrape_progress_{ts}.json"
            with open(progress_path, 'w', encoding='utf-8') as f:
                json.dump(progress, f, ensure_ascii=False, indent=2)
            logger.info(f"进度保存到: {progress_path}")

        await browser.close()

    # 输出 CSV
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"南京大学_增量爬取_{ts}.csv"
    if all_records:
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['姓名', '邮箱', '学院', '职称', '主页链接'])
            writer.writeheader()
            writer.writerows(all_records)
        logger.info(f"\n✅ 增量爬取结果: {csv_path}")
        logger.info(f"   总记录: {len(all_records)}")
        logger.info(f"   有邮箱: {sum(1 for r in all_records if r['邮箱'])}")

        # 按学院统计
        dept_stats = {}
        for r in all_records:
            d = r['学院']
            if d not in dept_stats:
                dept_stats[d] = {'total': 0, 'email': 0}
            dept_stats[d]['total'] += 1
            if r['邮箱']:
                dept_stats[d]['email'] += 1

        print(f"\n  各学院统计:")
        for d, s in sorted(dept_stats.items()):
            print(f"    {d:<20}: {s['total']:>4}人, {s['email']:>4}个邮箱 ({100*s['email']//s['total'] if s['total'] else 0}%)")
    else:
        logger.warning("没有爬取到任何记录！")


if __name__ == '__main__':
    asyncio.run(main())
