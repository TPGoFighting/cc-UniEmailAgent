"""
深度爬虫 v3 — 针对低人数学院的智能补全
核心策略：
1. 访问学院首页和已知的师资相关页面
2. 搜索包含邮箱的页面（直接搜索 "@nju.edu.cn"）
3. 抓取所有可能的教师信息链接
4. 优先使用短链接格式（如 <initials>/list.htm），因为这些页面包含个人邮箱
"""

import asyncio
import csv
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

# 排除的公共邮箱特征
PUBLIC_EMAIL_PREFIXES = [
    "sxydw", "njugcglxy", "gcglxydw", "njudz", "yb_eng", "yb_",
    "arch@", "history@", "oice@", "yingfeng@", "xwzx@",
    "jcjs@", "webmaster", "admin", "info@", "office@",
    "wxyxz@",  # 文学院公共邮箱 - 新增
]

# 被证实包含个人邮箱的页面 URL 模式
# <initials>/list.htm -> 商学院、教育研究院、工程管理学院等
SHORTURL_PATTERN = re.compile(r"/([a-z]{2,4}\d{0,2})/list\.htm$")


def is_public_email(email: str) -> bool:
    if not email:
        return True
    email_lower = email.lower()
    for prefix in PUBLIC_EMAIL_PREFIXES:
        if prefix in email_lower:
            return True
    return False


def extract_chinese_name(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"^([一-鿿]{2,4})", text.strip())
    return m.group(1) if m else ""


def is_chinese_name(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    if not re.fullmatch(r"[一-鿿]{2,4}", text):
        return False
    bad_ends = "报组室部处委会局办系院所馆站网栏目页版"
    if text[-1] in bad_ends:
        return False
    return True


# 各学院需要探索的页面
DEPT_SEED_URLS = {
    "商学院": [
        "https://nubs.nju.edu.cn/szdw/list.htm",
        "https://nubs.nju.edu.cn/8478/list.htm",
    ],
    "教育研究院": [
        "https://edu.nju.edu.cn/szdw/list.htm",
        "https://edu.nju.edu.cn/jyjs/list.htm",
    ],
    "文学院": [
        "https://chin.nju.edu.cn/szdw/xrjs/index.html",
        "https://chin.nju.edu.cn/szdw/xrjs/zggdwx/index.html",
        "https://chin.nju.edu.cn/szdw/xrjs/zggdwxx/index.html",
        "https://chin.nju.edu.cn/szdw/xrjs/zgxddwx/index.html",
        "https://chin.nju.edu.cn/szdw/xrjs/xjyysx/index.html",
        "https://chin.nju.edu.cn/szdw/xrjs/bjwxysjwx/index.html",
        "https://chin.nju.edu.cn/szdw/xrjs/wyx/index.html",
        "https://chin.nju.edu.cn/szdw/xrjs/hyywzx/index.html",
        "https://chin.nju.edu.cn/szdw/xrjs/yyxjyyyyx/index.html",
    ],
    "电子科学与工程学院": [
        "https://ese.nju.edu.cn/30444/list.htm",
        "https://ese.nju.edu.cn/16777/list.htm",
    ],
    "化学化工学院": [
        "https://chem.nju.edu.cn/szll/list.htm",
    ],
    "工程管理学院": [
        "https://sme.nju.edu.cn/szdw/list.htm",
    ],
    "艺术学院": [
        "https://art.nju.edu.cn/szdw/list.htm",
    ],
    "匡亚明学院": [
        "https://dii.nju.edu.cn/8328/list.htm",
    ],
    "能源与资源学院": [
        "https://energy.nju.edu.cn/ktzcy/js/index.html",
        "https://energy.nju.edu.cn/ktzcy/index.html",
    ],
}


async def scrape_department(browser, dept_name: str, seed_urls: list[str],
                            sem: asyncio.Semaphore) -> list[dict]:
    """对一个学院进行智能爬取"""
    results = []
    seen_emails = set()
    seen_urls = set()

    async with sem:
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        try:
            print(f"\n{'='*60}")
            print(f"🔍 [{dept_name}]")

            for seed_url in seed_urls:
                try:
                    await page.goto(seed_url, wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    continue
                await asyncio.sleep(1)

                # 获取所有链接
                links = await page.evaluate("""() => {
                    const links = [];
                    document.querySelectorAll('a[href]').forEach(a => {
                        const text = (a.textContent || '').trim();
                        const href = a.href;
                        if (!text || !href) return;
                        if (href.startsWith('javascript:') || href.endsWith('#')) return;
                        if (href.includes('main.htm') || href.includes('main.psp')) return;
                        if (href.includes('mailto:')) return;
                        links.push({text: text.substring(0, 60), href: href});
                    });
                    return links;
                }""")

                base_domain = urlparse(seed_url).netloc
                candidate_urls = set()

                for link in links:
                    text = link["text"]
                    url = link["href"]

                    # 只看同域名
                    if base_domain not in url:
                        continue

                    # 跳过明显的导航链接
                    nav_keywords = [
                        "首页", "学院概况", "学院简介", "机构设置", "新闻动态",
                        "通知公告", "学术动态", "科研动态", "人才培养", "招生",
                        "党", "团", "学生管理", "实验室", "图书馆", "联系我们",
                        "师德", "院长信箱", "南大主页", "主站", "返回", "上一页",
                        "下一页", "尾页", "下一页", "尾页", "个人中心", "网站首页",
                    ]
                    is_nav = False
                    for kw in nav_keywords:
                        if kw in text:
                            is_nav = True
                            break
                    if is_nav:
                        continue

                    # 保留短URL格式（最有价值）和包含姓名的链接
                    if SHORTURL_PATTERN.search(url):
                        name = extract_chinese_name(text)
                        if is_chinese_name(name):
                            candidate_urls.add(url)
                    elif is_chinese_name(extract_chinese_name(text)):
                        # 可能是包含姓名的链接
                        candidate_urls.add(url)

                print(f"  📄 {seed_url} → 候选数: {len(candidate_urls)}")

                # 访问候选页面提取邮箱
                for url in list(candidate_urls)[:30]:
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                        await asyncio.sleep(0.3)

                        page_text = await page.evaluate(
                            "() => document.body ? document.body.innerText : ''"
                        )
                        emails = EMAIL_RE.findall(page_text)
                        valid = [e for e in emails if not is_public_email(e)]

                        if valid:
                            # 提取信息
                            email = valid[0]
                            if email in seen_emails:
                                continue

                            # 尝试找姓名
                            title_match = re.search(r'(?:content|title|name)[=:"]?\s*"?([^"<>\n]{2,30})', page_text)
                            name_from_url = extract_chinese_name(urlparse(url).path.split('/')[-2] or urlparse(url).path.split('/')[-1])

                            # 在页面标题或文本开头找姓名
                            name = ""
                            lines = page_text.strip().split('\n')
                            for line in lines[:10]:
                                line = line.strip()
                                if len(line) <= 15 and is_chinese_name(line):
                                    name = line
                                    break

                            if not name:
                                name = name_from_url

                            # 找职称
                            title = ""
                            for t in ["教授", "副教授", "讲师", "助理教授", "研究员", "副研究员",
                                       "博导", "硕导", "院士", "博士后", "工程师", "实验师"]:
                                if t in page_text[:500]:
                                    title = t if not title else title + "、" + t

                            results.append({
                                "姓名": name or "未知",
                                "邮箱": email,
                                "学院": dept_name,
                                "职称": title[:30],
                                "主页链接": url,
                            })
                            seen_emails.add(email)
                            print(f"     ✅ {name or '?'} → {email}")

                    except Exception:
                        pass

        except Exception as e:
            print(f"  ❌ [{dept_name}] 错误: {e}")
        finally:
            await context.close()

    return results


async def main():
    print("=" * 60)
    print("🎓 V3 智能爬虫 — 针对低人数学院的深层探索")
    print("=" * 60)

    sem = asyncio.Semaphore(3)
    all_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        for dept_name, seed_urls in DEPT_SEED_URLS.items():
            results = await scrape_department(browser, dept_name, seed_urls, sem)
            all_results.extend(results)
            print(f"  📊 [{dept_name}] 新获取: {len(results)} 位教师")

        await browser.close()

    # 统计
    total = len(all_results)
    has_email = sum(1 for r in all_results if r["邮箱"] and r["邮箱"] != "无邮箱")
    print(f"\n{'='*60}")
    print(f"🎉 V3 新获取: {total} 人, 有邮箱: {has_email} 人")

    from collections import Counter
    dept_count = Counter(r["学院"] for r in all_results)
    for dept, cnt in dept_count.most_common():
        with_email = sum(1 for r in all_results if r["学院"] == dept and r["邮箱"] and r["邮箱"] != "无邮箱")
        print(f"  {dept}: {cnt}人, 有邮箱{with_email}人")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"南京大学_补充学院_v3_{timestamp}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["姓名", "邮箱", "学院", "职称", "主页链接"])
        writer.writeheader()
        writer.writerows(all_results)

    print(f"\n💾 已保存: {csv_path}")
    return csv_path


if __name__ == "__main__":
    asyncio.run(main())
