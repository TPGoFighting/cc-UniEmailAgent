"""
南京农业大学 (NJAU) 教师邮箱爬虫

架构分析：
1. 大部分学院使用 JSP 教师管理系统 (jsfc.jsp)，教师卡片包含 faculty.njau.edu.cn 链接
2. 人文学院、经管学院等有直接嵌入页面的邮箱
3. faculty.njau.edu.cn 教师主页系统全面维护中，无法获取详情页
"""

import asyncio
import re
import csv
import os
from pathlib import Path
from playwright.async_api import async_playwright

# 邮箱正则
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# 导航词黑名单
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
    '思想理论', '党章党规', '支部建设', '党员活动', '检查通报', '学习资料', '校友工作',
    '就业工作', '心理健康', '学生组织', '团务公开', '检查通报', '高校教师',
    '经管学院', '理学院', '工学院', '继续教育', '创新创业', '中心', '研究院',
    'English', 'EN', '设为首页', '加入收藏', '网站管理', '网站维护',
    '南农邮箱', '信息门户', '学校主页', '用户登录',
    '职称', '姓名', '搜索', '重置', '共115条', '共', '条', '下页', '上一页', '下一页',
    '尾页', '首页', '末页', '转到', '页',
    '地址', '邮编', '电话', '传真', '苏ICP', '版权所有',
    '书记院长信箱', '院长书记邮箱',
]

PUBLIC_EMAIL_PREFIXES = [
    'webmaster', 'admin', 'office', 'info', 'master', 'root', 'postmaster',
    'wxyxz', 'xwcb', 'bgs', 'dangzheng', 'yuanban', 'dangban', 'renshi',
    'jiaowu', 'xuegong', 'tuanwei', 'yanjiusheng', 'gysj', 'gyyz', 'glxb',
    'coe', 'cyxy', 'my', 'zhibao', 'njau', 'xx', 'yy',
]


def is_nav(text):
    """检查是否是导航文字"""
    return any(kw in text for kw in NAV_KEYWORDS)


def is_teacher_name(text):
    """验证是否为教师姓名（2-4个汉字）"""
    return bool(re.match(r'^[一-鿿]{2,4}$', text))


def clean_email(text):
    """反爬恢复"""
    text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
    text = text.replace('[@]', '@').replace('(@)', '@').replace('#@', '@')
    return text


def is_public_email(email):
    """检查是否为公共邮箱"""
    prefix = email.split('@')[0].lower()
    exclude_exact = ['njau', 'xx', 'yy']
    if prefix in exclude_exact:
        return True
    for p in PUBLIC_EMAIL_PREFIXES:
        if prefix.startswith(p):
            return True
    return False


OUTPUT_DIR = Path('outputs/eeb5bccd-46ec-4078-b265-cdd3e4868702')


async def crawl_jsp_page(context, college_name, url):
    """
    爬取 JSP 教师管理系统页面
    HTML 结构: <li><a href="faculty.njau.edu.cn/xxx/zh_CN/index.htm">
                <h2>姓名</h2><p>职称</p><div class="more"><span>教师主页</span></div></a></li>
    """
    page = await context.new_page()
    results = []
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        # 提取教师卡片信息
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

        # 翻页处理
        page_num = 1
        while page_num < 20:
            next_btn = await page.query_selector('a:has-text("下一页")')
            if not next_btn:
                break
            next_class = await next_btn.get_attribute('class') or ''
            if 'disabled' in next_class:
                break
            try:
                await next_btn.click()
                await asyncio.sleep(3)
                more = await page.evaluate('''() => {
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
                for t in more:
                    if is_teacher_name(t['name']):
                        results.append({
                            'name': t['name'],
                            'email': '',
                            'college': college_name,
                            'title': t['title'],
                            'url': t['url'],
                        })
                page_num += 1
            except Exception:
                break

    except Exception as e:
        print(f'  [{college_name}] JSP 页面失败: {e}')
    finally:
        await page.close()

    print(f'  [{college_name}] JSP 提取: {len(results)} 名教师')
    return results


async def crawl_text_page(context, college_name, url):
    """
    爬取文本型教师页面（邮箱和姓名均在页面文本中）
    如: 人文学院、经管学院等
    """
    page = await context.new_page()
    results = []
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        text = await page.evaluate('() => document.body.innerText')
        text = clean_email(text)

        # 提取所有邮箱
        emails = EMAIL_RE.findall(text)
        emails = [e.lower() for e in emails if not is_public_email(e)]
        emails = list(set(emails))

        # 提取所有教师名
        all_names = []
        # 方法1: 从 <a> 标签提取
        links = await page.evaluate('''() => {
            return Array.from(document.querySelectorAll('a')).map(a => a.textContent.trim());
        }''')
        for l in links:
            if is_teacher_name(l):
                all_names.append(l)

        # 方法2: 从文本中找 "XXX 教授/副教授/讲师" 模式
        name_patterns = re.findall(
            r'^([一-鿿]{2,4})\s*(教授|副教授|助理教授|讲师|研究员|副研究员|'
            r'助理研究员|工程师|高级工程师|实验师|高级实验师|博导|硕导)',
            text, re.MULTILINE
        )
        for np_ in name_patterns:
            all_names.append(np_[0])

        # 去重并排除导航
        all_names = list(set(n for n in all_names if is_teacher_name(n) and not is_nav(n)))

        # 关联邮箱与姓名
        used_emails = set()
        for name in all_names:
            # 在文本中找到离该姓名最近的邮箱
            name_pos = text.find(name)
            if name_pos < 0:
                continue
            # 搜索附近 200 字符内的邮箱
            nearby = text[max(0, name_pos - 50):name_pos + 200]
            found_emails = EMAIL_RE.findall(nearby)
            email = ''
            for e in found_emails:
                e_lower = e.lower()
                if not is_public_email(e_lower) and e_lower not in used_emails:
                    email = e_lower
                    used_emails.add(e_lower)
                    break

            results.append({
                'name': name,
                'email': email,
                'college': college_name,
                'title': '',
                'url': url,
            })

        # 如果还有未关联到姓名的邮箱，尝试独立添加
        for e in emails:
            if e not in used_emails:
                results.append({
                    'name': '',
                    'email': e,
                    'college': college_name,
                    'title': '',
                    'url': url,
                })

    except Exception as e:
        print(f'  [{college_name}] 文本页面失败: {e}')
    finally:
        await page.close()

    email_count = sum(1 for r in results if r['email'])
    print(f'  [{college_name}] 文本提取: {len(results)} 条, {email_count} 个邮箱')
    return results


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        )

        # ============================
        # 1. JSP 教师管理系统学院
        # ============================
        jsp_colleges = [
            ('工学院', 'https://coe.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1140'),
            ('信息管理学院', 'https://info.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1076'),
            ('金融学院', 'https://finance.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1230'),
            ('草业学院', 'https://cyxy.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1348'),
            ('生命科学学院', 'https://lfc.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1201'),
            ('资源与环境科学学院', 'https://re.njau.edu.cn/jsfc2.jsp?urltype=tree.TreeTempUrl&wbtreeid=1325'),
            ('外国语学院', 'https://foreign.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1124'),
            ('马克思主义学院', 'https://szb.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1143'),
            ('智慧农业学院', 'https://ai.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1164'),
            ('公共管理学院', 'https://clm.njau.edu.cn/2022/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1480'),
        ]

        # ============================
        # 2. 农学院 - 多个子系 JSP 页面
        # ============================
        nongxue_depts = [
            ('农学系', 'https://nx.njau.edu.cn/jsfc_nxx.jsp?urltype=tree.TreeTempUrl&wbtreeid=1227'),
            ('植物科学系', 'https://nx.njau.edu.cn/jfc_zwkx.jsp?urltype=tree.TreeTempUrl&wbtreeid=1228'),
            ('遗传育种系', 'https://nx.njau.edu.cn/jsfc_yczz.jsp?urltype=tree.TreeTempUrl&wbtreeid=1230'),
            ('种业科学系', 'https://nx.njau.edu.cn/jsfc_zykx.jsp?urltype=tree.TreeTempUrl&wbtreeid=1232'),
        ]

        # ============================
        # 3. 人文学院 - 文本页面（含邮箱）
        # ============================
        renwen_depts = [
            ('社会学系', 'https://xrw.njau.edu.cn/szdw/shxx.htm'),
            ('旅游管理系', 'https://xrw.njau.edu.cn/szdw/lyglx.htm'),
            ('农村发展系', 'https://xrw.njau.edu.cn/szdw/ncfzx.htm'),
            ('法律系', 'https://xrw.njau.edu.cn/szdw/flx.htm'),
            ('艺术系', 'https://xrw.njau.edu.cn/szdw/ysx.htm'),
            ('科学技术史系', 'https://xrw.njau.edu.cn/szdw/kxjssx.htm'),
        ]

        # ============================
        # 4. 经管学院 - 文本页面（含邮箱）
        # ============================
        jingguan_depts = [
            ('农业经济学系', 'https://economy.njau.edu.cn/xksz/szdw1/nyjjxx.htm'),
            ('管理学系', 'https://economy.njau.edu.cn/xksz/szdw1/glxx.htm'),
        ]

        # ============================
        # 5. 理学院 - 子系页面
        # ============================
        lixue_depts = [
            ('化学系', 'https://cos.njau.edu.cn/szdw3/hxx1/qb.htm'),
            ('数学系', 'https://cos.njau.edu.cn/szdw3/sxx/qb.htm'),
            ('物理系', 'https://cos.njau.edu.cn/szdw3/wlx/qb.htm'),
        ]

        # ============================
        # 6. 其他学院
        # ============================
        other_colleges = [
            ('园艺学院', [
                ('果树学科', 'https://yyxy.njau.edu.cn/szdw/gsxk.htm'),
                ('蔬菜学科', 'https://yyxy.njau.edu.cn/szdw/scxk.htm'),
                ('茶学学科', 'https://yyxy.njau.edu.cn/szdw/cxxk.htm'),
                ('观赏园艺学科', 'https://yyxy.njau.edu.cn/szdw/gsyyxk.htm'),
                ('中药学科', 'https://yyxy.njau.edu.cn/szdw/zyxk.htm'),
                ('设施园艺学科', 'https://yyxy.njau.edu.cn/szdw/ssyyxk.htm'),
                ('风景园林学科', 'https://yyxy.njau.edu.cn/szdw/fjylxk.htm'),
            ]),
            ('动物医学院', [
                ('师资队伍', 'https://cvm.njau.edu.cn/xksz/szdw.htm'),
            ]),
            ('动物科技学院', [
                ('教师目录', 'https://dky.njau.edu.cn/xksz/jsml.htm'),
            ]),
            ('食品科学技术学院', [
                ('专任教师', 'https://food.njau.edu.cn/szdw/zrjs1/azcfl.htm'),
            ]),
            ('植物保护学院', [
                ('昆虫学系', 'https://plant.njau.edu.cn/kcxx.jsp?urltype=tree.TreeTempUrl&wbtreeid=1195'),
                ('农药科学系', 'https://plant.njau.edu.cn/bgs.jsp?urltype=tree.TreeTempUrl&wbtreeid=1200'),
            ]),
        ]

        all_results = []

        # ---- 阶段 1: 并行爬取 JSP 学院 ----
        print('=== 阶段 1: JSP 学院 (无邮箱, 仅教师名) ===')
        jsp_tasks = [crawl_jsp_page(context, name, url) for name, url in jsp_colleges]
        # 农学院的子系也是 JSP 格式
        for dept_name, dept_url in nongxue_depts:
            jsp_tasks.append(
                crawl_jsp_page(context, f'农学院-{dept_name}', dept_url))
        batch_results = await asyncio.gather(*jsp_tasks)
        for r in batch_results:
            all_results.extend(r)

        # ---- 阶段 2: 文本页面学院（含邮箱） ----
        print('\n=== 阶段 2: 文本页面学院 (含邮箱) ===')

        # 人文学院各系
        renwen_tasks = []
        for dept_name, dept_url in renwen_depts:
            renwen_tasks.append(
                crawl_text_page(context, f'人文与社会发展学院-{dept_name}', dept_url))
        batch_results = await asyncio.gather(*renwen_tasks)
        for r in batch_results:
            all_results.extend(r)

        # 经管学院各系
        jingguan_tasks = []
        for dept_name, dept_url in jingguan_depts:
            jingguan_tasks.append(
                crawl_text_page(context, f'经济管理学院-{dept_name}', dept_url))
        batch_results = await asyncio.gather(*jingguan_tasks)
        for r in batch_results:
            all_results.extend(r)

        # 理学院各系
        lixue_tasks = []
        for dept_name, dept_url in lixue_depts:
            lixue_tasks.append(
                crawl_text_page(context, f'理学院-{dept_name}', dept_url))
        batch_results = await asyncio.gather(*lixue_tasks)
        for r in batch_results:
            all_results.extend(r)

        # ---- 阶段 3: 其他学院 ----
        print('\n=== 阶段 3: 其他学院 ===')
        other_tasks = []
        for college_name, depts in other_colleges:
            for dept_name, dept_url in depts:
                other_tasks.append(
                    crawl_text_page(context, f'{college_name}-{dept_name}', dept_url))
        batch_results = await asyncio.gather(*other_tasks)
        for r in batch_results:
            all_results.extend(r)

        await browser.close()

    # ============================
    # 去重与排序
    # ============================
    print(f'\n=== 去重前: {len(all_results)} 条 ===')

    # 按姓名去重（同名保留有邮箱的）
    seen_names = {}
    for r in all_results:
        name = r['name']
        if not name:
            continue
        if name not in seen_names:
            seen_names[name] = r
        else:
            existing = seen_names[name]
            # 保留有邮箱的版本
            if r['email'] and not existing['email']:
                seen_names[name] = r
            elif r['email'] and existing['email'] and r['college'] != existing['college']:
                # 不同学院同名，加学院后缀区分
                pass

    deduped = list(seen_names.values())
    deduped.sort(key=lambda x: (x['college'] or '', x['name'] or ''))

    print(f'=== 去重后: {len(deduped)} 条 ===')

    # 统计
    with_email = sum(1 for r in deduped if r['email'])
    print(f'=== 含邮箱: {with_email} 条 ===')

    # ============================
    # 输出 CSV
    # ============================
    timestamp = asyncio.__dict__.get('__name__', '')
    import datetime
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_path = OUTPUT_DIR / f'南京农业大学_教师邮箱_V1.0.0.csv'

    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['序号', '姓名', '邮箱', '学院', '职称', '主页链接'])
        for i, r in enumerate(deduped, 1):
            writer.writerow([
                i,
                r['name'],
                r['email'],
                r['college'],
                r['title'],
                r['url'],
            ])

    print(f'\n✅ CSV 已保存: {csv_path}')
    print(f'   总计 {len(deduped)} 条记录, {with_email} 个邮箱')


if __name__ == '__main__':
    asyncio.run(main())
