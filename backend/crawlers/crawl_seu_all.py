#!/usr/bin/env python3
"""
东南大学全学院教师信息爬取脚本
基于 Playwright 并行爬取，使用知识库已验证的师资 URL
"""
import asyncio
import csv
import os
import re
import time
from datetime import datetime

from playwright.async_api import async_playwright

OUTPUT_DIR = "D:/Work/test/UniEmailAgent/backend/outputs/9782a4a5-306a-437a-bf49-4900674734ad"
TASK_ID = "9782a4a5-306a-437a-bf49-4900674734ad"

sem = asyncio.Semaphore(4)  # 同时爬 4 个学院

# 东南大学学院列表（含已验证的师资URL或可探索的主页）
COLLEGES = [
    # (学院名称, 主页URL, 已知师资列表URL列表（可空）)
    ("建筑学院", "https://arch.seu.edu.cn", [
    ]),
    ("机械工程学院", "https://me.seu.edu.cn", [
        "https://me.seu.edu.cn/szll/list.htm",
    ]),
    ("能源与环境学院", "https://power.seu.edu.cn", [
        "https://power.seu.edu.cn/9232/list.htm",
    ]),
    ("信息科学与工程学院", "https://radio.seu.edu.cn", [
        "https://radio.seu.edu.cn/19212/list.htm",
        "https://radio.seu.edu.cn/19256/list.htm",
    ]),
    ("土木工程学院", "https://civil.seu.edu.cn", [
        "https://civil.seu.edu.cn/zrjs/list.htm",
    ]),
    ("电子科学与工程学院", "https://electronic.seu.edu.cn", [
        "https://electronic.seu.edu.cn/11478/list.htm",
        "https://electronic.seu.edu.cn/szllx/list.htm",
    ]),
    ("数学学院", "https://math.seu.edu.cn", [
        "https://math.seu.edu.cn/szdw/list.htm",
    ]),
    ("自动化学院", "https://automation.seu.edu.cn", [
        "https://automation.seu.edu.cn/szdw_32667/list.htm",
    ]),
    ("计算机科学与工程学院", "https://cse.seu.edu.cn", [
        "https://cse.seu.edu.cn/49354/list.htm",
    ]),
    ("软件学院", "https://cose.seu.edu.cn", [
    ]),
    ("人工智能学院", "https://ai.seu.edu.cn", [
    ]),
    ("物理学院", "https://physics.seu.edu.cn", [
        "https://physics.seu.edu.cn/23137/list.htm",
    ]),
    ("生物科学与医学工程学院", "https://bme.seu.edu.cn", [
        "https://bme.seu.edu.cn/476/list.htm",
        "https://bme.seu.edu.cn/499/list.htm",
        "https://bme.seu.edu.cn/505/list.htm",
        "https://bme.seu.edu.cn/513/list.htm",
        "https://bme.seu.edu.cn/61856/list.htm",
        "https://bme.seu.edu.cn/61858/list.htm",
        "https://bme.seu.edu.cn/62489/list.htm",
    ]),
    ("材料科学与工程学院", "https://smse.seu.edu.cn", [
        "https://smse.seu.edu.cn/2580/list.htm",
    ]),
    ("人文学院", "https://rwxy.seu.edu.cn", [
    ]),
    ("经济管理学院", "https://em.seu.edu.cn", [
        "https://em.seu.edu.cn/57213/list.htm",
    ]),
    ("电气工程学院", "https://ee.seu.edu.cn", [
        "https://ee.seu.edu.cn/25248/list.htm",
        "https://ee.seu.edu.cn/szdw/list.htm",
    ]),
    ("外国语学院", "https://sfl.seu.edu.cn", [
        "https://sfl.seu.edu.cn/9851/list.htm",
    ]),
    ("艺术学院", "https://arts.seu.edu.cn", [
        "https://arts.seu.edu.cn/szdw_25730/list.htm",
    ]),
    ("法学院", "https://law.seu.edu.cn", [
        "https://law.seu.edu.cn/9121/list.htm",
        "https://law.seu.edu.cn/9125/list.htm",
    ]),
    ("医学院", "https://med.seu.edu.cn", [
        "https://med.seu.edu.cn/8693/list.htm",
    ]),
    ("公共卫生学院", "https://med.seu.edu.cn", [
    ]),
    ("吴健雄学院", "https://wjx.seu.edu.cn", [
    ]),
    ("网络空间安全学院", "https://cyber.seu.edu.cn", [
    ]),
    ("马克思主义学院", "https://marxism.seu.edu.cn", [
        "https://marxism.seu.edu.cn/23294/list.htm",
    ]),
    ("生命科学与技术学院", "https://ils.seu.edu.cn", [
        "https://ils.seu.edu.cn/22853/list.htm",
    ]),
    ("统计与数据科学学院", "https://stat.seu.edu.cn", [
        "https://stat.seu.edu.cn/62001/list.htm",
    ]),
    ("仪器科学与工程学院", "https://ins.seu.edu.cn", [
        "https://ins.seu.edu.cn/45076/list.htm",
        "https://ins.seu.edu.cn/zrjs/list.htm",
    ]),
    ("化学化工学院", "https://chem.seu.edu.cn", [
        "https://chem.seu.edu.cn/zmxz_34305/list.htm",
    ]),
    ("交通学院", "https://tc.seu.edu.cn", [
        "https://tc.seu.edu.cn/58255/list.htm",
    ]),
    ("集成电路学院", "https://ic.seu.edu.cn", [
        "https://ic.seu.edu.cn/47757/list.htm",
        "https://ic.seu.edu.cn/47772/list.htm",
        "https://ic.seu.edu.cn/55864/list.htm",
    ]),
    ("体育系", "https://tyx.seu.edu.cn", [
        "https://tyx.seu.edu.cn/2166/list.htm",
    ]),
    ("未来技术学院", "https://futuretech.seu.edu.cn", [
    ]),
    ("苏州校区", "https://szyjy.seu.edu.cn", [
        "https://szyjy.seu.edu.cn/szdw/list.htm",
    ]),
]

# 邮箱反爬恢复
def decode_email(text):
    if not text:
        return ""
    text = text.replace("[at]", "@").replace("(at)", "@")
    text = text.replace("(#)", "@").replace("[#]", "@")
    text = text.replace("[@]", "@").replace("(@)", "@")
    text = text.replace("#@", "@").replace(" # ", "@")
    # 移除空白
    text = text.strip()
    return text

def extract_emails(text):
    """从文本中提取邮箱地址"""
    if not text:
        return []
    # 先恢复反爬格式
    text = decode_email(text)
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return list(set(re.findall(pattern, text)))

# 公共邮箱前缀
PUBLIC_PREFIXES = [
    "webmaster", "admin", "office", "info", "master", "root",
    "postmaster", "wxyxz", "xwcb", "bgs", "dangzheng", "yuanban",
    "web", "support", "service", "contact",
]

def is_public_email(email):
    """检查是否为公共邮箱"""
    if not email:
        return True
    prefix = email.split("@")[0].lower()
    for p in PUBLIC_PREFIXES:
        if prefix == p or prefix.startswith(p):
            return True
    return False

def is_chinese_name(text):
    """判断是否为中文姓名（2-4个汉字）"""
    text = text.strip()
    # 去掉括号内容特殊情况
    cn_chars = re.findall(r'[一-鿿]', text)
    return 2 <= len(cn_chars) <= 6 and len(cn_chars) == len(text)

async def discover_teacher_list(page, college_home):
    """在学院主页上寻找师资队伍链接"""
    try:
        await page.goto(college_home, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        content = await page.content()

        # 查找常见师资关键词的链接
        keywords = ["师资队伍", "教师名录", "师资力量", "师资概况", "专任教师",
                     "在职教师", "全部教师", "全体教师", "教职员工"]
        links = []
        for kw in keywords:
            try:
                elements = await page.query_selector_all(f'a:has-text("{kw}")')
                for el in elements:
                    href = await el.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else \
                            college_home.rstrip("/") + "/" + href.lstrip("/")
                        links.append((kw, full_url))
            except:
                pass

        # 去重
        seen = set()
        unique_links = []
        for kw, url in links:
            if url not in seen:
                seen.add(url)
                unique_links.append((kw, url))

        return unique_links
    except Exception as e:
        print(f"  [发现] 主页探索失败: {e}")
        return []

async def extract_teacher_from_list(page, list_url, college_name):
    """从教师列表页提取教师姓名和详情页链接"""
    teachers = []
    try:
        print(f"  [列表] 访问: {list_url}")
        await page.goto(list_url, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # 获取所有链接
        links = await page.query_selector_all("a")
        for link in links:
            try:
                text = await link.inner_text()
                text = text.strip()
                href = await link.get_attribute("href")
                if not text or not href:
                    continue
                # 判断是否为中文姓名
                if not is_chinese_name(text):
                    continue
                # 排除导航类链接
                nav_keywords = ["首页", "学院概况", "通知公告", "联系我们", "师资队伍",
                                "科学研究", "人才培养", "学生工作", "党群工作", "校友",
                                "招聘", "下载", "登录", "注册", "搜索", "友情链接",
                                "管理入口", "院内文档", "相关链接", "学校首页", "系所",
                                "第一页", "尾页", "跳转", "教授", "副教授", "讲师",
                                "助教", "院士", "博士", "硕士", "学士", "工程师",
                                "概况", "系所", "动态", "教学", "科研", "服务",
                                "分享", "收藏", "院长信箱", "书记信箱"]
                skip = False
                for kw in nav_keywords:
                    if kw in text:
                        skip = True
                        break
                if skip:
                    continue

                # 构建完整URL
                if href.startswith("http"):
                    full_url = href
                elif href.startswith("/"):
                    # 从list_url提取基础域名
                    from urllib.parse import urlparse
                    parsed = urlparse(list_url)
                    full_url = f"{parsed.scheme}://{parsed.netloc}{href}"
                else:
                    full_url = list_url.rstrip("/") + "/" + href.lstrip("/")

                teachers.append((text, full_url))
            except:
                continue

        # 去重
        seen_names = set()
        unique_teachers = []
        for name, url in teachers:
            if name not in seen_names:
                seen_names.add(name)
                unique_teachers.append((name, url))

        print(f"  [列表] 找到 {len(unique_teachers)} 位教师")
        return unique_teachers
    except Exception as e:
        print(f"  [列表] 访问失败 {list_url}: {e}")
        return []

async def extract_teacher_detail(page, teacher_name, detail_url, college_name):
    """访问教师个人详情页，提取邮箱和职称"""
    result = {"name": teacher_name, "email": "", "title": "", "college": college_name, "url": detail_url}
    try:
        await page.goto(detail_url, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        content = await page.content()
        text_content = await page.evaluate("document.body.innerText")

        # 提取邮箱
        emails = extract_emails(text_content)
        personal_emails = [e for e in emails if not is_public_email(e)]
        # 优先 seu.edu.cn 邮箱
        seu_emails = [e for e in personal_emails if "seu.edu.cn" in e]
        if seu_emails:
            result["email"] = seu_emails[0]
        elif personal_emails:
            result["email"] = personal_emails[0]

        # 提取职称
        title_keywords = ["教授", "副教授", "讲师", "助教", "研究员", "副研究员",
                          "助理研究员", "高级工程师", "工程师", "助理工程师",
                          "博导", "硕导", "院士", "教授级高工", "实验师",
                          "高级实验师", "教授级高级工程师"]
        for kw in title_keywords:
            if kw in text_content:
                result["title"] = kw
                break

        # 如果页面标题包含职称
        title_tag = await page.title()
        for kw in title_keywords:
            if kw in title_tag:
                result["title"] = kw
                break

        return result
    except Exception as e:
        print(f"    [详情] 失败 {teacher_name}: {e}")
        return result

async def crawl_college(browser, college_name, homepage, known_urls):
    """爬取单个学院"""
    async with sem:
        print(f"\n{'='*50}")
        print(f"开始爬取: {college_name}")
        print(f"{'='*50}")

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        page = await context.new_page()

        all_teachers_data = []
        teacher_links = []  # (name, url)
        teacher_urls_tried = set()

        # 1. 尝试已知列表URL
        for url in known_urls:
            teachers = await extract_teacher_from_list(page, url, college_name)
            for name, url2 in teachers:
                if url2 not in teacher_urls_tried:
                    teacher_urls_tried.add(url2)
                    teacher_links.append((name, url2))

        # 2. 如果没有已知URL或找到太少，尝试探索主页
        if len(teacher_links) < 5:
            print(f"  [发现] 已知URL找到人数较少({len(teacher_links)})，尝试主页发现...")
            discovered = await discover_teacher_list(page, homepage)
            for kw, discovered_url in discovered:
                # 避免重复爬已知URL
                if discovered_url in known_urls:
                    continue
                teachers = await extract_teacher_from_list(page, discovered_url, college_name)
                for name, url2 in teachers:
                    if url2 not in teacher_urls_tried:
                        teacher_urls_tried.add(url2)
                        teacher_links.append((name, url2))

        print(f"  [汇总] {college_name}: 共找到 {len(teacher_links)} 位教师")

        # 3. 批量访问详情页 (每次并发3个)
        detail_sem = asyncio.Semaphore(3)
        async def fetch_detail(name, detail_url):
            async with detail_sem:
                detail_page = await context.new_page()
                try:
                    result = await extract_teacher_detail(detail_page, name, detail_url, college_name)
                    return result
                finally:
                    await detail_page.close()

        # 分批处理
        batch_size = 6
        for i in range(0, len(teacher_links), batch_size):
            batch = teacher_links[i:i+batch_size]
            tasks = [fetch_detail(name, url) for name, url in batch]
            results = await asyncio.gather(*tasks)
            all_teachers_data.extend(results)
            print(f"  [进度] {college_name}: {min(i+batch_size, len(teacher_links))}/{len(teacher_links)}")

        await context.close()
        return all_teachers_data

def save_csv(all_data, filename="东南大学_教师邮箱.csv"):
    """保存CSV"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["姓名", "邮箱", "学院", "职称", "主页链接"])
        for row in all_data:
            writer.writerow([
                row.get("name", ""),
                row.get("email", ""),
                row.get("college", ""),
                row.get("title", ""),
                row.get("url", ""),
            ])
    print(f"\n✅ 已保存: {filepath} ({len(all_data)} 条记录)")
    return filepath

async def main():
    start_time = time.time()
    all_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # 并发爬取所有学院
        tasks = []
        for name, homepage, known_urls in COLLEGES:
            task = crawl_college(browser, name, homepage, known_urls)
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        for college_results in results:
            all_results.extend(college_results)

        await browser.close()

    # 去重（按姓名+学院）
    seen = set()
    unique_results = []
    for r in all_results:
        key = (r.get("name", ""), r.get("college", ""))
        if key not in seen:
            seen.add(key)
            unique_results.append(r)

    print(f"\n{'='*50}")
    print(f"爬取完成！总教师数: {len(unique_results)}")
    print(f"有邮箱的: {sum(1 for r in unique_results if r.get('email'))}")
    print(f"有职称的: {sum(1 for r in unique_results if r.get('title'))}")
    print(f"耗时: {time.time() - start_time:.0f} 秒")

    # 按学院统计
    from collections import Counter
    college_counts = Counter(r.get("college", "未知") for r in unique_results)
    print(f"\n各学院人数统计:")
    for c, n in sorted(college_counts.items(), key=lambda x: -x[1]):
        email_count = sum(1 for r in unique_results if r.get("college") == c and r.get("email"))
        print(f"  {c}: {n} 人 (有邮箱: {email_count})")

    # 保存CSV
    save_csv(unique_results)

    return unique_results

if __name__ == "__main__":
    asyncio.run(main())
