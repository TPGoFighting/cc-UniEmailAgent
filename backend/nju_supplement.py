"""
南京大学补充爬取 - 针对漏爬和未爬全的学院
"""

import asyncio
import csv
import re
import os
from collections import Counter
from playwright.async_api import async_playwright

TASK_DIR = r"D:\Work\test\UniEmailAgent\backend\outputs\d73dcbad-a0ca-4034-9c67-d4e6c0966cbf"

PUBLIC_EMAIL_PREFIXES = ['webmaster','admin','office','info','master','root','postmaster',
    'wxyxz','xwcb','bgs','dangzheng','yuanban','dangban','renshi','jiaowu','xuegong',
    'tuanwei','yanjiusheng','gysj','gyyz','glxb']

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

def extract_emails(text):
    text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\[\s*@\s*\]\s*', '@', text)
    text = re.sub(r'\s*\(\s*@\s*\)\s*', '@', text)
    text = text.replace('#@', '@')
    return [e.lower() for e in EMAIL_RE.findall(text) if not any(e.lower().startswith(p) for p in PUBLIC_EMAIL_PREFIXES)]

# 需要补充的学院
SUPPLEMENT_DEPTS = [
    # 新闻传播学院 - info/ 链接在zzjs.htm上
    ("新闻传播学院", "https://jc.nju.edu.cn/jzyg/zzjs.htm", "info/"),
    # 数学学院 - 教师在apypl/index.html上，链接为iXXXX.html
    ("数学学院", "https://math.nju.edu.cn/jzyg/apypl/index.html", "i"),
    # 马克思主义学院 - 教授/副教授子页
    ("马克思主义学院", "https://marxism.nju.edu.cn/szdw/js.htm", "page.htm"),
    # 法学院 - 试试其他页面
    ("法学院", "https://law.nju.edu.cn/szdw/zzjs1/js.htm", None),
    # 化学学院 - 子学科页面
    ("化学学院", "https://chem.nju.edu.cn/szll/list.htm", None),
    # 生命科学学院 - 试试不同页面
    ("生命科学学院", "https://life.nju.edu.cn/szdw/list.htm", None),
    # 文学院 - 精确提取教师
    ("文学院", "https://chin.nju.edu.cn/szdw/xrjs/index.html", None),
    # 物理学院 - 教师太多假条目，精确提取
    ("物理学院", "https://physics.nju.edu.cn/szdw/qbmd/index.html", None),
]

async def extract_and_crawl(name, url):
    """针对特定页面提取教师+爬取邮箱"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(3)

            teachers = []

            # ---- 新闻传播学院: 找 info/ 链接 ----
            if "news" in name or "新闻" in name:
                links = await page.evaluate('''() => {
                    const items = [];
                    document.querySelectorAll('a[href*="info/"]').forEach(a => {
                        const text = a.textContent.trim();
                        if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text)) {
                            items.push({name: text, url: a.href});
                        }
                    });
                    return items;
                }''')
                teachers = links
                print(f"  info链接: {len(teachers)}个")

            # ---- 数学学院: 解析长文本教师链接 ----
            elif "数学" in name:
                links = await page.evaluate('''() => {
                    const items = [];
                    document.querySelectorAll('a[href*="apypl/"]').forEach(a => {
                        const text = a.textContent.trim();
                        const href = a.href;
                        if (href.includes('.html') && text.length > 0) {
                            // 提取名字（第一个2-4中文字符）
                            const match = text.match(/^[\\u4e00-\\u9fff]{2,4}/);
                            if (match) {
                                const name = match[0];
                                // 提取职称
                                let title = '';
                                const titleMatch = text.match(/(教授|副教授|助理教授|讲师|研究员|副研究员|助理研究员|工程师|高级工程师|博士后|硕导|博导)/);
                                if (titleMatch) title = titleMatch[1];
                                items.push({name, title, url: href});
                            }
                        }
                    });
                    return items;
                }''')
                teachers = links
                print(f"  数学教师: {len(teachers)}个")

            # ---- 马克思主义学院: 先看js.htm上有什么 ----
            elif "马克思" in name:
                # 尝试点击不同的tab
                links = await page.evaluate('''() => {
                    const items = [];
                    // 看看有没有教师照片列表或者卡片
                    document.querySelectorAll('a').forEach(a => {
                        const text = a.textContent.trim();
                        const href = a.href;
                        if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text) && href &&
                            !href.endsWith('js.htm') && !href.endsWith('fjs.htm') &&
                            !href.includes('xzry') && !href.includes('rxjs') &&
                            href.includes('marxism') && !href.includes('javascript')) {
                            items.push({name: text, url: href, title: ''});
                        }
                    });
                    return items;
                }''')
                teachers = links
                print(f"  马院教师: {len(teachers)}个")
                if not teachers:
                    # 再试试子页面
                    for subpage, label in [('https://marxism.nju.edu.cn/szdw/js.htm', '教授'),
                                           ('https://marxism.nju.edu.cn/szdw/fjs.htm', '副教授')]:
                        try:
                            await page.goto(subpage, wait_until='domcontentloaded', timeout=15000)
                            await asyncio.sleep(2)
                            subs = await page.evaluate(f'''() => {{
                                const items = [];
                                document.querySelectorAll('a[href*="page.htm"]').forEach(a => {{
                                    const t = a.textContent.trim();
                                    if (/^[\\u4e00-\\u9fff]{{2,4}}$/.test(t)) {{
                                        items.push({{name: t, url: a.href, title: '{label}'}});
                                    }}
                                }});
                                return items;
                            }}''')
                            teachers.extend(subs)
                            print(f"  {label}: {len(subs)}个")
                        except:
                            pass

            # ---- 法学院: 深度探索JS结构 ----
            elif "法" in name:
                # 查看页面是否使用iframe
                iframes = await page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('iframe')).map(f => f.src);
                }''')
                print(f"  iframes: {iframes}")

                # 查看是否有隐藏的教师列表
                content = await page.content()
                # 搜索email
                emails_in_page = extract_emails(content)
                print(f"  页面中的邮箱: {emails_in_page[:5]}")

                # 看看所有的li或者卡片
                cards = await page.evaluate('''() => {
                    const items = [];
                    document.querySelectorAll('li, .card, .item, .teacher, .person').forEach(el => {
                        const text = el.textContent.trim();
                        const a = el.querySelector('a');
                        if (a && /^[\\u4e00-\\u9fff]{2,4}$/.test(text.slice(0,4))) {
                            items.push({text: text.slice(0,20), href: a.href});
                        }
                    });
                    return items;
                }''')
                print(f"  卡片/列表项: {len(cards)}")
                for c in cards[:10]:
                    print(f"    {c['text']:20s} {c['href']}")

            # ---- 其他学院: 通用改进版提取 ----
            else:
                teachers = await page.evaluate('''() => {
                    const items = [];
                    const navKW = ['概况','简介','通知','新闻','公告','招生','联系','返回','首页',
                        '更多','下载','搜索','登录','党建','工会','校友','科研','学术','教学',
                        '培养','就业','课程','师资','队伍','教育','学生','国际','交流','合作',
                        '研究','机构','项目','成果','荣誉','招聘','诚聘','规章','制度','安全',
                        '活动','实践','基金','奖励','服务','系统','在线','投稿','学院','系所',
                        '重点','基地','平台','实验室','中心','大学'];
                    document.querySelectorAll('a[href*="page.htm"]').forEach(a => {
                        const t = a.textContent.trim();
                        const href = a.href;
                        if (/^[\\u4e00-\\u9fff]{2,4}$/.test(t) && !href.includes('javascript:')) {
                            for (let kw of navKW) {
                                if (t.includes(kw)) return;
                            }
                            items.push({name: t, url: href, title: ''});
                        }
                    });
                    return items;
                }''')
                print(f"  page.htm教师: {len(teachers)}个")

                if not teachers:
                    # 查找 info/ 链接
                    teachers = await page.evaluate('''() => {
                        const items = [];
                        document.querySelectorAll('a[href*="info/"]').forEach(a => {
                            const t = a.textContent.trim();
                            if (/^[\\u4e00-\\u9fff]{2,4}$/.test(t)) {
                                items.push({name: t, url: a.href, title: ''});
                            }
                        });
                        return items;
                    }''')
                    print(f"  info/教师: {len(teachers)}个")

            # 去重
            seen = set()
            unique_teachers = []
            for t in teachers:
                if t['url'] not in seen:
                    seen.add(t['url'])
                    unique_teachers.append(t)

            print(f"  => 实际{len(unique_teachers)}个教师")

            # 爬取详情页提取邮箱
            results = []
            for i, t in enumerate(unique_teachers):
                try:
                    detail = await context.new_page()
                    await detail.goto(t['url'], wait_until='domcontentloaded', timeout=15000)
                    await asyncio.sleep(0.8)
                    body = await detail.evaluate('() => document.body.innerText')
                    emails = extract_emails(body)

                    # 如果没有标题，从body提取
                    if not t.get('title'):
                        for kw in ['教授','副教授','助理教授','讲师','研究员','副研究员','工程师','博士后','博导','硕导']:
                            if kw in body[:3000]:
                                t['title'] = kw
                                break

                    results.append({
                        'name': t['name'],
                        'email': emails[0] if emails else '',
                        'dept': name,
                        'title': t.get('title', ''),
                        'url': t['url']
                    })
                    await detail.close()
                except Exception as e:
                    results.append({
                        'name': t['name'],
                        'email': '',
                        'dept': name,
                        'title': t.get('title', ''),
                        'url': t['url']
                    })
                    continue

                if (i+1) % 20 == 0:
                    print(f"   进度: {i+1}/{len(unique_teachers)}")

            await page.close()
            await browser.close()
            return results

        except Exception as e:
            print(f"  爬取失败: {e}")
            await page.close()
            await browser.close()
            return []


async def main():
    print("=" * 60)
    print("南京大学补充爬取")
    print("=" * 60)

    all_results = []

    for name, url, _ in SUPPLEMENT_DEPTS:
        print(f"\n[{name}]")
        results = await extract_and_crawl(name, url)
        all_results.extend(results)
        print(f"  => 获得{len(results)}条，邮箱{len([r for r in results if r['email']])}个")

    # 读取已有CSV
    csv_files = [f for f in os.listdir(TASK_DIR) if f.endswith('.csv')]
    existing_data = []
    if csv_files:
        with open(os.path.join(TASK_DIR, csv_files[0]), encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            existing_data = list(reader)
        print(f"\n已有数据: {len(existing_data)}条")

    # 合并：补充数据覆盖已有数据（按URL去重）
    url_map = {}
    for r in existing_data:
        url_map[r['主页链接']] = {
            'name': r['姓名'], 'email': r['邮箱'], 'dept': r['学院'],
            'title': r['职称'], 'url': r['主页链接']
        }

    # 补充数据覆盖
    for r in all_results:
        url_map[r['url']] = r

    merged = list(url_map.values())

    # 过滤掉导航条目
    NAV_NAMES = ['概况','简介','通知','新闻','公告','招生','培养','就业','学位',
        '学科','科研','学术','党建','工会','校友','捐赠','图书馆','校园',
        '地图','网站','登录','联系我们','欢迎','首页','返回','更多','详情',
        '查看','下载','教学','学生','国际','诚聘','相关','办事','安全','规章',
        '学习','加入','在线','投稿','系统','实践','创新创业','师德','活动',
        '基金','班级','奖励','奖学金','资助','课程','教室','继续','教育',
        '培训','天地','记录','记忆','奖助','奖学','服务','科技','组织',
        '纪检','巡察','申报','评估','督导','专栏','百年','院庆','系庆',
        '重点','技术','平台','基地','合作','交流','成果','荣誉','项目',
        '机构','方向','方案','指南','经费','财务','资产','文档','下载',
        '公开','人事','动态','招聘','登录','教职员工','教师队伍','行政教辅',
        '退休人员','用户登录','加入收藏','学院概况','学院简介','师资队伍',
        '在职教师','兼职教师','荣休教师','访问学者','教育教学','科学研究',
        '党团建设','学生工作','招生信息','人才培养','学术研究','国际交流',
        '诚聘英才','规章制度','院长致辞','现任领导','机构设置','学院标识',
        '学术成果','科研项目','学术交流','合作交流','学生活动','相关下载',
        '党团动态','师德师风','教工之家','新闻动态','活动预告','招生资讯',
        '教务通知','本院概况','组织机构','学科方向','导师','硕士生','博士生',
        '本科生','研究生','博士后','校友天地','校友名录','校友风采','校友活动',
        '发展工作','终身教育','培训动态','培训项目','培训风采','法科百年',
        '庆典活动','学术科创','社会实践','公益服务','就业工作','国际化',
        '学术会议','海外学习','国际会议','合作项目','中德所',
        '南大主站','学校主页','首页信息','加入收藏','用户登录','内网入口',
        '院系领导','专业设置','文艺学','语言学','行政管理','暑期班','培训班',
        '海外班','退休教师']

    cleaned = [r for r in merged if r['name'] not in NAV_NAMES and not any(kw == r['name'] for kw in NAV_NAMES)]

    print(f"清洗后: {len(cleaned)}条（移除{len(merged)-len(cleaned)}条导航条目）")
    print(f"有邮箱: {len([r for r in cleaned if r['email']])}")

    # 写入CSV
    csv_path = os.path.join(TASK_DIR, "南京大学_全校教师邮箱_V1.0.0.csv")
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['序号', '姓名', '邮箱', '学院', '职称', '主页链接'])
        for i, r in enumerate(cleaned, 1):
            writer.writerow([i, r['name'], r['email'], r['dept'], r['title'], r['url']])

    print(f"\n输出: {csv_path}")

    # 按学院统计
    dept_count = Counter(r['dept'] for r in cleaned)
    print("\n各学院教师数:")
    for dept, count in sorted(dept_count.items(), key=lambda x: -x[1]):
        email_c = len([r for r in cleaned if r['dept'] == dept and r['email']])
        print(f"  {dept}: {count}人 (邮箱: {email_c})")


if __name__ == '__main__':
    asyncio.run(main())
