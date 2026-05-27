"""
V2 针对性爬虫 — 改进邮箱提取 + 正确处理学院页面结构
"""
import asyncio
import csv
import re
import os
from datetime import datetime
from collections import defaultdict
from playwright.async_api import async_playwright

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

# 公共邮箱黑名单
PUBLIC_EMAILS = {
    'webmaster@nju.edu.cn', 'admin@nju.edu.cn', 'info@nju.edu.cn',
    'wxyxz@nju.edu.cn', 'xwcb@nju.edu.cn', 'xgdw@nju.edu.cn',
    'history@nju.edu.cn', 'imnju@nju.edu.cn', 'sxydw@nju.edu.cn',
    'office@nju.edu.cn', 'mail@nju.edu.cn', 'service@nju.edu.cn',
    'xxgk@dicp.ac.cn', 'njugxy@163.com', 'job_eng@nju.edu.cn',
    'zhongf@nju.edu.cn',
}

# 个人邮箱黑名单（这些是在多个教师页面上重复出现的非个人邮箱）
DUPLICATE_BLACKLIST = {
    'zhanghao@nju.edu.cn',   # 电子学院管理员
    'fxshen@nju.edu.cn',     # 电子学院管理员
    'wangyuxuan@nju.edu.cn',  # 电子学院管理员
    'malab@nju.edu.cn',      # 实验室邮箱
    'wanghui@nju.edu.cn',    # 行政邮箱
}

def is_valid_personal_email(email):
    """检查是否为有效的个人邮箱"""
    email = email.strip().lower()
    if email in PUBLIC_EMAILS or email in DUPLICATE_BLACKLIST:
        return False
    # 排除明显的公共邮箱前缀
    public_prefixes = ['webmaster', 'admin', 'info', 'office', 'mail', 'service', 'postmaster']
    for prefix in public_prefixes:
        if email.startswith(prefix + '@'):
            return False
    return True


def extract_personal_email(page_text):
    """从页面文本中提取个人邮箱（优先匹配邮箱标签附近的邮箱）"""
    # 策略1: 查找「电子邮箱」「邮箱」「E-mail」等标签后的邮箱
    email_patterns = [
        r'电子邮箱[：:]\s*[\[【]?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
        r'邮箱[：:]\s*[\[【]?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
        r'E-?mail[：:]\s*[\[【]?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
        r'电子邮件[：:]\s*[\[【]?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
        r'联系邮箱[：:]\s*[\[【]?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
    ]

    for pat in email_patterns:
        m = re.search(pat, page_text, re.IGNORECASE)
        if m:
            email = m.group(1).strip().lower()
            if is_valid_personal_email(email):
                return email

    # 策略2: 恢复反爬邮箱后，查找所有邮箱，选第一个非公共的
    text = re.sub(r'\[at\]|\(at\)|#@|\[@\]', '@', page_text, flags=re.IGNORECASE)
    text = re.sub(r'\s*@\s*', '@', text)
    all_emails = EMAIL_RE.findall(text)
    for email in all_emails:
        if is_valid_personal_email(email):
            return email.lower()

    return ""


def extract_title(page_text):
    """提取职称"""
    titles = ['教授', '副教授', '助理教授', '讲师', '助教', '研究员',
              '副研究员', '助理研究员', '院士', '博导', '长江学者',
              '杰出青年', '青年学者', '长聘教授', '准聘教授', '准聘副教授',
              '准聘助理教授', '荣休教授']
    for t in titles:
        if t in page_text[:3000]:
            return t
    return ""


async def scrape_list_page(page, list_url, college_name):
    """从列表页收集教师链接"""
    print(f"  加载列表页: {list_url}")
    try:
        await page.goto(list_url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)
    except Exception as e:
        print(f"  ✗ 加载失败: {e}")
        return []

    # 首先获取所有链接
    links = await page.evaluate("""() => {
        const links = document.querySelectorAll('a[href]');
        return Array.from(links).map(a => ({
            text: (a.textContent || '').trim().replace(/\\s+/g, ' '),
            href: a.href,
            className: a.className || '',
            parentText: (a.parentElement?.textContent || '').trim().substring(0, 100)
        }));
    }""")

    # 过滤教师链接
    teacher_links = []
    seen = set()

    for link in links:
        text = link["text"]
        href = link["href"]
        parent = link["parentText"]

        # 跳过非教师链接
        if not text or len(text) > 20:
            continue

        # 导航关键词
        nav_words = ['首页', '概况', '简介', '通知', '公告', '新闻', '动态',
                     '招生', '培养', '科研', '学术', '党建', '工会', '校友',
                     '捐赠', '联系', '下载', '服务', '管理', '系统', '登录',
                     '注册', '关于', '返回', '主办', '承办', '地址', '电话',
                     '传真', '邮编', '友情', '快速', '专题', '栏目', '导航',
                     '关闭', '个人中心', '教学', '研究', '学工', '办事', '安全',
                     '人才', '诚聘', '专业', '课程', '就业', '创业', '国际',
                     '党团', '团委', '师资队伍', '教师名录', 'Chemical', 'English',
                     '南大概况', '南大', '工作动态', '事项提醒', '培训', '社会',
                     '首页信息', '国家', '校', '系', '院', '部', '处',
                     '专业设置', '研究方向', '学位', '委员会', '组织机构',
                     '科学', '实验室', '平台', '基地', '中心项目',
                     '硕士', '博士', '本科', '研究生', '学生', '证书',
                     '职业', '发展', '似水', '流年', '历届', '论坛',
                     '确认提交', '在线', '预约', '规章制度', '师德师风',
                     '监督', '举报', '报名方式', '访问学者',
                     '成果', '获奖', '项目', '会议', '交流', '合作',
                     '英文', '部门架构', '关闭此页',
                     '按岗位', '按系部', '专任教师', '兼职教授',
                     '全院名录', '实验技术', '行政学工', '荣休教师',
                     '行政', '办公部门', '党群工作', '党建',
                     '学院介绍', '学科介绍', '历史沿革', '机构设置',
                     '院系领导', '学院领导', '系科设置',
                     '委员', '职责', '联系方式', '学院标识',
                     ]

        is_nav = False
        for nw in nav_words:
            if nw in text:
                is_nav = True
                break

        if is_nav:
            continue

        # 如果链接文本包含职称信息（如「张三 教授」），这是教师条目
        has_title_in_text = any(t in text for t in ['教授', '副教授', '讲师', '研究员', '院士', '助理教授'])

        # 检查是否是教师名（2-4个汉字）
        is_chinese_name = bool(re.match(r'^[一-鿿·]{2,4}$', text))

        # 检查父元素是否包含职称信息
        has_title_in_parent = any(t in parent for t in ['教授', '副教授', '讲师', '研究员', '院士'])

        if (is_chinese_name or has_title_in_text) and href not in seen:
            seen.add(href)
            teacher_links.append({"name": text, "href": href, "parent": parent})

    # 如果找到的太少，尝试更宽松的匹配
    if len(teacher_links) < 10:
        print(f"    第一轮只找到 {len(teacher_links)} 个，尝试宽松匹配...")
        for link in links:
            text = link["text"]
            href = link["href"]
            if not text or len(text) > 25 or len(text) < 2:
                continue
            if href in seen:
                continue
            # 检查是否包含中文字符且不是纯导航
            if re.search(r'[一-鿿]', text) and not any(nw in text for nw in nav_words):
                seen.add(href)
                teacher_links.append({"name": text, "href": href, "parent": link["parentText"]})

    return teacher_links


async def scrape_teacher_detail(page, teacher, college_name):
    """访问教师详情页提取信息"""
    tname = teacher["name"]
    thref = teacher["href"]

    try:
        await page.goto(thref, wait_until="networkidle", timeout=25000)
        await asyncio.sleep(0.8)

        page_text = await page.evaluate("() => document.body?.innerText || ''")

        if not page_text:
            return None

        email = extract_personal_email(page_text)
        title = extract_title(page_text)

        # 尝试从页面提取真实姓名
        name_from_page = ""
        name_pats = [
            r'姓名[：:]\s*([一-鿿·]{2,5})',
            r'教师姓名[：:]\s*([一-鿿·]{2,5})',
        ]
        for pat in name_pats:
            m = re.search(pat, page_text[:2000])
            if m:
                name_from_page = m.group(1)
                break

        final_name = name_from_page if name_from_page else tname

        return {
            "姓名": final_name,
            "邮箱": email,
            "学院": college_name,
            "职称": title,
            "主页链接": thref,
        }
    except Exception as e:
        return None


async def scrape_college(browser, config):
    """爬取单个学院"""
    name = config["name"]
    list_urls = config["list_urls"]

    print(f"\n{'='*60}")
    print(f"爬取: {name}")
    print(f"{'='*60}")

    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    page = await context.new_page()

    all_teacher_links = []
    seen = set()

    # 收集教师链接
    for list_url in list_urls:
        teacher_links = await scrape_list_page(page, list_url, name)
        new_count = 0
        for tl in teacher_links:
            if tl["href"] not in seen:
                seen.add(tl["href"])
                all_teacher_links.append(tl)
                new_count += 1
        print(f"  {list_url} → +{new_count} 教师")

    # 如果还不够，尝试探索导航菜单
    if len(all_teacher_links) < 20:
        print(f"  仅找到 {len(all_teacher_links)} 个教师，尝试探索导航...")
        try:
            await page.goto(list_urls[0], wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # 点击可能的师资子分类链接
            nav_links = await page.evaluate("""() => {
                const links = document.querySelectorAll('a[href]');
                return Array.from(links).map(a => ({
                    text: (a.textContent || '').trim(),
                    href: a.href
                }));
            }""")

            sub_pages = []
            for nl in nav_links:
                ntext = nl["text"]
                nhref = nl["href"]
                # 这些是可能的教师子分类
                if any(kw in ntext for kw in ['教授', '副教授', '讲师', '教师', '人员', '系', '所', '中心']):
                    if len(ntext) <= 15 and nhref not in seen:
                        sub_pages.append(nhref)

            for sub_url in sub_pages[:5]:
                sub_links = await scrape_list_page(page, sub_url, name)
                for sl in sub_links:
                    if sl["href"] not in seen:
                        seen.add(sl["href"])
                        all_teacher_links.append(sl)
        except Exception as e:
            print(f"  探索失败: {e}")

    print(f"\n  共找到 {len(all_teacher_links)} 个教师链接，开始逐个访问详情页...")

    # 逐个访问详情页
    results = []
    for i, teacher in enumerate(all_teacher_links):
        if (i + 1) % 10 == 0:
            print(f"  进度: {i+1}/{len(all_teacher_links)}")

        result = await scrape_teacher_detail(page, teacher, name)
        if result and result["邮箱"]:
            results.append(result)
            print(f"  ✓ [{i+1}] {result['姓名']} → {result['邮箱']}")
        elif result:
            print(f"  ✗ [{i+1}] {result['姓名']} 无邮箱")

    await context.close()
    print(f"\n  {name} 完成: {len(results)} 位教师有邮箱")
    return results


async def main():
    print("=" * 60)
    print("南京大学 V2 针对性爬虫")
    print("=" * 60)

    # 只针对第一轮效果不好的学院
    configs = [
        {
            "name": "化学化工学院",
            "list_urls": [
                "https://chem.nju.edu.cn/szll/list.htm",
                "https://chem.nju.edu.cn/szll/js/list.htm",
            ],
        },
        {
            "name": "地球科学与工程学院",
            "list_urls": [
                "https://es.nju.edu.cn/szdw/list.htm",
                "https://es.nju.edu.cn/25233/list.htm",
            ],
        },
        {
            "name": "现代工程与应用科学学院",
            "list_urls": [
                "https://eng.nju.edu.cn/qyml2/list.htm",
                "https://eng.nju.edu.cn/43272/list.htm",
            ],
        },
        {
            "name": "生命科学学院",
            "list_urls": [
                "https://life.nju.edu.cn/szdw/list.htm",
                "https://life.nju.edu.cn/js/list.htm",
            ],
        },
        {
            "name": "商学院",
            "list_urls": [
                "https://nubs.nju.edu.cn/8878/list.htm",
                "https://nubs.nju.edu.cn/szdw/list.htm",
            ],
        },
        {
            "name": "文学院",
            "list_urls": [
                "https://chin.nju.edu.cn/szdw/xrjs/zggdwx/index.html",
                "https://chin.nju.edu.cn/szdw/xrjs/xjyysx/index.html",
                "https://chin.nju.edu.cn/szdw/xrjs/index.html",
            ],
        },
        {
            "name": "历史学院",
            "list_urls": [
                "https://history.nju.edu.cn/28475/list.htm",
                "https://history.nju.edu.cn/szdw/list.htm",
            ],
        },
        {
            "name": "中美文化研究中心",
            "list_urls": [
                "https://hnc.nju.edu.cn/szll.htm",
            ],
        },
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        all_results = []

        for config in configs:
            results = await scrape_college(browser, config)
            all_results.extend(results)

        await browser.close()

    # 保存
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(OUTPUT_DIR, f"南京大学_定向补抓V2_{timestamp}.csv")

    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=["姓名", "邮箱", "学院", "职称", "主页链接"])
        writer.writeheader()
        for r in all_results:
            writer.writerow(r)

    # 统计
    from collections import Counter
    counts = Counter(r["学院"] for r in all_results)
    print(f"\n{'='*60}")
    print(f"全部完成！共 {len(all_results)} 条记录")
    print(f"已保存: {csv_path}")
    for college, count in counts.most_common():
        print(f"  {college}: {count} 人")


if __name__ == "__main__":
    asyncio.run(main())
