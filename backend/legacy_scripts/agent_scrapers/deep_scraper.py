"""
深度爬虫 — 针对人数不足的学院，利用 Playwright 深入个人详情页提取教师邮箱。
支持两种策略：
  Strategy A: 从列表页逐个点击教师链接 → 详情页 → 提取邮箱 → 返回列表
  Strategy B: 如果列表页没有详情链接，尝试在页面中直接搜索邮箱正则
"""

import asyncio
import csv
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("请先安装 playwright: pip install playwright && playwright install chromium")
    sys.exit(1)

# ---------- 配置 ----------
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# 反爬恢复
ANTI_SPAM_MAP = {
    "[at]": "@", "(at)": "@", "#@": "@", "[@]": "@",
    " at ": "@", " AT ": "@", "[a]": "@", "(a)": "@",
}

# 导航特征词（不是教师姓名）
NAV_KEYWORDS = [
    "首页", "学院概况", "学院简介", "机构设置", "职能部门", "群众团体",
    "新闻动态", "通知公告", "学术动态", "科研动态", "科研信息",
    "人才培养", "招生培养", "招生信息", "招生招聘", "就业信息",
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
    "报名方式", "国际处", "科技处", "图书馆", "校史馆",
    "校园地图", "校园风光", "校园文化", "信息公开",
    "关于我们", "中心概况", "中心教师", "师资力量",
    "院庆专栏", "院况概览", "院史纪略", "学院领导",
    "学习教育", "学术组织", "教研室", "教师", "教授",
    "副教授", "讲师", "其他", "行政部门", "办公部门",
    "党委", "行政", "校友捐赠", "校友资讯", "人事动态",
    "学院招聘", "组织动态", "信息公开", "教学论文",
    "科研成果", "科研项目", "新闻中心", "学院新闻",
    "南京大学", "研究生院", "本科生院", "社会科学处",
    "人事处", "科学技术处", "国际合作与交流处",
]

# 典型导航词（短词，非人名）
NAV_SHORT = {
    "首页", "概况", "简介", "通知", "公告", "新闻", "动态",
    "招生", "培养", "就业", "联系", "关于", "下载", "链接",
    "专题", "专栏", "聚焦", "要闻", "信息", "服务", "平台",
    "网站", "导航", "搜索", "登录", "注册", "更多", "详情",
    "返回", "上一页", "下一页", "English", "中文", "EN",
}

# 学院 URL 列表 — 师资列表页
DEPARTMENTS = {
    "商学院": {
        "home": "https://nubs.nju.edu.cn/",
        "teacher_list": [
            "https://nubs.nju.edu.cn/szdw/list.htm",
            "https://nubs.nju.edu.cn/8478/list.htm",
        ],
    },
    "教育研究院": {
        "home": "https://edu.nju.edu.cn/",
        "teacher_list": [
            "https://edu.nju.edu.cn/szdw/list.htm",
            "https://edu.nju.edu.cn/jyjs/list.htm",
        ],
    },
    "文学院": {
        "home": "https://chin.nju.edu.cn/",
        "teacher_list": [
            "https://chin.nju.edu.cn/szdw/list.htm",
            "https://chin.nju.edu.cn/19953/list.htm",
        ],
    },
    "电子科学与工程学院": {
        "home": "https://ese.nju.edu.cn/",
        "teacher_list": [
            "https://ese.nju.edu.cn/30444/list.htm",
            "https://ese.nju.edu.cn/16777/list.htm",
        ],
    },
    "化学化工学院": {
        "home": "https://chem.nju.edu.cn/",
        "teacher_list": [
            "https://chem.nju.edu.cn/szll/list.htm",
            "https://chem.nju.edu.cn/12554/list.htm",
        ],
    },
    "匡亚明学院": {
        "home": "https://dii.nju.edu.cn/",
        "teacher_list": [
            "https://dii.nju.edu.cn/szdw/list.htm",
        ],
    },
    "工程管理学院": {
        "home": "https://sme.nju.edu.cn/",
        "teacher_list": [
            "https://sme.nju.edu.cn/szdw/list.htm",
        ],
    },
    "能源与资源学院": {
        "home": "https://energy.nju.edu.cn/",
        "teacher_list": [
            "https://energy.nju.edu.cn/szdw/list.htm",
        ],
    },
    "艺术学院": {
        "home": "https://art.nju.edu.cn/",
        "teacher_list": [
            "https://art.nju.edu.cn/szdw/list.htm",
        ],
    },
}


def clean_email(raw: str) -> str:
    """清理反爬保护后的邮箱"""
    if not raw:
        return ""
    raw = raw.strip()
    for encoded, at in ANTI_SPAM_MAP.items():
        raw = raw.replace(encoded, at)
    # 移除多余空格
    raw = raw.replace(" ", "")
    m = EMAIL_RE.search(raw)
    return m.group(0) if m else ""


def is_nav_text(text: str) -> bool:
    """判断文本是否是导航菜单项而非人名"""
    text = text.strip()
    if not text:
        return True
    # 太长的文本不太可能是导航
    if len(text) > 10:
        return False
    # 检查导航关键词
    if text in NAV_KEYWORDS:
        return True
    if text in NAV_SHORT:
        return True
    # 包含明显导航特征
    for kw in ["名单", "列表", "目录", "索引", "检索", "下载", "附件"]:
        if kw in text:
            return True
    return False


def is_staff_email(email: str) -> bool:
    """过滤学院公共邮箱"""
    if not email:
        return False
    staff_patterns = [
        "wxyxz", "xwcb", "webmaster", "admin", "postmaster",
        "office", "info", "master", "root", "service",
        "bgs", "dangzheng", "dangban", "jcjs", "yb_",
        "arch@", "history@", "oice@", "yingfeng@",
    ]
    email_lower = email.lower()
    for pat in staff_patterns:
        if pat in email_lower:
            return False
    return True


def extract_chinese_name(text: str) -> str:
    """从文本中提取中文姓名（2-4个汉字）"""
    if not text:
        return ""
    m = re.search(r"[一-鿿]{2,4}", text)
    return m.group(0) if m else ""


def extract_title(text: str) -> str:
    """从文本中提取职称"""
    titles = ["教授", "副教授", "讲师", "助教", "研究员", "副研究员",
              "院士", "博导", "硕导", "青年学者", "工程师", "高级工程师",
              "博士后", "助理教授", "助理研究员", "实验师"]
    found = []
    for t in titles:
        if t in text:
            found.append(t)
    return "、".join(found) if found else ""


def is_person_name(text: str) -> bool:
    """判断文本是否像人名"""
    text = text.strip()
    if not text:
        return False
    # 中文人名：2-4个汉字
    m = re.fullmatch(r"[一-鿿]{2,4}", text)
    if not m:
        return False
    # 过滤明显不是人名的
    if text.endswith(("报", "组", "室", "部", "处", "委", "会", "局", "办")):
        return False
    return True


async def try_find_teacher_list(page, dept_name: str) -> str:
    """在学院首页尝试找到师资列表页链接"""
    home_url = DEPARTMENTS[dept_name]["home"]

    # 师资相关的链接关键词
    teacher_link_patterns = [
        "师资队伍", "师资力量", "教师名录", "专任教师", "全院名录",
        "教师队伍", "教师列表", "师资", "人员组成", "教师", "教授",
        "faculty", "Faculty", "teachers", "staff",
    ]

    try:
        await page.goto(home_url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(1)

        # 获取所有链接
        links = await page.evaluate("""() => {
            const links = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const text = (a.textContent || '').trim();
                const href = a.href;
                if (text && href && !href.startsWith('javascript:') && !href.startsWith('#')) {
                    links.push({text: text, href: href});
                }
            });
            return links;
        }""")

        for link in links:
            for pattern in teacher_link_patterns:
                if pattern in link["text"]:
                    return link["href"]

    except Exception as e:
        print(f"  ⚠ 在首页查找师资链接失败: {e}")

    return ""


async def scrape_department(browser, dept_name: str, sem: asyncio.Semaphore) -> list[dict]:
    """爬取一个学院的所有教师信息"""
    results = []
    teacher_list_urls = DEPARTMENTS[dept_name]["teacher_list"]

    async with sem:
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        try:
            # 先尝试已有的列表 URL
            list_url = teacher_list_urls[0]
            print(f"\n{'='*60}")
            print(f"🔍 [{dept_name}] 尝试列表页: {list_url}")

            try:
                await page.goto(list_url, wait_until="domcontentloaded", timeout=20000)
            except Exception:
                # 如果第一个 URL 失败，尝试找师资链接
                found = await try_find_teacher_list(page, dept_name)
                if found:
                    list_url = found
                    print(f"  📍 找到师资页: {list_url}")
                    await page.goto(list_url, wait_until="domcontentloaded", timeout=20000)
                else:
                    # 尝试其他预设 URL
                    for alt_url in teacher_list_urls[1:]:
                        try:
                            await page.goto(alt_url, wait_until="domcontentloaded", timeout=15000)
                            list_url = alt_url
                            break
                        except Exception:
                            continue

            await asyncio.sleep(2)

            # 获取页面中所有链接，过滤出可能的教师条目
            candidate_links = await page.evaluate("""() => {
                const results = [];
                // 跳过导航区域（通常有 nav, header, menu 等标识）
                const skipSelectors = 'nav a, header a, .nav a, .menu a, .navbar a, .sidebar a, .footer a';
                const skipSet = new Set();
                document.querySelectorAll(skipSelectors).forEach(a => skipSet.add(a));

                document.querySelectorAll('a[href]').forEach(a => {
                    if (skipSet.has(a)) return;
                    const text = (a.textContent || '').trim();
                    const href = a.href;
                    if (!text || !href) return;
                    if (href.startsWith('javascript:') || href.startsWith('#')) return;
                    // 忽略图片链接（无文字）
                    if (text.length < 2 || text.length > 15) return;
                    // 跳转到外部网站
                    if (!href.includes(window.location.hostname) && href.startsWith('http')) return;
                    results.push({
                        text: text,
                        href: href,
                        tag: a.closest('li,td,div,p')?.tagName || '',
                    });
                });
                return results;
            }""")

            print(f"  📋 找到 {len(candidate_links)} 个候选链接")

            # 过滤: 保留看起来像人名的链接
            teacher_links = []
            for link in candidate_links:
                text = link["text"]
                if is_nav_text(text):
                    continue
                # 提取人名部分
                name = extract_chinese_name(text)
                if is_person_name(name):
                    title = extract_title(text)
                    teacher_links.append({
                        "name": name,
                        "title": title,
                        "url": link["href"],
                    })

            # 去重（同一个人可能出现在多个位置）
            seen = set()
            unique_teachers = []
            for t in teacher_links:
                key = t["name"] + t.get("title", "")
                if key not in seen:
                    seen.add(key)
                    unique_teachers.append(t)

            print(f"  👤 识别出 {len(unique_teachers)} 位可能的教师")
            for t in unique_teachers[:15]:
                print(f"     - {t['name']} ({t.get('title', '未知')}) → {t['url'][:60]}")

            if len(unique_teachers) > 50:
                print(f"  ⚠ 教师数量较多({len(unique_teachers)}人)，限制为前50人")
                unique_teachers = unique_teachers[:50]

            # 逐个进入详情页
            visited_detail = set()
            for i, teacher in enumerate(unique_teachers):
                detail_url = teacher["url"]
                if detail_url in visited_detail:
                    continue
                visited_detail.add(detail_url)

                email = ""
                try:
                    print(f"  [{i+1}/{len(unique_teachers)}] {teacher['name']} → {detail_url[:80]}")
                    await page.goto(detail_url, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(0.5)

                    # 获取页面全文
                    page_text = await page.evaluate("() => document.body.innerText || ''")

                    # 查找邮箱
                    emails = EMAIL_RE.findall(page_text)
                    # 过滤：保留看起来像个人邮箱的
                    valid_emails = [e for e in emails if is_staff_email(e)]

                    if valid_emails:
                        email = valid_emails[0]
                        print(f"     ✅ 邮箱: {email}")
                    else:
                        # 尝试在特定区域查找
                        contact_selectors = [
                            ".contact", ".email", ".mail", ".info",
                            "[class*=contact]", "[class*=email]", "[class*=info]",
                            ".teacher-info", ".profile", ".resume",
                        ]
                        for sel in contact_selectors:
                            try:
                                el_text = await page.evaluate(
                                    f"""(sel) => {{
                                        const el = document.querySelector(sel);
                                        return el ? el.innerText : '';
                                    }}""", sel
                                )
                                found = EMAIL_RE.findall(el_text)
                                valid_found = [e for e in found if is_staff_email(e)]
                                if valid_found:
                                    email = valid_found[0]
                                    print(f"     ✅ 邮箱(区域): {email}")
                                    break
                            except Exception:
                                pass

                    if not email:
                        print(f"     ❌ 未找到个人邮箱")

                except Exception as e:
                    print(f"     ⚠ 出错: {e}")

                results.append({
                    "姓名": teacher["name"],
                    "邮箱": email if email else "无邮箱",
                    "学院": dept_name,
                    "职称": teacher.get("title", ""),
                    "主页链接": detail_url,
                })

        except Exception as e:
            print(f"  ❌ [{dept_name}] 爬取出错: {e}")
            import traceback
            traceback.print_exc()

        finally:
            await context.close()

    return results


async def main():
    print("=" * 60)
    print("🎓 南京大学 — 深度教师邮箱爬虫")
    print("=" * 60)

    sem = asyncio.Semaphore(3)  # 并发限制

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        all_results = []
        dept_names = list(DEPARTMENTS.keys())

        # 逐个学院爬取（串行，避免反爬）
        for dept_name in dept_names:
            results = await scrape_department(browser, dept_name, sem)
            all_results.extend(results)
            print(f"\n  📊 [{dept_name}] 本次爬取: {len(results)} 位教师")

        await browser.close()

    # 统计
    total = len(all_results)
    has_email = sum(1 for r in all_results if r["邮箱"] and r["邮箱"] != "无邮箱")
    print(f"\n{'='*60}")
    print(f"🎉 总计爬取: {total} 位教师, 有邮箱: {has_email} 人")

    # 按学院统计
    from collections import Counter
    dept_count = Counter(r["学院"] for r in all_results)
    for dept, cnt in dept_count.most_common():
        with_email = sum(1 for r in all_results if r["学院"] == dept and r["邮箱"] and r["邮箱"] != "无邮箱")
        print(f"  {dept}: {cnt}人, 有邮箱{with_email}人")

    # 保存
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"南京大学_补充学院_{timestamp}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["姓名", "邮箱", "学院", "职称", "主页链接"])
        writer.writeheader()
        writer.writerows(all_results)

    print(f"\n💾 已保存: {csv_path}")
    return csv_path


if __name__ == "__main__":
    asyncio.run(main())
