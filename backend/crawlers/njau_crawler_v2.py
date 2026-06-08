"""
南京农业大学 (NJAU) 教师邮箱爬虫 V2

三大页面模式：
1. JSP 系统 (jsfc.jsp) - 教师卡片含 faculty.njau.edu.cn 链接，无邮箱（教师主页维护中）
2. 纯文本列表 - 教师名以文本形式列在页面上（如马克思主义学院）
3. 结构化文本 - 教师名和邮箱均嵌入在页面文本中（如人文学院、经管学院）
"""

import asyncio
import re
import csv
import datetime
from pathlib import Path
from playwright.async_api import async_playwright

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

NAV_KEYWORDS = [
    '首页', '概况', '简介', '新闻', '通知', '公告', '招生', '培养', '就业', '学位',
    '学科', '科研', '学术', '党建', '工会', '校友', '捐赠', '图书馆', '校园', '地图',
    '网站', '登录', '邮箱', '联系', '欢迎', '返回', '更多', '详情', '查看', '下载',
    '师资', '教师', '硕士', '本科', '研究', '行政', '管理', '教职', '荣休', '访问',
    '系科', '教研', '诚聘', '师德', '监督', '信箱', '机构', '设置', '领导', '人才',
    '学校', '学院', '搜索', '服务', '导航', 'English', '加入', '收藏', '成果', '转化',
    '奖励', '项目', '专利', '交流', '合作', '国际化', '中科院', '院士', '博士后',
    '实验', '技术', '党群', '团学', '学生', '活动', '实践', '基地', '平台', '基金',
    '信息', '公开', '奖助', '出国', '留学', '考试', '课程', '教学', '杰出', '方向',
    '队伍', '全部', '名单', '导师', '在职', '兼职', '专任', '离退休', '教工', '人事',
    '财务', '外事', '资产', '安全', '简报', '部门', '委员会', '职能', '标志', '报名',
    '注册', '系统', '空间', '预约', '书记', '院长', '规章制度', '教务处', '研究生院',
    '财务处', '网站首页', '学院首页', '学校首页', '学校主页', '南农首页', '南农主页',
    '学院介绍', '人才引进', '人才招聘', '党务人事', '院办服务', '教师风采', '兼职教授',
    '师德师风', '退休教授', '专家人才', '学科设置', '二级学科', '学科简介', '学科概况',
    '科研平台', '科研项目', '科研成果', '科研获奖', '创新团队', '研究平台', '科研动态',
    '学生动态', '实训平台', '学术交流', '党建动态', '工会动态', '党务公开', '政策理论',
    '相关下载', '资料下载', '规章制度', '学校文件', '招聘', '网站管理', '旧版回顾',
    '怀念旧版', '英文版', '信息门户', '用户登录', '公共事务', '捐赠', '办事指南',
    '学生园地', '学生事务', '国际交流', '国际会议', '出国交流', '校友工作', '院士风采',
    '杰出校友', '校友名录', '校友活动', '时光剪影', '学院沿革', '历任领导', '现任领导',
    '机构设置', '人才培养', '科学研究', '社会服务', '党建思政', '学生工作', '校友之窗',
    '交流合作', '团学工作', '招生就业', '金善宝', '年度进展', '联系我们', '院训院徽',
    '校园风景', '历史沿革', '党政领导', '党委委员', '院徽', '委员会', '行政机构',
    '系别设置', '实验中心', '群团组织', '教研组织', '党团活动', '教工之家',
    '思想理论', '党章党规', '支部建设', '党员活动', '检查通报', '学习资料',
    '就业工作', '心理健康', '学生组织', '团务公开', '高校教师',
    'English', 'EN', '设为首页', '加入收藏', '网站管理', '网站维护',
    '南农邮箱', '信息门户', '学校主页', '用户登录',
    '职称', '姓名', '搜索', '重置', '下页', '上一页', '下一页',
    '尾页', '首页', '末页', '转到', '页', '末页', '末页',
    '地址', '邮编', '电话', '传真', '苏ICP', '版权所有',
    '书记院长信箱', '院长书记邮箱',
    '系统提示', '抱歉', '通知公告', '教学改革', '实验教学',
    '教学成果', '课程建设', '教材建设', '实践教学',
    '下载中心', '党委工作', '工会工作',
    '网站首页', '学科建设', '人才培养', '社会服务',
    '国际合作', '人才队伍', 'EnglishVersion', '选课系统',
    '信息中心', '智慧南农', '网络服务', '校园卡',
    '教务系统', '科研系统', '人事系统', '财务系统',
    '研究生系统', '实验平台', '仪器共享', '大型仪器',
    '样本库', '招生信息', '就业信息', '学工队伍',
]

PUBLIC_EMAIL_PREFIXES = [
    'webmaster', 'admin', 'office', 'info', 'master', 'root', 'postmaster',
    'wxyxz', 'xwcb', 'bgs', 'dangzheng', 'yuanban', 'dangban', 'renshi',
    'jiaowu', 'xuegong', 'tuanwei', 'yanjiusheng', 'gysj', 'gyyz', 'glxb',
    'coe', 'cyxy', 'my', 'zhibao', 'njau', 'xx', 'yy',
]

OUTPUT_DIR = Path('outputs/eeb5bccd-46ec-4078-b265-cdd3e4868702')


def is_nav(text):
    return any(kw in text for kw in NAV_KEYWORDS)


def is_teacher_name(text):
    return bool(re.match(r'^[一-鿿]{2,4}$', text))


def clean_email(text):
    text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
    text = text.replace('[@]', '@').replace('(@)', '@').replace('#@', '@')
    return text


def is_public_email(email):
    prefix = email.split('@')[0].lower()
    exclude_exact = ['njau', 'xx', 'yy']
    if prefix in exclude_exact:
        return True
    for p in PUBLIC_EMAIL_PREFIXES:
        if prefix.startswith(p):
            return True
    return False


async def crawl_jsp_page(context, college_name, url):
    """JSP 教师卡片页面：提取含 faculty.njau.edu.cn 链接的教师"""
    page = await context.new_page()
    results = []
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        teachers = await page.evaluate('''() => {
            const teachers = [];
            document.querySelectorAll('a[href*="faculty.njau"]').forEach(a => {
                const h2 = a.querySelector('h2');
                const p = a.querySelector('p');
                if (h2) {
                    teachers.push({
                        name: h2.textContent.trim(),
                        title: p ? p.textContent.trim() : '',
                        url: a.href
                    });
                }
            });
            return teachers;
        }''')

        for t in teachers:
            if is_teacher_name(t['name']):
                results.append({
                    'name': t['name'],
                    'email': '',
                    'college': college_name,
                    'title': t['title'],
                    'url': t['url'],
                })
    except Exception as e:
        print(f'  [{college_name}] JSP 失败: {e}')
    finally:
        await page.close()

    print(f'  [{college_name}] JSP 提取: {len(results)} 名教师')
    return results


async def crawl_plain_text_list(context, college_name, url):
    """
    纯文本教师列表页面：教师姓名以文本形式嵌入，无链接
    如：马克思主义学院 (szb.njau.edu.cn)
    """
    page = await context.new_page()
    results = []
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        text = await page.evaluate('() => document.body.innerText')
        lines = text.split('\n')

        # 提取教师名单（在 "姓名：" 区域后的2-4字中文）
        # 马克思主义学院格式: 每行一个教师姓名 + 职称
        in_teacher_area = False
        for line in lines:
            line = line.strip()
            if '搜索 重置' in line or '姓名：' in line:
                in_teacher_area = True
                continue
            if '共' in line and '条' in line:
                in_teacher_area = False
                continue
            if not in_teacher_area:
                continue
            if not line:
                continue

            # 提取姓名（行首的2-4汉字）
            match = re.match(r'^([一-鿿]{2,4})$', line)
            if match:
                name = match.group(1)
                if not is_nav(name):
                    results.append({
                        'name': name,
                        'email': '',
                        'college': college_name,
                        'title': '',
                        'url': url,
                    })

    except Exception as e:
        print(f'  [{college_name}] 纯文本列表失败: {e}')
    finally:
        await page.close()

    print(f'  [{college_name}] 纯文本提取: {len(results)} 名教师')
    return results


async def crawl_text_with_email(context, college_name, url):
    """
    结构化文本页面：教师名和邮箱关联
    如：人文学院、经管学院 - 有邮箱直接嵌入在页面中
    """
    page = await context.new_page()
    results = []
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        # 获取页面中所有结构块
        blocks = await page.evaluate('''() => {
            // 获取段落块：每个 tr 或 分割段落
            const blocks = [];
            // Method 1: table rows
            document.querySelectorAll('tr').forEach(tr => {
                const text = tr.textContent.trim().replace(/\\s+/g, ' ');
                if (text.length > 0) blocks.push(text);
            });
            if (blocks.length < 3) {
                // Method 2: split by double newlines
                const text = document.body.innerText;
                text.split('\\n\\n').forEach(p => {
                    p = p.trim().replace(/\\s+/g, ' ');
                    if (p.length > 0) blocks.push(p);
                });
            }
            return blocks;
        }''')

        # 如果块太少，用备选方法
        if len(blocks) < 5:
            text = await page.evaluate('() => document.body.innerText')
            text = clean_email(text)
            paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
            blocks = paragraphs

        # 从每个块中提取姓名+邮箱
        paired = []
        for block in blocks:
            block_clean = clean_email(block)
            names_in_block = re.findall(r'([一-鿿]{2,4})', block_clean)
            emails_in_block = EMAIL_RE.findall(block_clean)
            personal_emails = [e.lower() for e in emails_in_block if not is_public_email(e.lower())]

            if personal_emails:
                # 关联：每个邮箱找最近的名字
                for email in personal_emails:
                    email_pos = block_clean.find(email)
                    # 在邮箱前面找最近的名字（限30字符内）
                    before = block_clean[max(0, email_pos - 40):email_pos]
                    before_names = re.findall(r'([一-鿿]{2,4})', before)
                    matched_name = ''
                    for n in reversed(before_names):
                        if not is_nav(n):
                            matched_name = n
                            break
                    paired.append({
                        'name': matched_name,
                        'email': email,
                        'college': college_name,
                        'title': '',
                        'url': url,
                    })

        # 也提取纯名（无邮箱的）
        seen_emails = set()
        for p in paired:
            if p['email']:
                seen_emails.add(p['email'])

        for block in blocks:
            names = re.findall(r'([一-鿿]{2,4})', block)
            for n in names:
                if is_teacher_name(n) and not is_nav(n):
                    # 检查是否已有
                    if not any(r['name'] == n for r in paired):
                        paired.append({
                            'name': n,
                            'email': '',
                            'college': college_name,
                            'title': '',
                            'url': url,
                        })

        # 去重
        seen = {}
        for r in paired:
            key = r['name'] + '|' + r['email']
            if key not in seen:
                seen[key] = r
        results = list(seen.values())

    except Exception as e:
        print(f'  [{college_name}] 文本页面失败: {e}')
    finally:
        await page.close()

    email_count = sum(1 for r in results if r['email'])
    print(f'  [{college_name}] 文本提取: {len(results)} 条, {email_count} 个邮箱')
    return results


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        )

        # ============================
        # 阶段 1: JSP 教师卡片（有 faculty.njau.edu.cn 链接）
        # ============================
        print('=== 阶段 1: JSP 教师卡片 ===')
        jsp_urls = [
            ('工学院', 'https://coe.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1140'),
            ('信息管理学院', 'https://info.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1076'),
            ('金融学院', 'https://finance.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1230'),
            ('草业学院', 'https://cyxy.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1348'),
            ('生命科学学院', 'https://lfc.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1201'),
            ('资源与环境科学学院', 'https://re.njau.edu.cn/jsfc2.jsp?urltype=tree.TreeTempUrl&wbtreeid=1325'),
            ('外国语学院', 'https://foreign.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1124'),
            ('智慧农业学院', 'https://ai.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1164'),
            ('农学院-农学系', 'https://nx.njau.edu.cn/jsfc_nxx.jsp?urltype=tree.TreeTempUrl&wbtreeid=1227'),
        ]
        jsp_tasks = [crawl_jsp_page(context, n, u) for n, u in jsp_urls]
        for r in await asyncio.gather(*jsp_tasks):
            all_results.extend(r)

        # ============================
        # 阶段 2: 纯文本教师列表（无链接）
        # ============================
        print('\n=== 阶段 2: 纯文本教师列表 ===')
        plain_urls = [
            ('马克思主义学院', 'https://szb.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1143'),
            ('公共管理学院', 'https://clm.njau.edu.cn/2022/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1480'),
        ]
        plain_tasks = [crawl_plain_text_list(context, n, u) for n, u in plain_urls]
        for r in await asyncio.gather(*plain_tasks):
            all_results.extend(r)

        # ============================
        # 阶段 3: 结构化文本页面（含邮箱）
        # ============================
        print('\n=== 阶段 3: 文本含邮箱页面 ===')

        # 人文与发展学院各系
        renwen_depts = [
            ('人文与社会发展学院', [
                '社会学系', '旅游管理系', '农村发展系', '法律系', '艺术系', '科学技术史系',
            ]),
        ]
        for college, depts in renwen_depts:
            tasks = []
            base_url = 'https://xrw.njau.edu.cn/szdw/'
            url_map = {
                '社会学系': 'shxx.htm',
                '旅游管理系': 'lyglx.htm',
                '农村发展系': 'ncfzx.htm',
                '法律系': 'flx.htm',
                '艺术系': 'ysx.htm',
                '科学技术史系': 'kxjssx.htm',
            }
            for d in depts:
                tasks.append(crawl_text_with_email(
                    context, f'{college}-{d}', base_url + url_map[d]))
            for r in await asyncio.gather(*tasks):
                all_results.extend(r)

        # 经济管理学院各系
        jingguan_depts = [
            ('农业经济学系', 'https://economy.njau.edu.cn/xksz/szdw1/nyjjxx.htm'),
            ('管理学系', 'https://economy.njau.edu.cn/xksz/szdw1/glxx.htm'),
        ]
        tasks = [crawl_text_with_email(context, f'经济管理学院-{n}', u) for n, u in jingguan_depts]
        for r in await asyncio.gather(*tasks):
            all_results.extend(r)

        # 理学院各系
        lixue_depts = [
            ('化学系', 'https://cos.njau.edu.cn/szdw3/hxx1/qb.htm'),
            ('数学系', 'https://cos.njau.edu.cn/szdw3/sxx/qb.htm'),
            ('物理系', 'https://cos.njau.edu.cn/szdw3/wlx/qb.htm'),
        ]
        tasks = [crawl_text_with_email(context, f'理学院-{n}', u) for n, u in lixue_depts]
        for r in await asyncio.gather(*tasks):
            all_results.extend(r)

        # ============================
        # 阶段 4: 其他学院
        # ============================
        print('\n=== 阶段 4: 其他学院 ===')
        other_urls = [
            ('园艺学院-果树学科', 'https://yyxy.njau.edu.cn/szdw/gsxk.htm'),
            ('园艺学院-蔬菜学科', 'https://yyxy.njau.edu.cn/szdw/scxk.htm'),
            ('园艺学院-茶学学科', 'https://yyxy.njau.edu.cn/szdw/cxxk.htm'),
            ('园艺学院-观赏园艺学科', 'https://yyxy.njau.edu.cn/szdw/gsyyxk.htm'),
            ('园艺学院-中药学科', 'https://yyxy.njau.edu.cn/szdw/zyxk.htm'),
            ('园艺学院-设施园艺学科', 'https://yyxy.njau.edu.cn/szdw/ssyyxk.htm'),
            ('园艺学院-风景园林学科', 'https://yyxy.njau.edu.cn/szdw/fjylxk.htm'),
            ('食品科学技术学院-专任教师', 'https://food.njau.edu.cn/szdw/zrjs1/azcfl.htm'),
            ('动物科技学院-教师目录', 'https://dky.njau.edu.cn/xksz/jsml.htm'),
            ('动物医学院-师资队伍', 'https://cvm.njau.edu.cn/xksz/szdw.htm'),
            ('植物保护学院-昆虫学系', 'https://plant.njau.edu.cn/kcxx.jsp?urltype=tree.TreeTempUrl&wbtreeid=1195'),
            ('植物保护学院-农药科学系', 'https://plant.njau.edu.cn/bgs.jsp?urltype=tree.TreeTempUrl&wbtreeid=1200'),
        ]
        tasks = [crawl_text_with_email(context, n, u) for n, u in other_urls]
        for r in await asyncio.gather(*tasks):
            all_results.extend(r)

        # ============================
        # 阶段 5: 植保学院主教师目录（有faculty链接）
        # ============================
        print('\n=== 阶段 5: 补充JSP ===')
        extra_jsp = [
            ('植物保护学院-教师目录', 'https://plant.njau.edu.cn/zwbhxy_all.jsp?urltype=tree.TreeTempUrl&wbtreeid=1192'),
        ]
        tasks = [crawl_jsp_page(context, n, u) for n, u in extra_jsp]
        for r in await asyncio.gather(*tasks):
            all_results.extend(r)

        await browser.close()

    # ============================
    # 去重与排序
    # ============================
    print(f'\n=== 去重前: {len(all_results)} 条 ===')

    seen_names = {}
    for r in all_results:
        name = r['name']
        if not name:
            continue
        if name not in seen_names:
            seen_names[name] = r
        else:
            existing = seen_names[name]
            # 保留有邮箱且有学院名称的版本
            if r['email'] and not existing['email']:
                seen_names[name] = r
            elif r['email'] and existing['email']:
                # 保留学院名更完整的
                if len(r['college']) > len(existing['college']):
                    seen_names[name] = r
                elif not existing['title'] and r['title']:
                    seen_names[name] = r

    deduped = list(seen_names.values())
    deduped.sort(key=lambda x: (x['college'] or '', x['name'] or ''))

    with_email = sum(1 for r in deduped if r['email'])
    print(f'=== 去重后: {len(deduped)} 条 ===')
    print(f'=== 含邮箱: {with_email} 条 ===')

    # 输出 CSV
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_path = OUTPUT_DIR / f'南京农业大学_教师邮箱_V1.0.0.csv'

    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['序号', '姓名', '邮箱', '学院', '职称', '主页链接'])
        for i, r in enumerate(deduped, 1):
            writer.writerow([i, r['name'], r['email'], r['college'],
                           r['title'], r['url']])

    print(f'\n✅ CSV: {csv_path}')
    print(f'   总计 {len(deduped)} 条, {with_email} 个邮箱')

    # 按学院统计
    from collections import Counter
    cc = Counter(r['college'] for r in deduped)
    print('\n各学院教师数:')
    for c, n in cc.most_common():
        ec = sum(1 for r in deduped if r['college'] == c and r['email'])
        print(f'  {c}: {n} 人, {ec} 邮箱 ({ec*100//n if n else 0}%)')


if __name__ == '__main__':
    asyncio.run(main())
