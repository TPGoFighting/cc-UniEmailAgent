"""
针对性爬取南京大学低人数学院 —— 深度进入教师详情页
"""
import asyncio
import csv
import re
import os
import sys
from datetime import datetime
from playwright.async_api import async_playwright

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")

# ========== 学院配置 ==========
# 每个学院配置：名称、教师列表入口URL、网站域名
COLLEGES = [
    {
        "name": "电子科学与工程学院",
        "domain": "https://ese.nju.edu.cn",
        # 可能的教师列表页
        "list_urls": [
            "https://ese.nju.edu.cn/szdw/list.htm",
            "https://ese.nju.edu.cn/30444/list.htm",
            "https://ese.nju.edu.cn/30445/list.htm",
        ],
    },
    {
        "name": "地球科学与工程学院",
        "domain": "https://es.nju.edu.cn",
        "list_urls": [
            "https://es.nju.edu.cn/szdw/list.htm",
            "https://es.nju.edu.cn/25233/list.htm",
        ],
    },
    {
        "name": "化学化工学院",
        "domain": "https://chem.nju.edu.cn",
        "list_urls": [
            "https://chem.nju.edu.cn/szdw/list.htm",
            "https://chem.nju.edu.cn/12584/list.htm",
        ],
    },
    {
        "name": "现代工程与应用科学学院",
        "domain": "https://eng.nju.edu.cn",
        "list_urls": [
            "https://eng.nju.edu.cn/szdw/list.htm",
            "https://eng.nju.edu.cn/zrjswyjxlwhbshwzp/list.htm",
        ],
    },
    {
        "name": "生命科学学院",
        "domain": "https://life.nju.edu.cn",
        "list_urls": [
            "https://life.nju.edu.cn/szdw/list.htm",
            "https://life.nju.edu.cn/12924/list.htm",
        ],
    },
    {
        "name": "历史学院",
        "domain": "https://history.nju.edu.cn",
        "list_urls": [
            "https://history.nju.edu.cn/szdw/list.htm",
            "https://history.nju.edu.cn/28500/list.htm",
        ],
    },
    {
        "name": "商学院",
        "domain": "https://nubs.nju.edu.cn",
        "list_urls": [
            "https://nubs.nju.edu.cn/szdw/list.htm",
            "https://nubs.nju.edu.cn/szdw.htm",
        ],
    },
    {
        "name": "文学院",
        "domain": "https://chin.nju.edu.cn",
        "list_urls": [
            "https://chin.nju.edu.cn/szdw/xrjs/zggdwx/index.html",
            "https://chin.nju.edu.cn/szdw/xrjs/xjyysx/index.html",
            "https://chin.nju.edu.cn/szdw.htm",
        ],
    },
    {
        "name": "中美文化研究中心",
        "domain": "https://hnc.nju.edu.cn",
        "list_urls": [
            "https://hnc.nju.edu.cn/szll.htm",
            "https://hnc.nju.edu.cn/szll/list.htm",
        ],
    },
]

# 邮箱正则（支持反爬恢复）
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

# 导航关键词（用于过滤非教师链接）
NAV_KEYWORDS = [
    '首页', '概况', '简介', '通知', '公告', '新闻', '动态', '招生', '培养',
    '科研', '学术', '党建', '工会', '校友', '捐赠', '联系', '下载', '服务',
    '管理', '系统', '登录', '注册', 'English', '关于', '返回', 'Copyright',
    '主办', '承办', '版权所有', '地址', '电话', '传真', '邮编', '邮箱',
    '友情链接', '快速通道', '专题', '栏目', '导航',
]

# 公共邮箱模式
PUBLIC_EMAIL_PATTERNS = [
    r'webmaster@', r'admin@', r'info@', r'office@', r'postmaster@',
    r'wxyxz@', r'xwcb@', r'imnju@', r'xgdw@',
]

def is_nav_link(text):
    """判断是否为导航链接"""
    text = text.strip()
    if not text:
        return True
    # 太短或太长
    if len(text) <= 2 or len(text) > 50:
        return True
    for kw in NAV_KEYWORDS:
        if kw in text:
            return True
    return False

def is_public_email(email):
    """判断是否为公共邮箱"""
    email_lower = email.lower()
    for pattern in PUBLIC_EMAIL_PATTERNS:
        if re.search(pattern, email_lower):
            return True
    return False

def extract_emails(text):
    """从文本中提取所有邮箱"""
    if not text:
        return []
    # 恢复反爬邮箱
    text = re.sub(r'\[at\]|\(at\)|#@|\[@\]', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*@\s*', '@', text)
    return EMAIL_RE.findall(text)

def normalize_email(email):
    """清理邮箱（转小写、去空格）"""
    return email.strip().lower()

async def scrape_college(browser, college):
    """爬取单个学院"""
    name = college["name"]
    domain = college["domain"]
    list_urls = college["list_urls"]

    print(f"\n{'='*60}")
    print(f"开始爬取: {name}")
    print(f"{'='*60}")

    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
    page = await context.new_page()
    page.set_default_timeout(30000)

    results = []
    seen_urls = set()
    teacher_links = []

    # --- 第1步：找到教师列表页，收集教师详情链接 ---
    list_found = False
    for list_url in list_urls:
        print(f"  尝试教师列表页: {list_url}")
        try:
            await page.goto(list_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # 获取页面所有链接
            links = await page.evaluate("""() => {
                const links = document.querySelectorAll('a[href]');
                return Array.from(links).map(a => ({
                    text: (a.textContent || '').trim(),
                    href: a.href
                }));
            }""")

            # 过滤出教师链接
            teacher_count = 0
            for link in links:
                text = link["text"]
                href = link["href"]

                if not text or is_nav_link(text):
                    continue

                # 教师姓名特征：2-4个汉字，不包含导航词
                if re.match(r'^[一-鿿·]{2,5}$', text):
                    if href not in seen_urls and domain in href:
                        seen_urls.add(href)
                        teacher_links.append({"name": text, "href": href})
                        teacher_count += 1
                        if teacher_count <= 5:
                            print(f"    → 找到教师: {text} → {href[:80]}")

            if teacher_count > 3:
                print(f"  从 {list_url} 找到 {teacher_count} 个教师链接")
                list_found = True

        except Exception as e:
            print(f"  ✗ 加载失败 ({list_url}): {e}")

    if not teacher_links:
        print(f"  ⚠ 未找到教师链接，尝试在学院首页查找")
        try:
            await page.goto(domain, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # 查找师资队伍相关链接
            links = await page.evaluate("""() => {
                const links = document.querySelectorAll('a[href]');
                return Array.from(links).map(a => ({
                    text: (a.textContent || '').trim(),
                    href: a.href
                }));
            }""")

            for link in links:
                text = link["text"]
                href = link["href"]
                if any(kw in text for kw in ['师资', '教师', 'faculty', 'staff', '人员']):
                    print(f"  找到师资入口: {text} → {href}")
                    try:
                        await page.goto(href, wait_until="networkidle", timeout=30000)
                        await asyncio.sleep(2)

                        sub_links = await page.evaluate("""() => {
                            const links = document.querySelectorAll('a[href]');
                            return Array.from(links).map(a => ({
                                text: (a.textContent || '').trim(),
                                href: a.href
                            }));
                        }""")

                        for sl in sub_links:
                            stext = sl["text"]
                            shref = sl["href"]
                            if re.match(r'^[一-鿿·]{2,5}$', stext):
                                if not is_nav_link(stext) and shref not in seen_urls and domain in shref:
                                    seen_urls.add(shref)
                                    teacher_links.append({"name": stext, "href": shref})
                    except Exception as e:
                        print(f"    ✗ 子页面加载失败: {e}")
        except Exception as e:
            print(f"  ✗ 首页加载失败: {e}")

    print(f"\n  共找到 {len(teacher_links)} 个潜在教师链接")

    # --- 第2步：逐个访问教师详情页，提取邮箱 ---
    for i, teacher in enumerate(teacher_links):
        tname = teacher["name"]
        thref = teacher["href"]

        if (i + 1) % 20 == 0:
            print(f"  进度: {i+1}/{len(teacher_links)}")

        try:
            await page.goto(thref, wait_until="networkidle", timeout=20000)
            await asyncio.sleep(0.5)

            page_text = await page.evaluate("() => document.body.innerText")
            title_text = await page.evaluate("() => document.title")

            # 提取邮箱
            emails = extract_emails(page_text)
            personal_email = ""
            for email in emails:
                if not is_public_email(email):
                    personal_email = normalize_email(email)
                    break

            # 提取职称
            title = ""
            title_patterns = [
                r'(教授|副教授|助理教授|讲师|助教|研究员|副研究员|助理研究员|院士|博导|长江学者|杰出青年|优秀青年|青年学者|长聘教授|准聘教授|准聘副教授|准聘助理教授)',
            ]
            for pattern in title_patterns:
                m = re.search(pattern, page_text[:2000])
                if m:
                    title = m.group(1)
                    break

            # 提取姓名（确认）
            name_from_page = ""
            name_patterns = [r'姓名[：:]\s*([一-鿿]{2,4})', r'姓名\s+([一-鿿]{2,4})']
            for pat in name_patterns:
                m = re.search(pat, page_text[:2000])
                if m:
                    name_from_page = m.group(1)
                    break

            final_name = name_from_page if name_from_page else tname

            if personal_email:
                results.append({
                    "姓名": final_name,
                    "邮箱": personal_email,
                    "学院": name,
                    "职称": title,
                    "主页链接": thref,
                })
                print(f"  ✓ [{i+1}/{len(teacher_links)}] {final_name} → {personal_email}")
            else:
                print(f"  ✗ [{i+1}/{len(teacher_links)}] {final_name} 无个人邮箱")

        except Exception as e:
            error_msg = str(e)[:100]
            print(f"  ✗ [{i+1}/{len(teacher_links)}] {tname}: {error_msg}")

    await context.close()
    print(f"\n  {name} 完成: {len(results)} 位教师")
    return results


async def main():
    print("=" * 60)
    print("南京大学低人数学院针对性爬虫")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        all_results = []

        for college in COLLEGES:
            results = await scrape_college(browser, college)
            all_results.extend(results)

        await browser.close()

    # 保存结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(OUTPUT_DIR, f"南京大学_低人数学院定向_{timestamp}.csv")

    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=["姓名", "邮箱", "学院", "职称", "主页链接"])
        writer.writeheader()
        for r in all_results:
            writer.writerow(r)

    print(f"\n{'='*60}")
    print(f"全部完成！共 {len(all_results)} 条记录")
    print(f"已保存至: {csv_path}")
    print(f"{'='*60}")

    # 按学院汇总
    from collections import Counter
    counts = Counter(r["学院"] for r in all_results)
    for college, count in counts.most_common():
        print(f"  {college}: {count} 人")


if __name__ == "__main__":
    asyncio.run(main())
