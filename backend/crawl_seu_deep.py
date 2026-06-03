#!/usr/bin/env python3
"""
第三轮深度补爬 - 针对问题学院使用不同的策略
1. 医学院：查看HTML源码中是否包含邮箱（可能不在innerText里）
2. 能源与环境学院、自动化学院、机械工程学院：尝试其他列表URL
3. 人文学院、法学院：查看页面具体结构
"""
import asyncio
import csv
import os
import re
from collections import defaultdict

from playwright.async_api import async_playwright

OUTPUT_DIR = "D:/Work/test/UniEmailAgent/backend/outputs/9782a4a5-306a-437a-bf49-4900674734ad"

async def analyze_page_structure(browser, url, label):
    """分析页面HTML结构，查找邮箱"""
    context = await browser.new_context()
    page = await context.new_page()
    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    html = await page.content()
    text = await page.evaluate("document.body.innerText")

    # 在HTML源码中搜索邮箱模式
    html_emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
    text_emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)

    # 检查反爬格式
    anti_crawl = re.findall(r'[a-zA-Z0-9._%+-]+\[at\][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
    anti_crawl2 = re.findall(r'[a-zA-Z0-9._%+-]+\(at\)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)

    print(f"\n=== {label} ===")
    print(f"  HTML中发现的邮箱: {html_emails[:10]}")
    print(f"  文本中发现的邮箱: {text_emails[:10]}")
    print(f"  反爬[at]格式: {anti_crawl[:5]}")
    print(f"  反爬(at)格式: {anti_crawl2[:5]}")
    print(f"  页面标题: {await page.title()}")
    print(f"  页面长度: {len(html)} chars")

    # 检查是否有iframe
    iframes = await page.query_selector_all("iframe")
    print(f"  iframe数量: {len(iframes)}")
    for i, iframe in enumerate(iframes):
        src = await iframe.get_attribute("src")
        print(f"    iframe {i}: src={src}")

    await context.close()
    return text_emails, html_emails

async def deep_crawl_college(browser, college_name, homepage, list_urls, name_filter=None):
    """
    深度爬取 - 从HTML源码中搜邮箱，不使用innerText
    """
    print(f"\n{'='*50}")
    print(f"[深度爬取] {college_name}")
    print(f"{'='*50}")

    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        viewport={"width": 1920, "height": 1080},
    )
    page = await context.new_page()

    results = []
    all_teacher_links = []

    for url in list_urls:
        try:
            print(f"  列表页: {url}")
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            links = await page.query_selector_all("a")
            for link in links:
                try:
                    text = await link.inner_text()
                    text = text.strip()
                    href = await link.get_attribute("href")
                    if not text or not href:
                        continue
                    cn = re.findall(r'[一-鿿]', text)
                    if len(cn) < 2 or len(cn) > 6 or len(cn) != len(text):
                        continue
                    nav_kws = ["首页", "学院概况", "通知公告", "联系我们", "师资队伍",
                                "科学研究", "招聘", "下载", "登录", "第一页", "尾页", "跳转"]
                    if any(kw in text for kw in nav_kws):
                        continue

                    if href.startswith("http"):
                        full_url = href
                    elif href.startswith("/"):
                        from urllib.parse import urlparse
                        parsed = urlparse(url)
                        full_url = f"{parsed.scheme}://{parsed.netloc}{href}"
                    else:
                        full_url = url.rstrip("/") + "/" + href.lstrip("/")

                    all_teacher_links.append((text, full_url))
                except:
                    continue
        except Exception as e:
            print(f"  [错误] {url}: {e}")

    # 去重
    seen = set()
    unique_links = []
    for n, u in all_teacher_links:
        if n not in seen:
            seen.add(n)
            unique_links.append((n, u))

    print(f"  找到 {len(unique_links)} 位教师")

    # 访问详情页 - 从HTML源码搜邮箱
    detail_sem = asyncio.Semaphore(4)
    async def fetch_detail(name, detail_url):
        async with detail_sem:
            try:
                p = await context.new_page()
                await p.goto(detail_url, timeout=25000, wait_until="domcontentloaded")
                await p.wait_for_timeout(1500)

                # 从HTML源码搜邮箱
                html = await p.content()

                # 各种邮箱模式
                emails = set()
                # 普通格式
                for m in re.finditer(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html):
                    emails.add(m.group())
                # 反爬格式
                for m in re.finditer(r'[a-zA-Z0-9._%+-]+\[at\][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html):
                    email = m.group().replace("[at]", "@")
                    emails.add(email)
                for m in re.finditer(r'[a-zA-Z0-9._%+-]+\(at\)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html):
                    email = m.group().replace("(at)", "@")
                    emails.add(email)

                text_content = await p.evaluate("document.body.innerText")
                await p.close()

                # 过滤公共邮箱
                def is_public(e):
                    prefix = e.split("@")[0].lower()
                    for pfx in ["webmaster", "admin", "office", "info", "master"]:
                        if prefix == pfx or prefix.startswith(pfx):
                            return True
                    return False

                personal = [e for e in emails if not is_public(e)]
                seu = [e for e in personal if "seu.edu.cn" in e]

                # 职称
                title = ""
                for kw in ["教授", "副教授", "讲师", "助教", "研究员", "副研究员",
                           "高级工程师", "博导", "硕导", "院士"]:
                    if kw in text_content:
                        title = kw
                        break

                email = seu[0] if seu else (personal[0] if personal else "")
                return {"name": name, "email": email, "college": college_name,
                        "title": title, "url": detail_url}
            except Exception:
                return {"name": name, "email": "", "college": college_name,
                        "title": "", "url": detail_url}

    # 分批
    batch_size = 10
    for i in range(0, len(unique_links), batch_size):
        batch = unique_links[i:i+batch_size]
        tasks = [fetch_detail(n, u) for n, u in batch]
        batch_results = await asyncio.gather(*tasks)
        results.extend(batch_results)
        if (i // batch_size) % 2 == 0:
            print(f"    进度: {min(i+batch_size, len(unique_links))}/{len(unique_links)}")

    await context.close()
    email_count = sum(1 for r in results if r.get("email"))
    print(f"  [完成] {college_name}: {len(results)} 人, {email_count} 有邮箱")
    return results

async def main():
    # 先分析几个有问题的学院的页面结构
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # 分析医学院和人文学院
        await analyze_page_structure(browser,
            "https://med.seu.edu.cn/8693/list.htm", "医学院列表页")

        # 找一个教师的详情页看看
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://med.seu.edu.cn/8693/list.htm", timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        links = await page.query_selector_all("a")
        teacher_urls = []
        for link in links:
            text = await link.inner_text()
            href = await link.get_attribute("href")
            text = text.strip()
            cn = re.findall(r'[一-鿿]', text)
            if len(cn) >= 2 and len(cn) <= 6 and len(cn) == len(text) and href:
                nav_kws = ["首页", "学院", "通知", "师资", "党建", "学生", "联系", "招聘", "下载"]
                if not any(kw in text for kw in nav_kws):
                    if href.startswith("http"):
                        full_url = href
                    elif href.startswith("/"):
                        from urllib.parse import urlparse
                        parsed = urlparse("https://med.seu.edu.cn/8693/list.htm")
                        full_url = f"{parsed.scheme}://{parsed.netloc}{href}"
                    else:
                        full_url = "https://med.seu.edu.cn/8693/list.htm"
                    teacher_urls.append((text, full_url))
                    if len(teacher_urls) >= 3:
                        break
        await context.close()

        for name, url in teacher_urls:
            await analyze_page_structure(browser, url, f"医学院详情页 - {name}")

        # 人文学院
        await analyze_page_structure(browser,
            "https://rwxy.seu.edu.cn/8782/list.htm", "人文学院列表页")

        # 法学院
        await analyze_page_structure(browser,
            "https://law.seu.edu.cn/9121/list.htm", "法学院列表页")

        # 能源与环境学院 - 分析为什么只抓到36人
        await analyze_page_structure(browser,
            "https://power.seu.edu.cn/9232/list.htm", "能源与环境学院列表页")

        # 自动化学院 - 分析为什么只抓到31人
        await analyze_page_structure(browser,
            "https://automation.seu.edu.cn/szdw_32667/list.htm", "自动化学院列表页")

        # 如果医学院和人文学院的页面有邮箱，执行深度爬取
        print("\n\n开始深度爬取问题学院...")

        deep_tasks = []

        # 医学院（如果HTML有邮箱）
        deep_tasks.append(deep_crawl_college(browser, "医学院",
            "https://med.seu.edu.cn", ["https://med.seu.edu.cn/8693/list.htm"]))

        # 人文学院
        deep_tasks.append(deep_crawl_college(browser, "人文学院",
            "https://rwxy.seu.edu.cn",
            ["https://rwxy.seu.edu.cn/8782/list.htm", "https://rwxy.seu.edu.cn/8783/list.htm"]))

        # 法学院
        deep_tasks.append(deep_crawl_college(browser, "法学院",
            "https://law.seu.edu.cn",
            ["https://law.seu.edu.cn/9121/list.htm", "https://law.seu.edu.cn/9125/list.htm"]))

        # 体育系
        deep_tasks.append(deep_crawl_college(browser, "体育系",
            "https://tyx.seu.edu.cn", ["https://tyx.seu.edu.cn/2166/list.htm"]))

        deep_results = await asyncio.gather(*deep_tasks)

        # 合并所有深度爬取结果
        all_deep = []
        for r in deep_results:
            all_deep.extend(r)

        await browser.close()

    # 与已有CSV合并
    existing_path = os.path.join(OUTPUT_DIR, "东南大学_教师邮箱.csv")
    existing = []
    if os.path.exists(existing_path):
        with open(existing_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing.append(row)

    merged = {}
    for r in existing:
        key = (r.get("姓名", ""), r.get("学院", ""))
        merged[key] = r

    for r in all_deep:
        key = (r["name"], r["college"])
        old = merged.get(key, {})
        new_email = r.get("email", "") or old.get("邮箱", "")
        new_title = r.get("title", "") or old.get("职称", "")
        merged[key] = {
            "姓名": r["name"],
            "邮箱": new_email,
            "学院": r["college"],
            "职称": new_title,
            "主页链接": r.get("url", old.get("主页链接", "")),
        }

    final = list(merged.values())
    filepath = os.path.join(OUTPUT_DIR, "东南大学_教师邮箱.csv")
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["姓名", "邮箱", "学院", "职称", "主页链接"])
        for row in final:
            writer.writerow([
                row.get("姓名", ""), row.get("邮箱", ""),
                row.get("学院", ""), row.get("职称", ""),
                row.get("主页链接", ""),
            ])

    from collections import Counter
    college_counts = Counter(r.get("学院", "未知") for r in final)
    print(f"\n{'='*60}")
    print(f"最终总教师数: {len(final)}")
    print(f"有邮箱的: {sum(1 for r in final if r.get('邮箱'))}")
    print(f"有职称的: {sum(1 for r in final if r.get('职称'))}")
    print(f"\n各学院人数统计:")
    for c, n in sorted(college_counts.items(), key=lambda x: -x[1]):
        email_count = sum(1 for r in final if r.get("学院") == c and r.get("邮箱"))
        print(f"  {c}: {n} 人 (有邮箱: {email_count})")

    print(f"\n✅ 已保存: {filepath}")

if __name__ == "__main__":
    asyncio.run(main())
