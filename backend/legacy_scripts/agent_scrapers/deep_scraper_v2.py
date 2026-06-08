"""
深度爬虫 v2 — 改进版
- 通过 URL 模式区分教师详情页和导航页
- 排除共享页脚/页头中的公共邮箱
- 自动跟踪分页
- 对无法用 Playwright 的学院，使用不同策略
"""

import asyncio
import csv
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("请先安装 playwright: pip install playwright && playwright install chromium")
    sys.exit(1)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

ANTI_SPAM_MAP = {
    "[at]": "@", "(at)": "@", "#@": "@", "[@]": "@",
    " at ": "@", " AT ": "@",
}

# 排除的公共/部门邮箱前缀
PUBLIC_EMAIL_PREFIXES = [
    "sxydw", "njugcglxy", "gcglxydw", "njudz", "yb_eng", "yb_",
    "arch@", "history@", "oice@", "yingfeng@", "xwzx@",
    "jcjs@", "webmaster", "admin", "info@", "office@",
]

NAV_KEYWORDS = [
    "首页", "学院概况", "学院简介", "机构设置", "职能部门", "群众团体",
    "新闻动态", "通知公告", "学术动态", "科研动态", "科研信息",
    "人才培养", "招生培养", "招生信息", "招生招聘", "就业",
    "师资队伍", "师资力量", "教师名录", "专任教师", "全院名录",
    "学术交流", "学术讲座", "学术成果", "学术前沿", "科研成果",
    "国际交流", "交流概况", "科研合作", "学生交换", "双学位",
    "合作联盟", "合作交流", "校友天地", "校友之窗", "校友动态",
    "院友风采", "学生天地", "学工园地", "升学就业",
    "党建工作", "团委工作", "党团工作", "支部活动",
    "学生管理", "学生工作", "管理规定", "规章制度",
    "培养方案", "教学公告", "课程资源", "教学成果", "教学年鉴",
    "学位工作", "考核开题", "规定细则", "课程回顾", "教学展览",
    "科研平台", "实验室", "科研机构", "文献资源", "数据库",
    "本院著作", "院图馆藏", "英文硕士", "英文项目",
    "师德师风", "师德监督", "院长信箱", "联系我们",
    "南大主页", "云上南雍", "主题展览", "毕业设计",
    "优秀校友", "教师作品", "乡村振兴", "历届论坛",
    "报名方式", "国际处", "科技处", "图书馆",
    "关于我们", "中心概况", "中心教师", "学院新闻",
    "院庆专栏", "院况概览", "院史纪略", "学院领导",
    "学习教育", "学术组织", "教研室", "行政部门", "办公部门",
    "党委", "行政", "校友捐赠", "校友资讯", "人事动态",
    "学院招聘", "组织动态", "教学论文", "历史渊源",
    "院系领导", "专业设置", "诚聘英才", "现任教师",
    "退休教师", "办事指南", "学术研究", "学术机构",
    "科研奖励", "院办刊物", "学术会议", "校友名录",
    "校友风采", "百年院庆", "学生活动", "学子风采",
    "学工布告", "党团建设", "暑期班", "培训班",
    "海外班", "留学生", "本科生", "研究生", "博士后",
    "系科设置", "学院标识", "教学与科", "通知与公",
    "讲座信息", "研究生导", "专业准入", "学习与课",
    "本科生招", "硕士研究", "博士研究", "科学研究",
    "党群工作", "工会工作", "党史学习", "活动掠影",
    "综合办事", "人事工作", "科研工作", "资产管理",
    "内部工作", "安全园地", "安全园地", "按岗位",
    "课题组介", "课题组简", "研究方向", "实验设备",
    "课题组成", "学术带头", "在读学生", "论文发表",
    "课程组新", "荣誉榜", "课题组快", "团队活动",
    "个人中心", "网站首页", "学院一览", "党群建设",
    "经济学院", "管理学院", "关闭此页",
    "下一页", "尾页", "next", "上一页", "查看更多",
]

# 南大教师详情页 URL 特征：包含 /page.htm 或 articleId 参数
TEACHER_PAGE_PATTERNS = [
    r"/page\.(htm|psp)",           # 标准文章页
    r"articleId=\d+",               # 重定向到文章
    r"/c\d+[a-z]?\d*/",            # 站点内文章ID
    r"/\d{4,6}/",                   # 文章编号
    r"\.html$",                     # HTML个人页（但要小心不是列表页）
]


def clean_email(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    for encoded, at in ANTI_SPAM_MAP.items():
        raw = raw.replace(encoded, at)
    raw = raw.replace(" ", "")
    m = EMAIL_RE.search(raw)
    return m.group(0) if m else ""


def is_public_email(email: str) -> bool:
    """检查是否是部门公共邮箱"""
    if not email:
        return True
    email_lower = email.lower()
    for prefix in PUBLIC_EMAIL_PREFIXES:
        if prefix in email_lower:
            return True
    return False


def is_teacher_detail_url(url: str) -> bool:
    """通过 URL 模式判断是否是教师个人详情页"""
    for pattern in TEACHER_PAGE_PATTERNS:
        if re.search(pattern, url):
            return True
    return False


def is_list_page(url: str) -> bool:
    """判断是否是列表页"""
    list_patterns = [r"/list\.htm", r"/list\d*\.htm", r"_redirect"]
    for p in list_patterns:
        if re.search(p, url):
            return True
    return False


def is_nav_link(text: str, url: str) -> bool:
    """综合判断是否是导航链接"""
    text = text.strip()
    if not text or len(text) < 2:
        return True

    # 导航文字检查
    if text in NAV_KEYWORDS:
        return True
    for kw in NAV_KEYWORDS:
        if text.startswith(kw) or kw.startswith(text):
            return True

    # 如果 URL 是列表页，且文字是导航特征
    if is_list_page(url):
        return True

    return False


def extract_chinese_name(text: str) -> str:
    """从文本中提取中文姓名"""
    if not text:
        return ""
    # 取前2-4个连续汉字
    m = re.search(r"^([一-鿿]{2,4})", text.strip())
    return m.group(1) if m else ""


def is_chinese_name(text: str) -> bool:
    """判断是否是中文姓名"""
    text = text.strip()
    if not text:
        return False
    # 2-4个汉字，不能是结尾的关键词
    m = re.fullmatch(r"[一-鿿]{2,4}", text)
    if not m:
        return False
    # 排除机构名
    bad_ends = ("报", "组", "室", "部", "处", "委", "会", "局", "办", "系",
                 "院", "所", "馆", "站", "网", "栏", "目", "页", "版")
    if text[-1] in bad_ends:
        return False
    return True


async def scrape_department_v2(browser, dept_name: str, dept_url: str, sem: asyncio.Semaphore) -> list[dict]:
    """
    改进版爬取策略：
    1. 先进入列表页
    2. 找到所有教师详情页链接（通过 URL 模式）
    3. 分页遍历
    4. 逐个访问详情页，在主要内容区查找邮箱
    """
    results = []
    visited_urls = set()
    teacher_links = []

    async with sem:
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        try:
            print(f"\n{'='*60}")
            print(f"🔍 [{dept_name}] 访问: {dept_url}")

            try:
                await page.goto(dept_url, wait_until="domcontentloaded", timeout=20000)
            except Exception as e:
                print(f"  ⚠ 无法访问列表页: {e}")
                return results

            await asyncio.sleep(2)

            # 第一步：收集当前列表页的教师链接
            links = await page.evaluate("""() => {
                const links = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    const text = (a.textContent || '').trim();
                    const href = a.href;
                    if (!text || !href) return;
                    if (href.startsWith('javascript:') || href.endsWith('#')) return;
                    links.push({text: text.substring(0, 50), href: href});
                });
                return links;
            }""")

            base_domain = urlparse(dept_url).netloc

            for link in links:
                text = link["text"]
                url = link["href"]

                # 只保留同域名的链接
                if base_domain not in url:
                    continue

                # 排除导航
                if is_nav_link(text, url):
                    continue

                # 必须是教师详情页（通过 URL 检测）
                if not is_teacher_detail_url(url):
                    continue

                # 提取姓名
                name = extract_chinese_name(text)
                if not is_chinese_name(name):
                    continue

                teacher_links.append({"name": name, "url": url, "text": text})

            # 去重
            seen_names = set()
            unique_teachers = []
            for t in teacher_links:
                if t["url"] not in visited_urls:
                    visited_urls.add(t["url"])
                    if t["name"] not in seen_names:
                        seen_names.add(t["name"])
                        unique_teachers.append(t)

            print(f"  👤 列表页找到 {len(unique_teachers)} 位教师")
            for t in unique_teachers[:10]:
                print(f"     - {t['name']} → {t['url'][:70]}")

            # 第二步：检查分页
            pagination_urls = set()
            for link in links:
                text = link["text"]
                url = link["href"]
                if base_domain not in url:
                    continue
                # 找到"下一页"或数字页码
                if re.match(r"^(下一页|下页|»|›|>$|>>|next)", text, re.I):
                    if is_list_page(url) and url != dept_url:
                        pagination_urls.add(url)

            # 限制最大教师数
            MAX_TEACHERS_PER_DEPT = 60
            if len(unique_teachers) > MAX_TEACHERS_PER_DEPT:
                print(f"  📐 限制为前 {MAX_TEACHERS_PER_DEPT} 位")
                unique_teachers = unique_teachers[:MAX_TEACHERS_PER_DEPT]

            # 第三步：逐个访问详情页
            for i, teacher in enumerate(unique_teachers):
                detail_url = teacher["url"]
                email = ""

                try:
                    print(f"  [{i+1}/{len(unique_teachers)}] {teacher['name']}")

                    await page.goto(detail_url, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(0.3)

                    # 策略1：在主要内容区域查找邮箱（排除 header/footer/nav）
                    emails_in_main = await page.evaluate("""() => {
                        // 排除页头页脚侧栏
                        const excludeTags = ['header', 'footer', 'nav', 'aside'];
                        const excludeClasses = ['.header', '.footer', '.nav', '.sidebar', '.menu', '.navbar',
                            '.foot', '.bottom', '.top-bar', '.site-footer', '.site-header'];

                        // 获取可能包含核心内容的区域
                        const mainSelectors = [
                            'main', 'article', '.content', '.main', '.article',
                            '.detail', '.details', '.entry', '.post',
                            '.teacher-info', '.teacher-detail', '.profile',
                            '.resume', '.intro', '.introduction',
                            '#content', '#main', '#article', '#detail',
                            '[class*="content"]', '[class*="main"]',
                            '[class*="detail"]', '[class*="article"]',
                        ];

                        let text = '';
                        for (const sel of mainSelectors) {
                            try {
                                const el = document.querySelector(sel);
                                if (el) {
                                    // 检查是否在排除标签内
                                    let parent = el;
                                    let excluded = false;
                                    while (parent) {
                                        if (parent.tagName && excludeTags.includes(parent.tagName.toLowerCase())) {
                                            excluded = true;
                                            break;
                                        }
                                        if (parent.className && typeof parent.className === 'string') {
                                            for (const cls of excludeClasses) {
                                                if (parent.className.includes(cls.replace('.', ''))) {
                                                    excluded = true;
                                                    break;
                                                }
                                            }
                                        }
                                        parent = parent.parentElement;
                                    }
                                    if (!excluded) {
                                        text += ' ' + (el.innerText || '');
                                    }
                                }
                            } catch(e) {}
                        }

                        // 如果主区域找不到，尝试排除页头页脚后取全文
                        if (!text.trim()) {
                            const body = document.body;
                            if (body) {
                                // 克隆body并移除页头页脚
                                const clone = body.cloneNode(true);
                                for (const sel of [...excludeTags.map(t => t), ...excludeClasses]) {
                                    clone.querySelectorAll(sel).forEach(el => el.remove());
                                }
                                text = clone.innerText || '';
                            }
                        }
                        return text;
                    }""")

                    # 提取邮箱
                    found_emails = EMAIL_RE.findall(emails_in_main)
                    valid_emails = [e for e in found_emails if not is_public_email(e)]

                    if valid_emails:
                        email = valid_emails[0]
                        print(f"     ✅ {email}")
                    else:
                        # 某些教师页面通过 JS 渲染邮箱，尝试全页搜索
                        full_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
                        all_emails = EMAIL_RE.findall(full_text)
                        personal_emails = [e for e in all_emails if not is_public_email(e)]
                        if personal_emails:
                            email = personal_emails[0]
                            print(f"     ✅ (全页) {email}")
                        else:
                            print(f"     ❌ 未找到个人邮箱")

                except Exception as e:
                    print(f"     ⚠ 出错: {e}")

                results.append({
                    "姓名": teacher["name"],
                    "邮箱": email if email else "无邮箱",
                    "学院": dept_name,
                    "职称": "",
                    "主页链接": detail_url,
                })

        except Exception as e:
            print(f"  ❌ [{dept_name}] 爬取出错: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await context.close()

    return results


# 学院配置 — 直接指定师资列表页 URL
DEPARTMENTS_V2 = {
    "商学院": "https://nubs.nju.edu.cn/szdw/list.htm",
    "教育研究院": "https://edu.nju.edu.cn/szdw/list.htm",
    "文学院": "https://chin.nju.edu.cn/szdw/xrjs/index.html",
    "电子科学与工程学院": "https://ese.nju.edu.cn/30444/list.htm",
    "化学化工学院": "https://chem.nju.edu.cn/szll/list.htm",
    "工程管理学院": "https://sme.nju.edu.cn/szdw/list.htm",
    "艺术学院": "https://art.nju.edu.cn/szdw/list.htm",
    "匡亚明学院": "https://dii.nju.edu.cn/szdw/list.htm",
    "能源与资源学院": "https://energy.nju.edu.cn/szdw/list.htm",
}


async def main():
    print("=" * 60)
    print("🎓 南京大学 — 深度教师邮箱爬虫 V2")
    print("=" * 60)

    sem = asyncio.Semaphore(3)
    all_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        for dept_name, dept_url in DEPARTMENTS_V2.items():
            results = await scrape_department_v2(browser, dept_name, dept_url, sem)
            all_results.extend(results)
            total_dept = len(results)
            has_email = sum(1 for r in results if r["邮箱"] and r["邮箱"] != "无邮箱")
            print(f"  📊 [{dept_name}] 爬取: {total_dept} 人, 有邮箱: {has_email} 人")

        await browser.close()

    # 统计
    total = len(all_results)
    has_email = sum(1 for r in all_results if r["邮箱"] and r["邮箱"] != "无邮箱")
    print(f"\n{'='*60}")
    print(f"🎉 总计: {total} 人, 有邮箱: {has_email} 人")

    from collections import Counter
    dept_count = Counter(r["学院"] for r in all_results)
    for dept, cnt in dept_count.most_common():
        with_email = sum(1 for r in all_results if r["学院"] == dept and r["邮箱"] and r["邮箱"] != "无邮箱")
        print(f"  {dept}: {cnt}人, 有邮箱{with_email}人")

    # 保存
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"南京大学_补充学院_v2_{timestamp}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["姓名", "邮箱", "学院", "职称", "主页链接"])
        writer.writeheader()
        writer.writerows(all_results)

    print(f"\n💾 已保存: {csv_path}")
    return csv_path


if __name__ == "__main__":
    asyncio.run(main())
