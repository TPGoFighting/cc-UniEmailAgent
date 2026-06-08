"""
南京农业大学 (NJAU) 教师邮箱爬虫 V3

综合所有方案的最佳提取方法
"""

import asyncio
import re
import csv
import datetime
from pathlib import Path
from collections import Counter
from playwright.async_api import async_playwright

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

NAV_KEYWORDS = [
    '首页', '通知', '公告', '概况', '简介', '新闻', '招生', '就业', '学位',
    '学科', '科研', '学术', '党建', '工会', '校友', '捐赠', '登录', '邮箱',
    '联系', '欢迎', '返回', '更多', '详情', '查看', '下载', '搜索', '服务', '导航',
    'English', 'EN', '加入', '收藏', '成果', '奖励', '项目', '专利', '交流', '合作',
    '中科院', '院士', '博士后', '实验', '技术', '党群', '团学', '学生', '活动',
    '实践', '基地', '平台', '基金', '信息', '公开', '奖助', '出国', '留学',
    '考试', '课程', '教学', '方向', '队伍', '全部', '名单', '导师', '在职',
    '兼职', '离退休', '教工', '人事', '财务', '外事', '资产', '安全', '简报',
    '部门', '委员会', '职能', '标志', '报名', '注册', '系统', '空间', '预约',
    '书记', '院长', '规章制度', '教务处', '研究生院', '财务处',
    '地址', '邮编', '电话', '传真', '苏ICP', '版权所有',
    '书记院长信箱', '院长书记邮箱', '学校主页', '南农首页',
    '网站首页', '学院首页', '学校首页', '南农主页', '信息门户',
    '用户登录', '公共事务', '旧版回顾', '英文版', '怀念旧版',
    '设为首页', '加入收藏', '网站管理', '网站维护', '南农邮箱',
    '人才引进', '人才招聘', '师德师风', '退休教授', '专家人才',
    '相关下载', '资料下载', '招聘', '教师风采', '兼职教授',
    '金善宝', '年度进展', '联系我们', '院训院徽', '校园风景',
    '历史沿革', '党政领导', '党委委员', '院徽', '委员会',
    '行政机构', '系别设置', '实验中心', '群团组织', '教研组织',
    '党团活动', '教工之家', '思想理论', '党章党规', '支部建设',
    '党员活动', '检查通报', '学习资料', '心理健康', '学生组织',
    '团务公开', '高校教师', '学院概况', '学院简介', '学院介绍',
    '现任领导', '历任领导', '学院沿革', '机构设置',
    '人才培养', '科学研究', '社会服务', '党建思政', '学生工作',
    '校友之窗', '交流合作', '团学工作', '招生就业', '下载中心',
    '学科建设', '创新创业', '继续教育', '中心', '研究院',
    '职称', '姓名', '搜索', '重置', '下页', '上一页', '下一页',
    '尾页', '首页', '末页', '转到', '页', '条',
]

PUBLIC_PREFIXES = [
    'webmaster', 'admin', 'office', 'info', 'master', 'root', 'postmaster',
    'wxyxz', 'xwcb', 'bgs', 'dangzheng', 'yuanban', 'dangban', 'renshi',
    'jiaowu', 'xuegong', 'tuanwei', 'yanjiusheng', 'gysj', 'gyyz', 'glxb',
    'coe', 'cyxy', 'my', 'zhibao', 'njau', 'xx', 'yy',
]

OUTPUT_DIR = Path('outputs/eeb5bccd-46ec-4078-b265-cdd3e4868702')


def is_nav(text):
    return any(kw in text for kw in NAV_KEYWORDS)


def is_teacher_name(text):
    return bool(re.match(r'^[一-鿿]{2,4}$', text)) and not is_nav(text)


def clean_email_text(text):
    text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
    text = text.replace('[@]', '@').replace('(@)', '@').replace('#@', '@')
    return text


def is_public(email):
    prefix = email.split('@')[0].lower()
    if prefix in ['njau', 'xx', 'yy']:
        return True
    return any(prefix.startswith(p) for p in PUBLIC_PREFIXES)


async def crawl_jsp(context, college, url):
    """JSP 教师卡片模式：提取教师名+faulty主页链接"""
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
                    'name': t['name'], 'email': '',
                    'college': college, 'title': t['title'], 'url': t['url'],
                })

        # 翻页
        for _ in range(20):
            btn = await page.query_selector('a:has-text("下一页")')
            if not btn:
                break
            cls = await btn.get_attribute('class') or ''
            if 'disabled' in cls:
                break
            try:
                await btn.click()
                await asyncio.sleep(3)
                more = await page.evaluate('''() => {
                    const t = []; document.querySelectorAll('a[href*="faculty.njau"]').forEach(a => {
                        const h2 = a.querySelector('h2'); const p = a.querySelector('p');
                        if (h2) t.push({name: h2.textContent.trim(), title: p?p.textContent.trim():'', url: a.href});
                    }); return t;
                }''')
                for t in more:
                    if is_teacher_name(t['name']):
                        results.append({
                            'name': t['name'], 'email': '',
                            'college': college, 'title': t['title'], 'url': t['url'],
                        })
            except Exception:
                break
    except Exception as e:
        print(f'  JSP失败 [{college}]: {e}')
    finally:
        await page.close()

    email_c = sum(1 for r in results if r['email'])
    print(f'  JSP [{college}]: {len(results)} 人, {email_c} 邮箱')
    return results


async def crawl_plain(context, college, url):
    """纯文本教师名提取（马克思主义学院等）"""
    page = await context.new_page()
    results = []
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)
        text = await page.evaluate('() => document.body.innerText')
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if is_teacher_name(line):
                results.append({
                    'name': line, 'email': '',
                    'college': college, 'title': '', 'url': url,
                })
    except Exception as e:
        print(f'  纯文本失败 [{college}]: {e}')
    finally:
        await page.close()
    print(f'  文本 [{college}]: {len(results)} 人')
    return results


async def crawl_text_with_email_proximity(context, college, url):
    """
    文本型页面：用位置邻近法匹配姓名和邮箱
    多次扫描，避免遗漏
    """
    page = await context.new_page()
    results = []
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)
        text = await page.evaluate('() => document.body.innerText')
        text = clean_email_text(text)

        # 提取所有邮箱
        all_emails = EMAIL_RE.findall(text)
        personal_emails = [e.lower() for e in all_emails if not is_public(e.lower())]
        personal_emails = list(set(personal_emails))

        # 提取所有教师名
        names = list(set(re.findall(r'^([一-鿿]{2,4})$', text, re.MULTILINE)))
        names = [n for n in names if is_teacher_name(n)]

        # 方法1: 以名字为中心，找最近的邮箱
        name_to_email = {}
        used_emails = set()
        for name in names:
            pos = text.find(name)
            if pos < 0:
                continue
            # 向后搜索200字符
            nearby = text[pos:pos + 300]
            found = EMAIL_RE.findall(nearby)
            for e in found:
                el = e.lower()
                if not is_public(el) and el not in used_emails:
                    name_to_email[name] = el
                    used_emails.add(el)
                    break

        # 方法2: 反向 - 以邮箱为中心，找最近的名字
        email_to_name = {}
        for em in personal_emails:
            if em in used_emails:
                continue
            pos = text.find(em)
            if pos < 0:
                continue
            before = text[max(0, pos - 60):pos]
            before_names = re.findall(r'([一-鿿]{2,4})', before)
            for n in reversed(before_names):
                if is_teacher_name(n) and n not in name_to_email:
                    email_to_name[n] = em
                    used_emails.add(em)
                    break

        # 合并结果
        for n in names:
            email = name_to_email.get(n, '') or email_to_name.get(n, '')
            results.append({
                'name': n, 'email': email,
                'college': college, 'title': '', 'url': url,
            })

        # 未关联到姓名的邮箱，作为额外记录
        for e in personal_emails:
            if e not in used_emails:
                results.append({
                    'name': '', 'email': e,
                    'college': college, 'title': '', 'url': url,
                })

        # 如果几乎没找到邮箱，再试一次更宽松的策略
        email_c = sum(1 for r in results if r['email'])
        if email_c < 2 and personal_emails:
            # 尝试查找 mailto: 标签的关联
            mailto_data = await page.evaluate('''() => {
                const pairs = [];
                document.querySelectorAll('a[href*="mailto:"]').forEach(a => {
                    const email = a.href.replace('mailto:', '').trim();
                    const row = a.closest('tr, li, div, p') || a.parentElement;
                    pairs.push({email: email, text: row.textContent.trim().substring(0, 300)});
                });
                return pairs;
            }''')
            for md in mailto_data:
                em = md['email'].lower()
                if is_public(em):
                    continue
                # 在容器文本中找名字
                container_names = re.findall(r'([一-鿿]{2,4})', md['text'])
                matched = ''
                for n in container_names:
                    if is_teacher_name(n):
                        matched = n
                        break
                if matched and not any(r['name'] == matched and r['email'] for r in results):
                    results.append({
                        'name': matched, 'email': em,
                        'college': college, 'title': '', 'url': url,
                    })

    except Exception as e:
        print(f'  文本邮箱失败 [{college}]: {e}')
    finally:
        await page.close()

    email_c = sum(1 for r in results if r['email'])
    print(f'  文本邮箱 [{college}]: {len(results)} 条, {email_c} 邮箱')
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

        # ====== 阶段 1: JSP 教师卡片 ======
        print('=== 阶段1: JSP 学院 ===')
        batch1 = []
        for n, u in [
            ('工学院', 'https://coe.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1140'),
            ('信息管理学院', 'https://info.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1076'),
            ('金融学院', 'https://finance.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1230'),
            ('草业学院', 'https://cyxy.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1348'),
            ('生命科学学院', 'https://lfc.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1201'),
            ('资源与环境科学学院', 'https://re.njau.edu.cn/jsfc2.jsp?urltype=tree.TreeTempUrl&wbtreeid=1325'),
            ('外国语学院', 'https://foreign.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1124'),
            ('智慧农业学院', 'https://ai.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1164'),
            ('农学院-农学系', 'https://nx.njau.edu.cn/jsfc_nxx.jsp?urltype=tree.TreeTempUrl&wbtreeid=1227'),
        ]:
            batch1.append(crawl_jsp(context, n, u))
        for r in await asyncio.gather(*batch1):
            all_results.extend(r)

        # ====== 阶段 2: 纯文本教师列表 ======
        print('\n=== 阶段2: 纯文本学院 ===')
        batch2 = []
        for n, u in [
            ('马克思主义学院', 'https://szb.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1143'),
            ('公共管理学院', 'https://clm.njau.edu.cn/2022/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1480'),
        ]:
            batch2.append(crawl_plain(context, n, u))
        for r in await asyncio.gather(*batch2):
            all_results.extend(r)

        # ====== 阶段 3: 文本含邮箱 - 人文学院 ======
        print('\n=== 阶段3: 人文学院 ===')
        batch3 = []
        for dn, du in [
            ('社会学系', 'https://xrw.njau.edu.cn/szdw/shxx.htm'),
            ('旅游管理系', 'https://xrw.njau.edu.cn/szdw/lyglx.htm'),
            ('农村发展系', 'https://xrw.njau.edu.cn/szdw/ncfzx.htm'),
            ('法律系', 'https://xrw.njau.edu.cn/szdw/flx.htm'),
            ('艺术系', 'https://xrw.njau.edu.cn/szdw/ysx.htm'),
            ('科学技术史系', 'https://xrw.njau.edu.cn/szdw/kxjssx.htm'),
        ]:
            batch3.append(crawl_text_with_email_proximity(
                context, f'人文与社会发展学院-{dn}', du))
        for r in await asyncio.gather(*batch3):
            all_results.extend(r)

        # ====== 阶段 4: 经管学院 ======
        print('\n=== 阶段4: 经管学院 ===')
        batch4 = []
        for dn, du in [
            ('农业经济学系', 'https://economy.njau.edu.cn/xksz/szdw1/nyjjxx.htm'),
            ('管理学系', 'https://economy.njau.edu.cn/xksz/szdw1/glxx.htm'),
        ]:
            batch4.append(crawl_text_with_email_proximity(
                context, f'经济管理学院-{dn}', du))
        for r in await asyncio.gather(*batch4):
            all_results.extend(r)

        # ====== 阶段 5: 理学院 ======
        print('\n=== 阶段5: 理学院 ===')
        batch5 = []
        for dn, du in [
            ('化学系', 'https://cos.njau.edu.cn/szdw3/hxx1/qb.htm'),
            ('数学系', 'https://cos.njau.edu.cn/szdw3/sxx/qb.htm'),
            ('物理系', 'https://cos.njau.edu.cn/szdw3/wlx/qb.htm'),
        ]:
            batch5.append(crawl_text_with_email_proximity(
                context, f'理学院-{dn}', du))
        for r in await asyncio.gather(*batch5):
            all_results.extend(r)

        # ====== 阶段 6: 其他学院 ======
        print('\n=== 阶段6: 其他学院 ===')
        batch6 = []
        for n, u in [
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
        ]:
            batch6.append(crawl_text_with_email_proximity(context, n, u))
        for r in await asyncio.gather(*batch6):
            all_results.extend(r)

        await browser.close()

    # ====== 去重 ======
    print(f'\n=== 去重前: {len(all_results)} 条 ===')
    seen = {}
    for r in all_results:
        name = r['name']
        if not name:
            continue
        if name not in seen:
            seen[name] = r
        else:
            ex = seen[name]
            if r['email'] and not ex['email']:
                seen[name] = r
            elif r['email'] and ex['email'] and len(r['college']) > len(ex['college']):
                seen[name] = r
            elif r['title'] and not ex['title']:
                seen[name] = r

    deduped = list(seen.values())
    deduped.sort(key=lambda x: (x['college'] or '', x['name'] or ''))
    with_email = sum(1 for r in deduped if r['email'])
    print(f'=== 去重后: {len(deduped)} 条, 含邮箱: {with_email} 条 ===')

    # 输出
    csv_path = OUTPUT_DIR / '南京农业大学_教师邮箱_V1.0.0.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['序号', '姓名', '邮箱', '学院', '职称', '主页链接'])
        for i, r in enumerate(deduped, 1):
            w.writerow([i, r['name'], r['email'], r['college'], r['title'], r['url']])
    print(f'\n✅ CSV: {csv_path}')

    # 统计
    cc = Counter(r['college'] for r in deduped)
    print('\n各学院统计:')
    for c, n in cc.most_common():
        ec = sum(1 for r in deduped if r['college'] == c and r['email'])
        print(f'  {c}: {n} 人, {ec} 邮箱')


if __name__ == '__main__':
    asyncio.run(main())
