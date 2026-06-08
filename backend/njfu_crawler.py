"""
南京林业大学 (Nanjing Forestry University) 教师邮箱爬虫
并行爬取所有学院的教师列表页 -> 进入详情页提取邮箱
"""
import asyncio
import re
import csv
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

# 邮箱正则
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# 导航关键词黑名单
NAV_WORDS = {
    '首页','学院概况','师资队伍','人才培养','科学研究','党建工作','学院简介',
    '现任领导','组织机构','通知公告','规章制度','学术组织','科研成果','科研平台',
    '推广应用','国际合作','社会服务','学院新闻','工作动态','群团工作','校友天地',
    '实验室管理','党政管理','旧版','设为首页','本科生培养','研究生培养','国际教育',
    '团委','工会','就业','招生','学院首页','学校主页','学院大厅','教师登录',
    '管理登录','用户登陆','网站首页','学院历史','学院现状','学院领导','学院机构',
    '下载中心','学术动态','科研论著','全职教师','师资力量','荣退教师','师资简介',
    '师资名录','学术科研','机构设置','学术交流','实验教学','党群工作','学院介绍',
    '历任领导','留学生','博士后','兼职教授','讲师','本科','硕士','博士','研究生',
    '学科平台','委员会','学科带头人','查看更多','查看详情','院长','书记','学生工作',
    '校友','招生','就业','党建','群团','学科建设','学生活动','教师风采','学工队伍',
    '科研项目','科研团队','科研获奖','科研机构','教授观点','学术活动','案例中心',
    '党群建设','党建学习','支部风采','学院办公室','教学管理中心','最新成果','历史沿革',
    '院士','特聘教授','产业教授','荣休教师','两办人员','系部设置','博士生导师',
    '硕士生导师','行政人员','在研项目','研究所','实验室建设','交流合作','社会团体',
    '学院制度','学科概况','优势学科','成果奖励','科研论文','基金申报','网上党校',
    '博士生培养','招生信息','交通运输系','交通工程系','车辆工程系','教育培养','本科培养',
    '研究生教育','获奖情况','本科教育','专业介绍','培养方案','专业认证','教学成果',
    '选课指南','教学动态','党委工作','工会工作','校友之家','实验中心','交流合作',
    '马院简介','教学机构','教辅机构','师资概况','教师介绍','学科简介','导师简况',
    '植物科学系','动物学系','微生物学系','获奖情况','校友天地','体育中心','通知下载',
    '联系我们','体育部概况','校体委会','裁判队伍','健康服务','课外体育','系科部门',
    '个人简历','研究方向','科研项目','论文发表','教学工作','中心简介','中心动态',
    '实验条件','虚仿项目','学科竞赛','一流课程','仪器设备','学工动态','服务指南',
    '学院党委','党员管理','统战工作','学院工会','校友活动','学院介绍','历任领导',
    '教授','副教授','工程师','高级实验师','实验师','学科带头人','博士生导师',
    '硕士生导师','查看详情','更多','欢迎','新闻','通知','公告','English',
    '学科方向','研究团队','科研课题','学术兼职','代表成果','社会服务','发明专利',
    '教材著作','软件著作权','成果转化','招生就业','考研就业','学生天地','团学工作',
    '支部建设','关工委','继续教育','专业设置','精品课程','实验示范中心','虚拟仿真',
    '中外合作','留学生教育','人才引进','博士后流动站','教授委员会','学术委员会',
    '学位委员会','教学委员会','院务公开','信息公开','书记信箱','院长信箱','师德师风',
    '教师入口','学生入口','办公系统','教务系统','科研系统','资产系统','财务系统',
    '人事系统','学科竞赛','科技竞赛','创新创业','学生组织','学生社团','心理教育',
    '资助工作','评奖评优','国防教育','宿舍管理','队伍建设','理论园地',
    '组织机构','党建工作','离退休','教工','系别','专任教师','在职教师',
    '按职称','按系别','教师登陆','BS管理器','学科建设',
}

# 姓名黑名单（常被误判为教师名的导航词）
FAKE_NAMES = {
    '愿景使命','农林经济系','工商管理系','应用经济学系','会计学系',
    '教学科研','文件下载','校友园地','系部设置','科研课题','学科方向',
    '代表成果','发明专利','教材著作','软件著作权','成果转化',
    '教学成果','选课指南','教学动态','党委工作','工会工作','校友之家',
    '实验中心','交流合作','学生工作','校友工作','就业工作','人才招聘',
    '校企合作','基地建设','实践教学','实验教学','专业实践','联合培养',
    '专家人才','两办','党政','团委','学工','教务','科研','研究生',
    '博士后','留学生','本科生','研究生','博士生','硕士生','学科建设',
    '科研平台','重点实验室','工程中心','研究中心','研究所','研究院',
    '院士风采','杰出人才','学术团队','创新团队','青年人才','学术报告',
    '学术会议','学术讲座','学术论坛','学术沙龙','国际会议','学术交流',
    '合作交流','校企合作','国际合作','社会服务','技术转移','科技服务',
    '科技开发','科技推广','成果展示','荣誉成果','教师获奖','学生获奖',
    '国际交流','出国出境','来访访问','外专外教','港澳台','留学项目',
    '留学指南','留学申请','海外学习','海外实习','国际班','合作项目',
    '招生简章','招生计划','招生政策','招生专业','招生宣传','就业信息',
    '就业指导','就业政策','就业统计','就业质量','就业报告','毕业生',
    '校友会','校友名录','校友风采','校友捐赠','校友服务','校友动态',
    '教师登录','管理登录','用户登陆','网站首页','学校主页','学院大厅',
    'BS管理器','旧版回顾','设为首页','加入收藏','返回首页','English',
    '教师下载','教学下载','科研下载','行政下载','表格下载','文件下载',
    '两办主任','党务秘书','教学秘书','科研秘书','研究生秘书','行政秘书',
    '辅导员','班主任','实验员','资料员','教务员','办事员','科员',
    '学院办公室','教学管理中心','研究生管理','科研管理','行政管理',
    '学生管理','后勤管理','设备管理','实验室管理','安全管理','网络管理',
}


# 学院定义: (学院名, 列表页URL列表)
# 每个学院可以有多个列表页（如按职称、按系别分页）
COLLEGES = [
    # 1. 林草学院、水土保持学院
    ('林草学院', [
        ('院士', 'http://linxue.njfu.edu.cn/szdw/ys2/index.html'),
        ('森林保护系', 'http://linxue.njfu.edu.cn/szdw/slbhx/index.html'),
        ('水土保持系', 'http://linxue.njfu.edu.cn/szdw/stbcx/index.html'),
    ]),

    # 2. 材料科学与工程学院
    ('材料学院', [
        ('全职教师', 'https://wood.njfu.edu.cn/szdw/qzjs/index.html'),
    ]),

    # 3. 化学工程学院
    ('化工学院', [
        ('教授', 'http://hg.njfu.edu.cn/szdw/js/index.html'),
        ('副教授', 'http://hg.njfu.edu.cn/szdw/fjs/index.html'),
        ('院士', 'http://hg.njfu.edu.cn/szdw/ys/index.html'),
        ('特聘教授', 'http://hg.njfu.edu.cn/szdw/tpjs/index.html'),
        ('产业教授', 'http://hg.njfu.edu.cn/szdw/cyjs/index.html'),
    ]),

    # 4. 机械电子工程学院
    ('机电学院', [
        ('师资队伍', 'http://jidian.njfu.edu.cn/szdw/index.html'),
    ]),

    # 5. 土木工程学院
    ('土木学院', [
        ('全职教师', 'https://tumu.njfu.edu.cn/1945/list.htm'),
    ]),

    # 6. 经济管理学院
    ('经管学院', [
        ('全职教师', 'https://cem.njfu.edu.cn/qzjs/list.htm'),
        ('农林经济系', 'https://cem.njfu.edu.cn/4741/list.htm'),
        ('工商管理系', 'https://cem.njfu.edu.cn/4742/list.htm'),
        ('应用经济学系', 'https://cem.njfu.edu.cn/4744/list.htm'),
        ('会计学系', 'https://cem.njfu.edu.cn/4745/list.htm'),
    ]),

    # 7. 人文社会科学学院、生态文明传播学院
    ('人文学院', [
        ('全职教师', 'http://renwen.njfu.edu.cn/szdwn/qzjs/index.html'),
    ]),

    # 8. 信息科学技术学院、人工智能学院
    ('信息学院', [
        ('教授/研究员', 'http://it.njfu.edu.cn/szll/js/index.html'),
        ('副教授', 'http://it.njfu.edu.cn/szll/fjs/index.html'),
        ('学科带头人', 'http://it.njfu.edu.cn/szll/xkdtr/index.html'),
        ('兼职教授', 'http://it.njfu.edu.cn/szll/jzjs/index.html'),
        ('讲师', 'http://it.njfu.edu.cn/szll/js2594/index.html'),
    ]),

    # 9. 风景园林学院
    ('风景园林学院', [
        ('专业教师', 'https://yuanlin.njfu.edu.cn/rw/szll/ylghsjx/'),
    ]),

    # 10. 理学院
    ('理学院', [
        ('师资队伍', 'https://cos.njfu.edu.cn/75/list.htm'),
    ]),

    # 11. 外国语学院
    ('外国语学院', [
        ('师资名录', 'http://waiyuan.njfu.edu.cn/szdw/szml/index.html'),
    ]),

    # 12. 艺术设计学院
    ('艺术设计学院', [
        ('教师风采', 'http://art.njfu.edu.cn/szdw/jsfc/index.html'),
    ]),

    # 13. 家居与工业设计学院
    ('家居学院', [
        ('教授', 'http://jiaju.njfu.edu.cn/xjdw/js6680/index.html'),
        ('副教授', 'http://jiaju.njfu.edu.cn/xjdw/fjs6196/index.html'),
    ]),

    # 14. 轻工与食品学院
    ('轻工食品学院', [
        ('博士生导师', 'http://qg.njfu.edu.cn/szdw/bssds/index.html'),
        ('硕士生导师', 'http://qg.njfu.edu.cn/szdw/sssds/index.html'),
    ]),

    # 15. 汽车与交通工程学院
    ('汽车交通学院', [
        ('交通运输系', 'http://jty.njfu.edu.cn/jgsz/jtysx/index.html'),
        ('交通工程系', 'http://jty.njfu.edu.cn/jgsz/jtgcx/index.html'),
        ('车辆工程系', 'http://jty.njfu.edu.cn/jgsz/clgcx/index.html'),
    ]),

    # 16. 生态与环境学院
    ('生态与环境学院', [
        ('在职教师', 'https://cee.njfu.edu.cn/szdw/zzjs/index.html'),
    ]),

    # 17. 马克思主义学院
    ('马克思主义学院', [
        ('教师介绍', 'http://my.njfu.edu.cn/szdw/jsjs/index.html'),
    ]),

    # 18. 生命科学学院
    ('生命科学学院', [
        ('植物科学系', 'https://sky.njfu.edu.cn/szdw/js/index.html'),
        ('动物学系', 'https://sky.njfu.edu.cn/szdw/jsjqt/index.html'),
        ('微生物学系', 'https://sky.njfu.edu.cn/szdw/sysglry/index.html'),
    ]),

    # 19. 体育美育部
    ('体育部', [
        ('师资队伍', 'http://tyb.njfu.edu.cn/szdw/index.html'),
    ]),
]


async def extract_teachers(page, list_url, college_name, sub_name):
    """从教师列表页提取教师姓名+详情页URL"""
    try:
        await page.goto(list_url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        # 获取页面上所有链接
        links = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim().replace(/\\s+/g, ' ');
                const href = a.href || '';
                const parent = a.parentElement;
                if (text && href && !href.startsWith('javascript') && !href.startsWith('#')) {
                    results.push({
                        text: text,
                        href: href,
                        parentTag: parent ? parent.tagName.toLowerCase() : '',
                        parentCls: parent ? (parent.className || '') : '',
                    });
                }
            });
            return results;
        }""")

        # 过滤出教师姓名
        teachers = []
        seen_urls = set()

        for l in links:
            t = l['text'].strip()
            h = l['href']

            # 基本过滤
            if len(t) < 2 or len(t) > 5:
                continue
            cn_count = sum(1 for c in t if '一' <= c <= '鿿')
            if cn_count < 2:
                continue
            if t in NAV_WORDS or t in FAKE_NAMES:
                continue
            # 排除包含特殊字符的
            if re.search(r'[#@￥%&*()（）《》【】\[\]]', t):
                continue
            # 排除纯数字或字母
            if re.match(r'^[\dA-Za-z\s]+$', t):
                continue

            # 排除分页链接
            if t in ['下一页', '上一页', '首页', '末页', '>>', '<<', '>', '<']:
                continue

            # 排除已知的导航链接
            if any(kw in t for kw in ['登录', '注册', '联系', '帮助', '反馈', '系统', '设置']):
                continue

            # 排除过长的条目
            if len(t) > 6:
                continue

            # 去重（同URL只取第一次出现的）
            if h in seen_urls:
                continue
            seen_urls.add(h)

            teachers.append({
                'name': t,
                'url': h,
                'college': college_name,
                'sub_category': sub_name
            })

        return teachers
    except Exception as e:
        print(f'  ⚠️ {college_name}/{sub_name} 列表页加载失败: {e}')
        return []


async def extract_email(page, teacher):
    """进入教师详情页提取邮箱"""
    try:
        await page.goto(teacher['url'], wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(1)

        text = await page.evaluate('() => document.body.innerText')

        # 反爬恢复
        text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
        text = text.replace('#@', '@')
        text = text.replace('[@]', '@')
        text = text.replace('(@)', '@')

        # 提取邮箱
        emails = EMAIL_RE.findall(text)

        # 过滤公共邮箱
        public_prefixes = ['webmaster', 'admin', 'office', 'info', 'master', 'root', 'postmaster',
                          'wxyxz', 'xwcb', 'bgs', 'dangzheng', 'yuanban', 'dangban', 'renshi',
                          'jiaowu', 'xuegong', 'tuanwei', 'yanjiusheng', 'gysj', 'gyyz', 'glxb',
                          'xinxixy', 'bsmanager', 'webplus']

        personal_emails = []
        for e in emails:
            prefix = e.split('@')[0].lower()
            if not any(prefix == p or prefix.startswith(p + '.') or prefix.startswith(p + '_') for p in public_prefixes):
                personal_emails.append(e.lower())

        # 去重
        personal_emails = list(set(personal_emails))

        if personal_emails:
            teacher['email'] = personal_emails[0]
        else:
            teacher['email'] = ''

        # 从详情页提取职称
        title_match = re.search(r'职称[：:]\s*([^\n]{1,20})', text)
        if title_match:
            teacher['title'] = title_match.group(1).strip()
        else:
            teacher['title'] = ''

    except Exception as e:
        teacher['email'] = ''
        teacher['title'] = ''

    return teacher


async def crawl_college(context, college_name, sub_pages, semaphore):
    """爬取一个学院的所有教师"""
    all_teachers = []
    seen_teachers = set()  # 用于去重

    for sub_name, list_url in sub_pages:
        async with semaphore:
            page = await context.new_page()
            try:
                teachers = await extract_teachers(page, list_url, college_name, sub_name)

                if not teachers:
                    print(f'  {college_name}/{sub_name}: 未找到教师')
                    await page.close()
                    continue

                print(f'  {college_name}/{sub_name}: 找到 {len(teachers)} 位教师')

                # 去重
                new_teachers = []
                for t in teachers:
                    # 用姓名+URL作为去重key
                    key = f"{t['name']}|{t['url']}"
                    if key not in seen_teachers:
                        seen_teachers.add(key)
                        new_teachers.append(t)

                all_teachers.extend(new_teachers)

            except Exception as e:
                print(f'  ⚠️ {college_name}/{sub_name} 处理失败: {e}')
            finally:
                await page.close()

    return all_teachers


async def main():
    output_dir = sys.argv[1] if len(sys.argv) > 1 else 'outputs/test'
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f'输出目录: {output_dir}')
    print(f'共 {len(COLLEGES)} 个学院')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
        )

        # 并发爬取学院列表（3个一批）
        all_teachers = []
        semaphore = asyncio.Semaphore(3)

        college_tasks = []
        for college_name, sub_pages in COLLEGES:
            task = crawl_college(context, college_name, sub_pages, semaphore)
            college_tasks.append((college_name, task))

        # 分批运行（3个学院一批）
        for i in range(0, len(college_tasks), 3):
            batch = college_tasks[i:i+3]
            print(f'\n--- 批次 {i//3 + 1}: {[name for name, _ in batch]} ---')
            results = await asyncio.gather(*[task for _, task in batch])
            for (name, _), teachers in zip(batch, results):
                print(f'  ✅ {name}: {len(teachers)} 位教师')
                all_teachers.extend(teachers)

        print(f'\n共提取到 {len(all_teachers)} 位教师（去重后），正在进入详情页提取邮箱...')

        # 进入所有教师的详情页提取邮箱（5个并发）
        email_semaphore = asyncio.Semaphore(5)

        async def crawl_detail(teacher):
            async with email_semaphore:
                page = await context.new_page()
                try:
                    teacher = await extract_email(page, teacher)
                    email_status = '有邮箱' if teacher['email'] else '无邮箱'
                    print(f'  {teacher["name"]}: {email_status}')
                except Exception as e:
                    teacher['email'] = ''
                    teacher['title'] = ''
                finally:
                    await page.close()
                return teacher

        # 分批处理，每批20个
        detailed_teachers = []
        for i in range(0, len(all_teachers), 20):
            batch = all_teachers[i:i+20]
            print(f'  详情页批次 {i//20 + 1}/{ (len(all_teachers)+19)//20 }...')
            results = await asyncio.gather(*[crawl_detail(t) for t in batch])
            detailed_teachers.extend(results)

        await browser.close()

    # 统计
    with_email = [t for t in detailed_teachers if t.get('email')]
    without_email = [t for t in detailed_teachers if not t.get('email')]

    print(f'\n{"="*50}')
    print(f'爬取完成！')
    print(f'总教师数: {len(detailed_teachers)}')
    print(f'有邮箱: {len(with_email)} ({len(with_email)/len(detailed_teachers)*100:.1f}%)')
    print(f'无邮箱: {len(without_email)}')

    # 按学院统计
    from collections import Counter
    college_stats = Counter(t['college'] for t in detailed_teachers)
    college_email_stats = {}
    for t in detailed_teachers:
        c = t['college']
        if c not in college_email_stats:
            college_email_stats[c] = {'total': 0, 'with_email': 0}
        college_email_stats[c]['total'] += 1
        if t.get('email'):
            college_email_stats[c]['with_email'] += 1

    print(f'\n各学院统计:')
    for c in sorted(college_stats.keys()):
        s = college_email_stats[c]
        rate = s['with_email'] / s['total'] * 100 if s['total'] > 0 else 0
        print(f'  {c}: {s["total"]}人, {s["with_email"]}邮箱 ({rate:.1f}%)')

    # 写入 CSV
    import datetime
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_path = output_path / f'南京林业大学_教师邮箱_{timestamp}.csv'

    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['序号', '姓名', '邮箱', '学院', '职称', '主页链接'])
        for idx, t in enumerate(detailed_teachers, 1):
            writer.writerow([idx, t['name'], t.get('email', ''), t['college'], t.get('title', ''), t['url']])

    print(f'\nCSV 已保存: {csv_path}')
    print(f'总记录: {len(detailed_teachers)}')

    # 输出文件路径供后续使用
    result = {
        'csv_path': str(csv_path),
        'total': len(detailed_teachers),
        'with_email': len(with_email),
        'teachers': detailed_teachers,
    }

    # 保存 JSON 供后续处理
    json_path = output_path / 'njfu_result.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'JSON 已保存: {json_path}')


if __name__ == '__main__':
    asyncio.run(main())
