"""
修复化学化工和地球科学 — 展开侧边栏分类获取教师链接
"""
import asyncio
import csv
import re
import os
from datetime import datetime
from playwright.async_api import async_playwright

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

PUBLIC_SET = {
    'webmaster@nju.edu.cn', 'admin@nju.edu.cn', 'info@nju.edu.cn',
    'history@nju.edu.cn', 'imnju@nju.edu.cn', 'sxydw@nju.edu.cn',
    'xgdw@nju.edu.cn', 'zhanghao@nju.edu.cn', 'fxshen@nju.edu.cn',
    'wangyuxuan@nju.edu.cn', 'office@nju.edu.cn', 'malab@nju.edu.cn',
    'wanghui@nju.edu.cn', 'dongting@nju.edu.cn',
}


def extract_personal_email(page_text):
    patterns = [
        r'电子邮箱[：:]\s*[\[【]?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
        r'邮箱[：:]\s*[\[【]?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
        r'E-?mail[：:]\s*[\[【]?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
        r'电子邮件[：:]\s*[\[【]?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
    ]
    for pat in patterns:
        m = re.search(pat, page_text, re.IGNORECASE)
        if m:
            email = m.group(1).strip().lower()
            if email not in PUBLIC_SET:
                return email

    text = re.sub(r'\[at\]|\(at\)|#@|\[@\]', '@', page_text, flags=re.IGNORECASE)
    text = re.sub(r'\s*@\s*', '@', text)
    all_emails = EMAIL_RE.findall(text)
    for email in all_emails:
        email_lower = email.lower()
        if email_lower not in PUBLIC_SET:
            return email_lower
    return ""


async def scrape_college_with_sidebar(browser, config):
    """处理侧边栏展开式学院"""
    name = config["name"]
    list_url = config["list_url"]
    domain = config["domain"]
    # 侧边栏分类关键词
    category_keywords = config.get("categories", [])

    print(f"\n=== {name} ===")
    context = await browser.new_context(viewport={"width": 1280, "height": 900})
    page = await context.new_page()
    page.set_default_timeout(15000)

    # 1. 访问教师列表页
    try:
        await page.goto(list_url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)
    except Exception as e:
        print(f"  页面加载失败: {e}")
        await context.close()
        return []

    # 2. 找到所有侧边栏分类链接
    sidebar_links = await page.evaluate("""() => {
        const links = document.querySelectorAll('a[href]');
        return Array.from(links).map(a => ({
            text: (a.textContent || '').trim(),
            href: a.href,
            className: a.className || '',
            parentId: a.parentElement?.id || ''
        }));
    }""")

    # 收集分类链接
    category_urls = set()
    for link in sidebar_links:
        text = link["text"]
        href = link["href"]
        if domain not in href:
            continue
        # 匹配分类关键词
        for kw in category_keywords:
            if kw in text:
                category_urls.add(href)
                print(f"  找到分类: {text} -> {href}")

    if not category_urls:
        # 尝试用更宽泛的规则找
        print(f"  未找到分类链接，尝试宽泛匹配...")
        for link in sidebar_links:
            text = link["text"]
            href = link["href"]
            if domain not in href:
                continue
            # 常见的子分类表达：XX学、XX系、XX组、XX方向
            if any(suffix in text for suffix in ['学', '系', '组', '方向']) and len(text) <= 15:
                if 'szll' in href or 'list.htm' in href:
                    category_urls.add(href)

    print(f"  共找到 {len(category_urls)} 个分类")

    # 3. 遍历每个分类，展开获取教师链接
    all_teacher_links = []
    seen_teacher_urls = set()

    for cat_url in list(category_urls)[:20]:  # 最多20个分类
        try:
            await page.goto(cat_url, wait_until="networkidle", timeout=15000)
            await asyncio.sleep(1.5)

            # 获取该分类下的教师链接
            cat_links = await page.evaluate("""() => {
                const links = document.querySelectorAll('a[href]');
                return Array.from(links).map(a => ({
                    text: (a.textContent || '').trim(),
                    href: a.href
                }));
            }""")

            for cl in cat_links:
                text = cl["text"]
                href = cl["href"]
                if domain not in href:
                    continue
                # 教师姓名：2-4个汉字
                if re.match(r'^[一-鿿·]{2,4}$', text):
                    if href not in seen_teacher_urls:
                        seen_teacher_urls.add(href)
                        all_teacher_links.append({"name": text, "href": href})
        except Exception as e:
            print(f"  ✗ {cat_url}: {str(e)[:60]}")

    # 如果不够，尝试直接点击页面中的可展开元素
    if len(all_teacher_links) < 10:
        print(f"  只找到 {len(all_teacher_links)} 个教师，尝试展开页面元素...")
        await page.goto(list_url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        # 尝试点击所有可展开的链接
        click_targets = await page.evaluate("""() => {
            const elements = document.querySelectorAll('a, li, .category, .submenu, [data-toggle]');
            return Array.from(elements).map(el => ({
                tag: el.tagName,
                text: (el.textContent || '').trim().substring(0, 30),
                href: el.href || '',
                className: el.className || ''
            }));
        }""")

        expand_targets = []
        for ct in click_targets:
            if any(kw in ct["text"] for kw in category_keywords + ['学', '系', '组']):
                if len(ct["text"]) <= 15:
                    expand_targets.append(ct)

        for et in expand_targets[:15]:
            try:
                # 尝试点击文本元素
                escaped = et["text"].replace("'", "\\'")
                await page.evaluate(f"""
                    const links = document.querySelectorAll('a');
                    for (const a of links) {{
                        if (a.textContent.trim() === '{escaped}') {{
                            a.click();
                            break;
                        }}
                    }}
                """)
                await asyncio.sleep(1)

                # 检查新出现的链接
                new_links = await page.evaluate("""() => {
                    const links = document.querySelectorAll('a[href]');
                    return Array.from(links).map(a => ({
                        text: (a.textContent || '').trim(),
                        href: a.href
                    }));
                }""")
                for nl in new_links:
                    ntext = nl["text"]
                    nhref = nl["href"]
                    if domain in nhref and re.match(r'^[一-鿿·]{2,4}$', ntext):
                        if nhref not in seen_teacher_urls:
                            seen_teacher_urls.add(nhref)
                            all_teacher_links.append({"name": ntext, "href": nhref})
            except:
                pass

    print(f"  共找到 {len(all_teacher_links)} 个教师链接")

    # 4. 逐个访问详情页提取邮箱
    results = []
    for i, teacher in enumerate(all_teacher_links):
        try:
            await page.goto(teacher["href"], wait_until="networkidle", timeout=20000)
            await asyncio.sleep(0.6)

            page_text = await page.evaluate("() => document.body?.innerText || ''")
            email = extract_personal_email(page_text)

            title = ""
            for t in ['教授', '副教授', '助理教授', '讲师', '研究员', '副研究员', '院士']:
                if t in page_text[:3000]:
                    title = t
                    break

            if email:
                results.append({
                    "姓名": teacher["name"],
                    "邮箱": email,
                    "学院": name,
                    "职称": title,
                    "主页链接": teacher["href"],
                })
                print(f"  ✓ [{i+1}/{len(all_teacher_links)}] {teacher['name']} → {email}")
            else:
                print(f"  ✗ [{i+1}/{len(all_teacher_links)}] {teacher['name']} 无邮箱")
        except Exception as e:
            pass

    await context.close()
    print(f"  {name} 完成: {len(results)} 人")
    return results


async def main():
    configs = [
        {
            "name": "化学化工学院",
            "domain": "chem.nju.edu.cn",
            "list_url": "https://chem.nju.edu.cn/szll/list.htm",
            "categories": ["无机化学", "分析化学", "有机化学", "物理化学",
                          "高分子", "化学生物学", "化学工程", "应用化学",
                          "跨学科", "教授", "副教授", "讲师"],
        },
        {
            "name": "地球科学与工程学院",
            "domain": "es.nju.edu.cn",
            "list_url": "https://es.nju.edu.cn/szdw/list.htm",
            "categories": ["教授", "副教授", "讲师", "地质", "地球化学",
                          "地球物理", "水文", "工程地质", "矿物", "古生物",
                          "构造", "岩石", "地球探测", "水文学"],
        },
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        all_results = []

        for config in configs:
            results = await scrape_college_with_sidebar(browser, config)
            all_results.extend(results)

        await browser.close()

    if all_results:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(OUTPUT_DIR, f"南京大学_侧边栏补抓_{ts}.csv")
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=["姓名", "邮箱", "学院", "职称", "主页链接"])
            writer.writeheader()
            for r in all_results:
                writer.writerow(r)
        print(f"\n保存: {path}")
        print(f"总计: {len(all_results)} 人")

        from collections import Counter
        for c, n in Counter(r["学院"] for r in all_results).most_common():
            print(f"  {c}: {n} 人")


if __name__ == "__main__":
    asyncio.run(main())
