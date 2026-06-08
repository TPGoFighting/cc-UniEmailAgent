"""
南京林业大学 (NJFU) 教师邮箱爬虫
使用 Playwright + asyncio 并行爬取
"""
import asyncio
import re
import csv
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path("outputs/9e689a19-b5ca-42bf-98bd-be621a7b951c")
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# 导航关键词黑名单（用于过滤非教师链接）
NAV_KW = [
    '概况', '简介', '新闻', '通知', '公告', '招生', '培养', '就业', '学位', '学科',
    '科研', '学术', '党建', '工会', '校友', '捐赠', '图书馆', '网站', '登录', '邮箱',
    '联系', '欢迎', '首页', '返回', '更多', '详情', '查看', '下载', '师资', '教师',
    '硕士', '本科', '研究', '行政', '管理', '教职', '荣休', '访问', '系科', '教研',
    '诚聘', '师德', '监督', '信箱', '机构', '设置', '领导', '人才', '学校', '学院',
    '搜索', '服务', '导航', 'English', '加入', '收藏', '成果', '转化', '奖励', '项目',
    '专利', '交流', '合作', '国际化', '院士', '博士后', '实验', '技术', '党群', '团学',
    '学生', '活动', '实践', '基地', '平台', '基金', '信息', '公开', '奖助', '出国',
    '留学', '考试', '课程', '教学', '杰出', '方向', '队伍', '全部', '名单', '导师',
    '在职', '兼职', '专任', '离退休', '教工', '人事', '财务', '外事', '资产', '安全',
    '简报', '部门', '委员会', '职能', '标志', '报名', '注册', '系统', '空间', '预约',
    '教师登录', '书记', '院长', '规章制度', '微服务', '教务处', '研究生院', '财务处',
    '学科建设', '党委', '团委', '学工', '学生工作', '科学研究', '人才培养',
    '组织机构', '现任领导', '历任领导', '历史沿革', '两办', '产业', '特聘',
    '教授', '副教授', '讲师', '学科带头人', '物理', '化学', '生物',
    '2025', '2026', '2024', '2023', '2022', '2021', '2020',
    '党政', '党校', '纪检', '统战', '品牌', '评优', '科技', '创新',
    '实践', '心理', '健康', '学风', '网上', '基金', '申报', '招聘',
    '校园', '院友', '行政', '实验', '设备', '仪器', '中心', '委员会', '秘书',
    '网站首页', '用户登陆', '用户登录', 'EN', '旧版', '版',
    '搜索结果', '诚邀加盟', '案例中心', '人文之星',
]

# 合法的职称关键词
TITLE_KW = ['教授', '副教授', '助理教授', '讲师', '研究员', '副研究员', '助理研究员',
            '工程师', '高级工程师', '博导', '硕导', '院士', '实验师', '高级实验师']

# ========== 学院定义 ==========
# 每个条目：(学院名, 教师列表URL, 备注)
# url_type: 'list' = 标准列表页提取教师名+详情页找邮箱
#           'inline' = 邮箱直接在列表页文本中

COLLEGES = [
    # 林草学院、水土保持学院
    ("林草学院、水土保持学院", [
        ("师资队伍(院士)", "http://linxue.njfu.edu.cn/szdw/ys2/index.html"),
    ], "list"),

    # 材料科学与工程学院
    ("材料科学与工程学院", [
        ("全职教师", "http://wood.njfu.edu.cn/szdw/qzjs/index.html"),
    ], "list"),

    # 化学工程学院
    ("化学工程学院", [
        ("教授", "http://hg.njfu.edu.cn/szdw/js/index.html"),
        ("副教授", "http://hg.njfu.edu.cn/szdw/fjs/index.html"),
        ("讲师", "http://hg.njfu.edu.cn/szdw/js1335/index.html"),
        ("特聘教授", "http://hg.njfu.edu.cn/szdw/tpjs/index.html"),
        ("产业教授", "http://hg.njfu.edu.cn/szdw/cyjs/index.html"),
    ], "list"),

    # 机械电子工程学院
    ("机械电子工程学院", [
        ("教授", "http://jidian.njfu.edu.cn/szdw/js/index.html"),
        ("副教授", "http://jidian.njfu.edu.cn/szdw/fjs/index.html"),
        ("讲师", "http://jidian.njfu.edu.cn/szdw/js2617/index.html"),
        ("实验员系列", "http://jidian.njfu.edu.cn/szdw/syyxl/index.html"),
    ], "list"),

    # 土木工程学院
    ("土木工程学院", [
        ("全职教师", "https://tumu.njfu.edu.cn/1945/list.htm"),
    ], "list"),

    # 经济管理学院（特殊：邮箱在列表页直接显示）
    ("经济管理学院", [
        ("全职教师(内联邮箱)", "https://cem.njfu.edu.cn/qzjs/list.htm"),
    ], "inline"),

    # 人文社会科学学院
    ("人文社会科学学院", [
        ("全职教师", "http://renwen.njfu.edu.cn/szdwn/qzjs/index.html"),
    ], "list"),

    # 信息科学技术学院、人工智能学院
    ("信息科学技术学院、人工智能学院", [
        ("教授/研究员", "http://it.njfu.edu.cn/szll/js/index.html"),
        ("副教授", "http://it.njfu.edu.cn/szll/fjs/index.html"),
        ("讲师", "http://it.njfu.edu.cn/szll/js2594/index.html"),
    ], "list"),

    # 理学院
    ("理学院", [
        ("师资队伍", "https://cos.njfu.edu.cn/75/list.htm"),
    ], "list"),

    # 外国语学院
    ("外国语学院", [
        ("师资名录", "http://waiyuan.njfu.edu.cn/szdw/szml/index.html"),
    ], "list"),

    # 艺术设计学院
    ("艺术设计学院", [
        ("教师风采", "http://art.njfu.edu.cn/szdw/jsfc/index.html"),
    ], "list"),

    # 家居与工业设计学院
    ("家居与工业设计学院", [
        ("教授", "http://jiaju.njfu.edu.cn/xjdw/js6680/index.html"),
        ("副教授", "http://jiaju.njfu.edu.cn/xjdw/fjs6196/index.html"),
        ("讲师", "http://jiaju.njfu.edu.cn/xjdw/js3069/index.html"),
    ], "list"),

    # 轻工与食品学院
    ("轻工与食品学院", [
        ("制浆造纸工程系", "http://qg.njfu.edu.cn/szdw/zjzzgcx/index.html"),
        ("食品科学与工程系", "http://qg.njfu.edu.cn/szdw/spkxygcx/index.html"),
    ], "list"),

    # 汽车与交通工程学院
    ("汽车与交通工程学院", [
        ("教授", "http://jty.njfu.edu.cn/szdw/azc/js/index.html"),
        ("副教授", "http://jty.njfu.edu.cn/szdw/azc/fjs/index.html"),
    ], "list"),

    # 生命科学学院
    ("生命科学学院", [
        ("师资队伍", "https://sky.njfu.edu.cn/szdw/index.html"),
    ], "list"),

    # 体育美育部
    ("体育美育部、体育运动中心", [
        ("师资队伍", "http://tyb.njfu.edu.cn/szdw/index.html"),
    ], "list"),
]


def is_teacher_name(text):
    """验证是否为合法的教师姓名"""
    text = text.strip()
    if not re.match(r'^[一-鿿]{2,4}$', text):
        return False
    if any(kw in text for kw in NAV_KW):
        return False
    return True


def extract_title(text):
    """从页面文本中提取职称"""
    found = []
    for kw in TITLE_KW:
        if kw in text:
            found.append(kw)
    return '、'.join(found[:3]) if found else ''


def restore_email(text):
    """反爬邮箱恢复"""
    text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\[\]\s*', '@', text)
    text = re.sub(r'#@', '@', text)
    text = re.sub(r'\[@\]', '@', text)
    text = re.sub(r'\(@\)', '@', text)
    return text


async def crawl_list_page(context, college_name, sub_name, url, url_type):
    """
    爬取单个教师列表页
    url_type: 'list' 标准模式，inline 内联邮箱模式
    """
    page = await context.new_page()
    results = []
    seen_urls = set()

    try:
        print(f"  [访问] {college_name} - {sub_name}: {url}")
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        if url_type == 'inline':
            # 内联邮箱模式：邮箱在列表页正文中直接显示
            body_text = await page.evaluate('() => document.body.innerText')
            lines = [l.strip() for l in body_text.split('\n') if l.strip()]

            current_name = None
            for i, line in enumerate(lines):
                # 尝试匹配教师姓名
                if is_teacher_name(line):
                    current_name = line
                # 提取邮箱
                restored = restore_email(line)
                emails = EMAIL_RE.findall(restored)
                if emails and current_name:
                    # 前一行可能有职称/系信息
                    dept_info = ""
                    if i >= 1:
                        dept_info = lines[i - 1] if i - 1 >= 0 else ""
                    title = extract_title(dept_info + line)
                    email = emails[0].lower()

                    # 过滤公共邮箱
                    public_prefixes = ['webmaster', 'admin', 'office', 'info', 'master',
                                       'root', 'postmaster', 'bgs', 'dangzheng', 'yuanban',
                                       'dangban', 'renshi', 'jiaowu', 'xuegong', 'tuanwei',
                                       'yanjiusheng']
                    email_prefix = email.split('@')[0]
                    if any(email_prefix == p or email_prefix.startswith(p) for p in public_prefixes):
                        current_name = None
                        continue

                    if email not in seen_urls:
                        seen_urls.add(email)
                        results.append({
                            'name': current_name,
                            'email': email,
                            'department': college_name,
                            'title': title,
                            'url': url
                        })
                    current_name = None

        else:
            # 标准模式：从<a>标签提取教师名+详情页链接
            raw_entries = await page.evaluate('''() => {
                const r = [];
                document.querySelectorAll('a').forEach(a => {
                    const text = a.textContent.trim();
                    if (a.href && text) {
                        r.push({name: text, url: a.href});
                    }
                });
                return r;
            }''')

            # 过滤：只保留2-4汉字姓名 + 排除导航关键词
            teacher_entries = []
            for entry in raw_entries:
                name = entry['name'].strip()
                href = entry['url'].strip()
                if not is_teacher_name(name):
                    continue
                # 排除导航类URL
                if any(href.endswith(s) for s in ['index.html', 'list.htm', 'main.htm']):
                    continue
                if '#' in href:
                    continue
                if any(kw in href for kw in ['list.htm', 'index.html', 'main.htm', 'list.htm']):
                    continue
                teacher_entries.append({'name': name, 'url': href})

            # 按URL去重
            seen = set()
            unique_entries = []
            for e in teacher_entries:
                if e['url'] not in seen:
                    seen.add(e['url'])
                    unique_entries.append(e)

            print(f"    → 找到 {len(unique_entries)} 个教师链接")

            # 进入每个教师详情页提取邮箱
            for entry in unique_entries:
                try:
                    detail_page = await context.new_page()
                    await detail_page.goto(entry['url'], wait_until='domcontentloaded', timeout=15000)
                    await asyncio.sleep(1)

                    body_text = await detail_page.evaluate('() => document.body.innerText')
                    restored = restore_email(body_text)
                    emails = EMAIL_RE.findall(restored)

                    title = extract_title(body_text)

                    if emails:
                        email = emails[0].lower()
                        # 过滤公共邮箱
                        public_prefixes = ['webmaster', 'admin', 'office', 'info', 'master']
                        email_prefix = email.split('@')[0]
                        if not any(email_prefix == p or email_prefix.startswith(p) for p in public_prefixes):
                            results.append({
                                'name': entry['name'],
                                'email': email,
                                'department': college_name,
                                'title': title,
                                'url': entry['url']
                            })
                    else:
                        # 无邮箱也保留记录
                        results.append({
                            'name': entry['name'],
                            'email': '',
                            'department': college_name,
                            'title': title,
                            'url': entry['url']
                        })

                    await detail_page.close()

                except Exception as e:
                    # 单个教师失败不影响整体
                    pass

    except Exception as e:
        print(f"  [失败] {college_name} - {sub_name}: {e}")
    finally:
        await page.close()

    return results


async def main():
    all_results = []
    stats = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
        )

        # 分批并行：每批3个学院
        batch_size = 3
        for i in range(0, len(COLLEGES), batch_size):
            batch = COLLEGES[i:i + batch_size]
            tasks = []
            for college_name, url_list, url_type in batch:
                for sub_name, url in url_list:
                    tasks.append(crawl_list_page(context, college_name, sub_name, url, url_type))

            batch_results = await asyncio.gather(*tasks)
            for dept_results in batch_results:
                all_results.extend(dept_results)

        await browser.close()

    # 统计
    for r in all_results:
        dept = r['department']
        if dept not in stats:
            stats[dept] = {'total': 0, 'with_email': 0}
        stats[dept]['total'] += 1
        if r['email']:
            stats[dept]['with_email'] += 1

    print("\n\n========== 爬取结果统计 ==========")
    total_with_email = sum(1 for r in all_results if r['email'])
    print(f"总记录: {len(all_results)}, 含邮箱: {total_with_email}")
    for dept, s in sorted(stats.items()):
        rate = s['with_email'] / s['total'] * 100 if s['total'] > 0 else 0
        print(f"  {dept}: {s['total']}人, {s['with_email']}邮箱 ({rate:.0f}%)")

    # 写入CSV
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / "南京林业大学_教师邮箱_V1.0.0.csv"
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['序号', '姓名', '邮箱', '学院', '职称', '主页链接'])
        for idx, r in enumerate(all_results, 1):
            writer.writerow([idx, r['name'], r['email'], r['department'], r['title'], r['url']])

    print(f"\n✅ CSV 已保存: {csv_path}")
    return csv_path


if __name__ == '__main__':
    asyncio.run(main())
