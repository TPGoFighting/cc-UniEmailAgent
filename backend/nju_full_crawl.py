"""
南京大学全校各院系教师邮箱爬取脚本 v2 - 优化版
- Phase 1: 快速收集所有学院的教师条目（姓名+详情URL）
- Phase 2: 并行访问所有教师详情页提取邮箱（并发15个）
"""

import asyncio
import csv
import re
import os
from datetime import datetime
from collections import Counter
from playwright.async_api import async_playwright

TASK_DIR = r"D:\Work\test\UniEmailAgent\backend\outputs\d73dcbad-a0ca-4034-9c67-d4e6c0966cbf"

PUBLIC_EMAIL_PREFIXES = ['webmaster','admin','office','info','master','root','postmaster',
    'wxyxz','xwcb','bgs','dangzheng','yuanban','dangban','renshi','jiaowu','xuegong',
    'tuanwei','yanjiusheng','gysj','gyyz','glxb']

NAV_KW = ['概况','简介','新闻','通知','公告','招生','培养','就业','学位','学科','科研',
    '学术','党建','工会','校友','捐赠','图书馆','校园','地图','网站','登录','联系我们',
    '欢迎','首页','返回','更多','详情','查看','下载','教师名录','copyright','版权所有',
    '教学','学生','国际','诚聘','相关','办事','安全','规章','学习','加入','在线','投稿',
    '系统','实践','创新创业','师德','活动','基金','班级','奖励','奖学金','资助','课程',
    '教室','继续','教育','培训','天地','记录','记忆','奖助','奖学','服务','科技','组织',
    '纪检','巡察','申报','评估','督导','专栏','百年','院庆','系庆','重点','技术','平台',
    '基地','合作','交流','成果','荣誉','项目','机构','学科','方向','培养','方案','指南',
    '经费','财务','资产','安全','文档','下载','公开','人事','动态','招聘','登录']

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
NAME_RE = re.compile(r'^[一-鿿]{2,4}$')
TITLE_KW = ['教授','副教授','助理教授','讲师','研究员','副研究员','助理研究员',
            '工程师','高级工程师','博士后','博导','硕导','院士','长江学者','杰青',
            '优青','高级实验师','实验师','实验师','主任','副主任','院长','副院长']

def is_public_email(email):
    prefix = email.split('@')[0].lower()
    return any(prefix.startswith(p) for p in PUBLIC_EMAIL_PREFIXES)

def extract_emails(text):
    """反爬恢复后提取邮箱"""
    text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\[\s*@\s*\]\s*', '@', text)
    text = re.sub(r'\s*\(\s*@\s*\)\s*', '@', text)
    text = text.replace('#@', '@')
    emails = EMAIL_RE.findall(text)
    return [e.lower() for e in emails if not is_public_email(e)]

def extract_title(text):
    m = re.search(r'[（(]([^）)]+)[）)]', text)
    if m:
        txt = m.group(1)
        for kw in TITLE_KW:
            if kw in txt:
                return kw
        return txt  # 返回原始括号内容作为职称
    return ''

def extract_clean_name(text):
    name = text.strip()
    name = re.sub(r'[（(].*?[）)]', '', name).strip()
    name = name.replace(' ', '')
    return name

# ============ 所有学院师资列表页 ============
DEPT_LIST = [
    ("文学院", "https://chin.nju.edu.cn/szdw/xrjs/index.html"),
    ("历史学院", "https://history.nju.edu.cn/28475/list.htm"),
    ("哲学学院", "https://philo.nju.edu.cn/4712/list.htm"),
    ("新闻传播学院", "https://jc.nju.edu.cn/jzyg/zzjs.htm"),
    ("法学院", "https://law.nju.edu.cn/szdw/zzjs1/js.htm"),
    ("外国语学院", "https://sfs.nju.edu.cn/szdw/index.html"),
    ("政府管理学院", "https://public.nju.edu.cn/szdw/qzjs/index.html"),
    ("国际关系学院", "https://sis.nju.edu.cn/jsrk/list.htm"),
    ("信息管理学院", "https://im.nju.edu.cn/szll/zzjs.htm"),
    ("社会学院", "https://sociology.nju.edu.cn/qzjs/list.htm"),
    ("马克思主义学院", "https://marxism.nju.edu.cn/szdw/js.htm"),
    ("数学学院", "https://math.nju.edu.cn/jzyg/apypl/index.html"),
    ("物理学院", "https://physics.nju.edu.cn/szdw/qbmd/index.html"),
    ("天文与空间科学学院", "https://astronomy.nju.edu.cn/szll/szgk/index.html"),
    ("化学学院", "https://chem.nju.edu.cn/szll/list.htm"),
    ("计算机学院", "https://cs.nju.edu.cn/2639/list.htm"),
    ("计算机学院(副教授)", "https://cs.nju.edu.cn/2640/list.htm"),
    ("计算机学院(准长聘)", "https://cs.nju.edu.cn/zzp/list.htm"),
    ("计算机学院(跨学科博导)", "https://cs.nju.edu.cn/kxkbd/list.htm"),
    ("计算机学院(高工)", "https://cs.nju.edu.cn/2642/list.htm"),
    ("计算机学院(技术人员)", "https://cs.nju.edu.cn/2643/list.htm"),
    ("软件学院", "https://software.nju.edu.cn/szll/szdw/index.html"),
    ("人工智能学院", "https://ai.nju.edu.cn/people/list.htm"),
    ("电子科学与工程学院", "https://ese.nju.edu.cn/kxkbsszdjs/list.htm"),
    ("现代工程与应用科学学院", "https://eng.nju.edu.cn/43271/list.htm"),
    ("环境学院", "https://hjxy.nju.edu.cn/szdw/index.html"),
    ("地球科学与工程学院", "https://es.nju.edu.cn/25235/list.htm"),
    ("地理与海洋科学学院", "https://sgos.nju.edu.cn/62681/list.htm"),
    ("大气科学学院", "https://as.nju.edu.cn/js/list.htm"),
    ("南京赫尔辛基大气学院", "https://nh.nju.edu.cn/xyzl/szdw/nhjs.htm"),
    ("生命科学学院", "https://life.nju.edu.cn/szdw/list.htm"),
    ("医学院", "https://med.nju.edu.cn/10649/list.htm"),
    ("工程管理学院", "https://sme.nju.edu.cn/rxjs/list.htm"),
    ("匡亚明学院", "https://dii.nju.edu.cn/lsjs/list.htm"),
    ("建筑与城市规划学院", "https://arch.nju.edu.cn/szdw/index.html"),
    ("艺术学院", "https://art.nju.edu.cn/55208/list.htm"),
    ("智能科学与技术学院", "https://is.nju.edu.cn/57159/list.htm"),
    ("智能软件与工程学院", "https://ise.nju.edu.cn/szll/zjzjs.htm"),
    ("集成电路学院", "https://ic.nju.edu.cn/zzjs/list.htm"),
    ("数字经济与管理学院", "https://sdem.nju.edu.cn/56976/list.htm"),
    ("能源与资源学院", "https://sser.nju.edu.cn/szll.htm"),
    ("机器人与自动化学院", "https://ra.nju.edu.cn/szll/zzjs/index.html"),
    ("前沿科学学院", "https://frontier.nju.edu.cn/zrjs/list.htm"),
    ("生物医学工程学院", "https://bme.nju.edu.cn/szll/zzjs/index.html"),
    ("教育研究院", "https://edu.nju.edu.cn/8746/list.htm"),
    ("海外教育学院", "https://hwxy.nju.edu.cn/szdw/zc/yyjs/index.html"),
    ("体育部", "https://tyb.nju.edu.cn/jbgk/szdw/index.html"),
    ("人文社会科学高级研究院", "https://ias.nju.edu.cn/13109/list.htm"),
    ("现代生物研究院", "https://imb.nju.edu.cn/"),
    ("地球系统科学研究所", "https://essi.nju.edu.cn/main.htm"),
    ("社会学院(心理学系)", "https://sociology.nju.edu.cn/xlxx/list.htm"),
    ("政府管理学院(兼职)", "https://public.nju.edu.cn/szdw/jzjs/jzjs/index.html"),
    ("医学院(院士)", "https://med.nju.edu.cn/10871/list.htm"),
]

async def extract_teachers_from_listing(page, dept_name, list_url):
    """从列表页提取教师条目（姓名+详情URL+职称），不进入详情页"""
    teachers = []
    await page.goto(list_url, wait_until='domcontentloaded', timeout=30000)
    await asyncio.sleep(2.5)

    # 策略1: page.htm 链接
    page_links = await page.evaluate('''() => {
        const items = [];
        const navKW = ["概况","简介","历史","沿革","通知","新闻","公告","科研","学术",
            "党建","工会","校友","捐赠","联系","成果","基地","培养","招生","就业",
            "学位","本科","研究","机构","项目","合作","交流","人才","招聘","规章",
            "制度","委员","领导","联系","在线","投稿","系统","登录","教师登录",
            "师德","奖励","基金","课程","教室","实践","国际","诚聘","相关","办事",
            "安全","下载","活动","荣誉","加入","返回","更多","参观","培训","继续",
            "教育","学生","天地","记录","记忆","奖助","奖学","服务","科技","组织",
            "纪检","巡察","申报","评估","督导","专栏","百年","院庆","系庆","重点",
            "技术","平台","基地","合作","交流","成果","荣誉","项目","机构","学科",
            "方向","培养","方案","指南","经费","财务","资产","文档","公开","人事",
            "动态","招聘","登录","师德","监督","信箱","团建","党群","工会","委员会",
            "财务","资产","安全","文档","下载"];
        document.querySelectorAll('a[href*="page.htm"]').forEach(a => {
            const text = a.textContent.trim();
            const href = a.href;
            if (text.length > 0 && text.length < 45 && !href.includes('javascript:')) {
                for (let kw of navKW) {
                    if (text.includes(kw)) return;
                }
                items.push({text, href});
            }
        });
        return items;
    }''')

    for link in page_links:
        name = extract_clean_name(link['text'])
        if NAME_RE.match(name):
            teachers.append({
                'name': name,
                'title': extract_title(link['text']),
                'url': link['href'],
                'dept': dept_name
            })

    # 如果 page.htm 策略找到的太少或没有，尝试策略2: 检查是否是列表页（教育研究院等会用 list.htm）
    if not teachers:
        # 检查页面主体区域的所有链接
        all_links = await page.evaluate('''() => {
            // 找到主要内容区域
            const mainContent = document.querySelector('main, .content, .article, #content, .wp_content, .list, .teacher_list, .sub_content, .right, .right-content, .col_right, #right, .container') || document.body;
            const items = [];
            const navKW = ["概况","简介","历史","通知","新闻","公告","招生","培养","就业",
                "学位","学科","科研","学术","党建","工会","校友","联系","首页","返回",
                "更多","详情","查看","下载","教学","学生","国际","诚聘","相关","办事",
                "安全","规章","制度","学习","加入","系统","活动","基金","奖励","课程",
                "师资","教师","教育","服务","组织"];
            mainContent.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href;
                if (text.length > 0 && text.length < 40 && href && !href.startsWith('javascript:') && href !== document.location.href) {
                    // 过滤导航
                    for (let kw of navKW) {
                        if (text.includes(kw)) return;
                    }
                    // 必须是中文名模式
                    items.push({text, href});
                }
            });
            return items;
        }''')

        for link in all_links:
            name = extract_clean_name(link['text'])
            if NAME_RE.match(name):
                teachers.append({
                    'name': name,
                    'title': extract_title(link['text']),
                    'url': link['href'],
                    'dept': dept_name
                })

    # 去重
    seen = set()
    unique = []
    for t in teachers:
        if t['url'] not in seen and not t['url'].endswith(list_url.rstrip('/')) and not t['url'].endswith(list_url.rstrip('/') + '/main.htm'):
            seen.add(t['url'])
            unique.append(t)

    return unique


async def crawl_teacher_detail(sem, browser, teacher):
    """爬取单个教师详情页提取邮箱"""
    async with sem:
        page = await browser.new_page()
        try:
            await page.goto(teacher['url'], wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(0.8)

            body_text = await page.evaluate('() => document.body.innerText')
            emails = extract_emails(body_text)

            # 检查meta description
            meta_desc = await page.evaluate('''() => {
                const m = document.querySelector('meta[name="description"]');
                return m ? m.content : '';
            }''')
            if meta_desc:
                emails.extend(extract_emails(meta_desc))

            emails = list(set(emails))
            email = emails[0] if emails else ''

            # 提取职称（如果还没有）
            if not teacher['title']:
                for kw in TITLE_KW:
                    if kw in body_text[:3000]:
                        teacher['title'] = kw
                        break

            await page.close()
            return {**teacher, 'email': email}

        except Exception as e:
            await page.close()
            return {**teacher, 'email': ''}


async def main():
    print("=" * 60)
    print("南京大学全校教师邮箱爬取 v2")
    print(f"目标学院数: {len(DEPT_LIST)}")
    print("=" * 60)

    all_teachers = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
        )

        # === Phase 1: 快速收集所有教师条目 ===
        print("\n--- Phase 1: 收集教师条目 ---")
        for i, (dept_name, list_url) in enumerate(DEPT_LIST, 1):
            try:
                page = await context.new_page()
                teachers = await extract_teachers_from_listing(page, dept_name, list_url)
                await page.close()
                all_teachers.extend(teachers)
                print(f"[{i}/{len(DEPT_LIST)}] {dept_name}: {len(teachers)} 位教师")
            except Exception as e:
                print(f"[{i}/{len(DEPT_LIST)}] {dept_name}: 失败 - {e}")
                continue

        # 按URL去重（合并计算机学院等有重复URL的情况）
        seen_urls = set()
        deduped_teachers = []
        for t in all_teachers:
            if t['url'] not in seen_urls:
                seen_urls.add(t['url'])
                deduped_teachers.append(t)

        all_teachers = deduped_teachers
        print(f"\nPhase 1 完成! 总计 {len(all_teachers)} 位教师（已去重）")

        # === Phase 2: 并行访问详情页提取邮箱 ===
        print("\n--- Phase 2: 提取邮箱 ---")
        sem = asyncio.Semaphore(10)  # 并发10个详情页
        tasks = [crawl_teacher_detail(sem, browser, t) for t in all_teachers]

        results = []
        completed = 0
        total = len(tasks)

        # 分批处理，显示进度
        batch_size = 20
        for batch_start in range(0, total, batch_size):
            batch = tasks[batch_start:batch_start + batch_size]
            batch_results = await asyncio.gather(*batch)
            results.extend(batch_results)
            completed += len(batch)
            email_count = len([r for r in results if r['email']])
            print(f"进度: {completed}/{total} | 已获邮箱: {email_count}")

        await browser.close()

    # 最终去重
    seen_emails = set()
    seen_urls_final = set()
    final = []
    for r in results:
        if r['email']:
            if r['email'] not in seen_emails:
                seen_emails.add(r['email'])
                # 统一学院名：将"计算机学院(副教授)"等合并为"计算机学院"
                dept = re.sub(r'\(.*?\)', '', r['dept']).strip()
                final.append({**r, 'dept': dept})
        else:
            if r['url'] not in seen_urls_final:
                seen_urls_final.add(r['url'])
                dept = re.sub(r'\(.*?\)', '', r['dept']).strip()
                final.append({**r, 'dept': dept})

    # 写入CSV
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(TASK_DIR, f"南京大学_全校教师邮箱_V1.0.0.csv")

    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['序号', '姓名', '邮箱', '学院', '职称', '主页链接'])
        for i, r in enumerate(final, 1):
            writer.writerow([i, r['name'], r['email'], r['dept'], r['title'], r['url']])

    print(f"\n{'='*60}")
    print(f"🎉 爬取完成!")
    print(f"总计教师: {len(final)} 人")
    print(f"有邮箱:   {len([r for r in final if r['email']])} 人")
    print(f"无邮箱:   {len([r for r in final if not r['email']])} 人")
    print(f"输出文件: {csv_path}")
    print(f"{'='*60}")

    # 按学院统计
    dept_count = Counter(r['dept'] for r in final)
    print("\n各学院教师数:")
    for dept, count in sorted(dept_count.items(), key=lambda x: -x[1]):
        email_c = len([r for r in final if r['dept'] == dept and r['email']])
        print(f"  {dept}: {count}人 (邮箱: {email_c})")


if __name__ == '__main__':
    asyncio.run(main())
