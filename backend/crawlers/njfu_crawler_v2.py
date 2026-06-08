"""
南京林业大学 (NJFU) 第二轮补充爬取
修复 main.htm 过滤问题 + 补充缺失学院
"""
import asyncio
import re
import csv
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path("outputs/9e689a19-b5ca-42bf-98bd-be621a7b951c")
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# 扩展的职称白名单
TITLE_KW = ['教授', '副教授', '助理教授', '讲师', '研究员', '副研究员', '助理研究员',
            '工程师', '高级工程师', '博导', '硕导', '院士', '实验师', '高级实验师']

# 导航关键词（用于过滤非教师条目）
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
    '学科带头人', '2025', '2026', '2024', '2023', '2022', '2021', '2020',
    '党政', '党校', '纪检', '统战', '品牌', '评优', '科技', '创新',
    '实践', '心理', '健康', '学风', '网上', '基金', '申报', '招聘',
    '校园', '院友', '行政', '实验', '设备', '仪器', '中心', '委员会', '秘书',
    '网站首页', '用户登陆', '用户登录', 'EN', '旧版', '版',
    '搜索结果', '诚邀加盟', '案例中心', '人文之星',
    '上一页', '下一页', '尾页', '跳转', '首　页', '首 页', '首页',
    '办公电话', '组织框架', '交流动态', '合作项目', '就业方向',
    '新媒集锦', '下载专区', '党建规章', '支部风采',
    '人事', '财务', '外事', '简报',
]


def is_teacher_name(text):
    """验证是否为合法的教师姓名 (2-4汉字, 不在导航黑名单中)"""
    text = text.strip()
    if not re.match(r'^[一-鿿]{2,4}$', text):
        return False
    if any(kw in text for kw in NAV_KW):
        return False
    return True


def extract_title(text):
    """从页面文本提取职称"""
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


async def crawl_standard(context, college_name, list_url, detail_url_filter=None):
    """
    标准模式：从列表页提取教师名+链接 -> 进入详情页找邮箱
    不再使用 URL endswith 过滤，而是检查 URL 是否指向非教师页
    """
    page = await context.new_page()
    results = []

    try:
        print(f"  [访问] {college_name}: {list_url}")
        await page.goto(list_url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        # 提取所有 2-4汉字 的链接
        raw = await page.evaluate('''() => {
            const r = [];
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                if (a.href && text) {
                    r.push({name: text, url: a.href});
                }
            });
            return r;
        }''')

        # 过滤出教师名
        entries = []
        visited_urls = set()
        for e in raw:
            name = e['name'].strip()
            url = e['url'].strip()
            if not is_teacher_name(name):
                continue
            # 排除 # 链接
            if '#' in url or 'javascript:' in url:
                continue
            # 排除纯导航URL（学院首页、列表页等）
            if url == list_url:
                continue
            if re.search(r'/(index|list|main)\.(html?|htm|psp)$', url) and 'main.htm' not in url:
                # 但保留 main.htm 的链接（很多学院教师详情页用 main.htm）
                continue
            # 去重
            if url not in visited_urls:
                visited_urls.add(url)
                entries.append({'name': name, 'url': url})

        print(f"    → 找到 {len(entries)} 个教师链接")

        # 进入每个教师详情页找邮箱
        for entry in entries:
            try:
                detail = await context.new_page()
                await detail.goto(entry['url'], wait_until='domcontentloaded', timeout=15000)
                await asyncio.sleep(1)

                body = await detail.evaluate('() => document.body.innerText')
                restored = restore_email(body)
                emails = EMAIL_RE.findall(restored)
                title = extract_title(body)

                # 清洗邮箱
                email = emails[0].lower() if emails else ''
                if email:
                    public_prefixes = ['webmaster', 'admin', 'office', 'info', 'master', 'root', 'postmaster']
                    prefix = email.split('@')[0]
                    if any(prefix == p or prefix.startswith(p) for p in public_prefixes):
                        email = ''

                results.append({
                    'name': entry['name'],
                    'email': email,
                    'department': college_name,
                    'title': title,
                    'url': entry['url']
                })

                await detail.close()
            except Exception:
                pass  # 单条失败不影响整体

    except Exception as e:
        print(f"  [失败] {college_name}: {e}")
    finally:
        await page.close()

    return results


async def crawl_renwen(context):
    """
    人文学院特殊处理：教师链接文本是"详情"而非姓名
    从页面结构中提取姓名（姓名和详情链接在同一条目中）
    """
    page = await context.new_page()
    results = []

    try:
        print(f"  [访问] 人文社会科学学院: http://renwen.njfu.edu.cn/szdwn/qzjs/index.html")
        await page.goto('http://renwen.njfu.edu.cn/szdwn/qzjs/index.html',
                        wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        # 尝试多种方式提取教师名和详情链接
        entries = await page.evaluate('''() => {
            const result = [];

            // 方式1: 找"详情"链接，看前面的兄弟元素或者父元素中是否包含教师姓名
            document.querySelectorAll('a').forEach(a => {
                if (a.textContent.trim() === '详情' && a.href) {
                    // 查找父级容器
                    let parent = a.parentElement;
                    let depth = 0;
                    while (parent && depth < 5) {
                        // 在父级容器中找2-4汉字的文本
                        const text = parent.textContent.trim();
                        const nameMatch = text.match(/^[\\u4e00-\\u9fff]{2,4}/);
                        if (nameMatch) {
                            result.push({name: nameMatch[0], url: a.href});
                            return;
                        }
                        // 或者找前面的兄弟节点的文本
                        let prev = a.previousSibling;
                        while (prev) {
                            const pt = prev.textContent.trim();
                            if (pt && /^[\\u4e00-\\u9fff]{2,4}$/.test(pt)) {
                                result.push({name: pt, url: a.href});
                                return;
                            }
                            prev = prev.previousSibling;
                        }
                        parent = parent.parentElement;
                        depth++;
                    }
                }
            });

            // 方式2: 直接找div/span中的2-4汉字
            document.querySelectorAll('.teacher-name, .name, .teacher, td, li, div, span, p').forEach(el => {
                const text = el.textContent.trim();
                if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text)) {
                    // 找最近的链接
                    const link = el.closest('a') || el.querySelector('a');
                    if (link && link.href && !link.href.includes('#') && !link.href.includes('index.html')) {
                        const url = link.href;
                        if (!result.find(r => r.url === url)) {
                            result.push({name: text, url: url});
                        }
                    }
                }
            });

            return result;
        }''')

        seen_urls = set()
        unique = []
        for e in entries:
            if e['url'] not in seen_urls:
                seen_urls.add(e['url'])
                unique.append(e)

        print(f"    → 找到 {len(unique)} 个教师链接")

        for entry in unique:
            if not is_teacher_name(entry['name']):
                continue
            try:
                detail = await context.new_page()
                await detail.goto(entry['url'], wait_until='domcontentloaded', timeout=15000)
                await asyncio.sleep(1)

                body = await detail.evaluate('() => document.body.innerText')
                restored = restore_email(body)
                emails = EMAIL_RE.findall(restored)
                title = extract_title(body)

                email = emails[0].lower() if emails else ''
                if email:
                    public_prefixes = ['webmaster', 'admin', 'office', 'info', 'master']
                    prefix = email.split('@')[0]
                    if any(prefix == p or prefix.startswith(p) for p in public_prefixes):
                        email = ''

                results.append({
                    'name': entry['name'],
                    'email': email,
                    'department': '人文社会科学学院、生态文明传播学院',
                    'title': title,
                    'url': entry['url']
                })

                await detail.close()
            except Exception:
                pass

    except Exception as e:
        print(f"  [失败] 人文社会科学学院: {e}")
    finally:
        await page.close()

    return results


async def main():
    all_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )

        # 第二轮爬取的学院（修复了main.htm过滤问题 + 新增学院）
        colleges = [
            # 修复：土木工程学院 (教师URL是 main.htm)
            ("土木工程学院", [
                ("全职教师", "https://tumu.njfu.edu.cn/1945/list.htm"),
            ]),
            # 修复：理学院 (教师URL是 {pinyin}/main.htm)
            ("理学院", [
                ("师资队伍", "https://cos.njfu.edu.cn/75/list.htm"),
            ]),
            # 新增：信息学院副教授各子页
            ("信息科学技术学院、人工智能学院", [
                ("学科带头人", "http://it.njfu.edu.cn/szll/xkdtr/index.html"),
                ("兼职教授", "http://it.njfu.edu.cn/szll/jzjs/index.html"),
            ]),
            # 新增：家居学院所有子分类
            ("家居与工业设计学院", [
                ("师资队伍总页", "http://jiaju.njfu.edu.cn/xjdw/index.html"),
            ]),
            # 新增：交通学院讲师
            ("汽车与交通工程学院", [
                ("讲师", "http://jty.njfu.edu.cn/szdw/azc/js9802/index.html"),
            ]),
            # 新增：化学工程学院荣休教师
            ("化学工程学院", [
                ("荣休教师", "http://hg.njfu.edu.cn/szdw/txjs/index.html"),
            ]),
            # 新增：林草学院主师资页
            ("林草学院、水土保持学院", [
                ("师资队伍主页", "http://linxue.njfu.edu.cn/szdw/index.html"),
            ]),
            # 新增：材料学院实验中心队伍
            ("材料科学与工程学院", [
                ("实验中心队伍", "http://wood.njfu.edu.cn/sypt/syzxdw/index.html"),
            ]),
        ]

        # 先爬标准学院
        for college_name, url_list in colleges:
            for sub_name, url in url_list:
                task_results = await crawl_standard(context, college_name, url)
                all_results.extend(task_results)

        # 然后爬人文学院 (特殊处理)
        renwen_results = await crawl_renwen(context)
        all_results.extend(renwen_results)

        await browser.close()

    # 统计
    stats = {}
    for r in all_results:
        dept = r['department']
        if dept not in stats:
            stats[dept] = {'total': 0, 'with_email': 0}
        stats[dept]['total'] += 1
        if r['email']:
            stats[dept]['with_email'] += 1

    print("\n\n========== 第二轮补充爬取统计 ==========")
    total_email = sum(1 for r in all_results if r['email'])
    print(f"总记录: {len(all_results)}, 含邮箱: {total_email}")
    for dept, s in sorted(stats.items()):
        rate = s['with_email'] / s['total'] * 100 if s['total'] > 0 else 0
        print(f"  {dept}: {s['total']}人, {s['with_email']}邮箱 ({rate:.0f}%)")

    # 追加写入CSV
    csv_path = OUTPUT_DIR / "南京林业大学_教师邮箱_第二轮补充_V1.1.0.csv"
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['序号', '姓名', '邮箱', '学院', '职称', '主页链接'])
        for idx, r in enumerate(all_results, 1):
            writer.writerow([idx, r['name'], r['email'], r['department'], r['title'], r['url']])

    print(f"\n✅ CSV 已保存: {csv_path}")


if __name__ == '__main__':
    asyncio.run(main())
