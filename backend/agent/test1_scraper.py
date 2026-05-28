"""测试1 — 南京大学教师邮箱爬虫。

多级爬取：学院列表页 → 教师个人详情页 → 提取邮箱
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
    print("请先安装: pip install playwright && playwright install chromium")
    sys.exit(1)

# 固定输出目录
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "a6be504a-8ff0-4b89-9d62-8752953ed8e9"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
AT_RE = re.compile(r"\s*\[at\]\s*|\s*\(at\)\s*|\s*#@\s*|\s*\[@\]\s*", re.IGNORECASE)

# 公共邮箱特征 — 排除
PUBLIC_PREFIXES = [
    "webmaster", "admin", "info@", "office@", "master@", "root@",
    "postmaster@", "wxyxz@", "sxydw@", "nju_" * 3,
]

# 导航关键词 — 排除非教师链接
NAV_KW = {
    "首页", "概况", "简介", "领导", "部门", "制度", "招聘", "通知", "公告",
    "新闻", "动态", "科研", "党建", "团建", "学生", "招生", "就业", "合作",
    "联系", "关于", "下载", "办事", "指南", "登录", "注册", "加入", "返回",
    "更多", "查看", "详情", "关闭", "中文", "英文", "网站", "地图",
    "博士后", "教研室", "实验室", "研究所", "中心", "学院", "大学",
    "科学研究", "学术", "交流", "国际", "版权所有", "友情链接",
    "人才培养", "社会服务", "校友", "基金会", "图书馆", "学报",
    "师德", "院长信箱", "主站", "上一页", "下一页", "尾页", "个人中心",
}

# 南京大学各院系教师列表页
DEPT_CONFIGS = [
    {
        "name": "计算机科学与技术系",
        "urls": [
            "https://cs.nju.edu.cn/szdw/list.htm",
            "https://cs.nju.edu.cn/21798/list.htm",
        ],
    },
    {
        "name": "人工智能学院",
        "urls": [
            "https://ai.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "软件学院",
        "urls": [
            "https://software.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "数学系",
        "urls": [
            "https://math.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "物理学院",
        "urls": [
            "https://physics.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "电子科学与工程学院",
        "urls": [
            "https://ese.nju.edu.cn/30444/list.htm",
            "https://ese.nju.edu.cn/16777/list.htm",
        ],
    },
    {
        "name": "商学院",
        "urls": [
            "https://nubs.nju.edu.cn/szdw/list.htm",
            "https://nubs.nju.edu.cn/8478/list.htm",
        ],
    },
    {
        "name": "化学化工学院",
        "urls": [
            "https://chem.nju.edu.cn/szll/list.htm",
        ],
    },
    {
        "name": "工程管理学院",
        "urls": [
            "https://sme.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "教育研究院",
        "urls": [
            "https://edu.nju.edu.cn/szdw/list.htm",
            "https://edu.nju.edu.cn/jyjs/list.htm",
        ],
    },
    {
        "name": "文学院",
        "urls": [
            "https://chin.nju.edu.cn/szdw/xrjs/index.html",
        ],
    },
    {
        "name": "法学院",
        "urls": [
            "https://law.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "外国语学院",
        "urls": [
            "https://sfs.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "新闻传播学院",
        "urls": [
            "https://jc.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "历史学院",
        "urls": [
            "https://history.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "哲学系",
        "urls": [
            "https://philo.nju.edu.cn/4712/list.htm",
        ],
    },
    {
        "name": "医学院",
        "urls": [
            "https://med.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "生命科学学院",
        "urls": [
            "https://life.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "环境学院",
        "urls": [
            "https://hjxy.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "地理与海洋科学学院",
        "urls": [
            "https://sgos.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "地球科学与工程学院",
        "urls": [
            "https://es.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "大气科学学院",
        "urls": [
            "https://atmos.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "天文与空间科学学院",
        "urls": [
            "https://astronomy.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "建筑与城市规划学院",
        "urls": [
            "https://arch.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "信息管理学院",
        "urls": [
            "https://im.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "社会学院",
        "urls": [
            "https://sociology.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "政府管理学院",
        "urls": [
            "https://public.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "马克思主义学院",
        "urls": [
            "https://marx.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "艺术学院",
        "urls": [
            "https://art.nju.edu.cn/szdw/list.htm",
        ],
    },
    {
        "name": "匡亚明学院",
        "urls": [
            "https://dii.nju.edu.cn/8328/list.htm",
        ],
    },
    {
        "name": "现代工程与应用科学学院",
        "urls": [
            "https://eng.nju.edu.cn/zrjswyjxlwhbshwzp/list.htm",
        ],
    },
    {
        "name": "能源与资源学院",
        "urls": [
            "https://energy.nju.edu.cn/ktzcy/js/index.html",
        ],
    },
]


def extract_emails(text: str) -> list[str]:
    text = AT_RE.sub("@", text)
    return list(set(EMAIL_RE.findall(text)))


def is_public_email(email: str) -> bool:
    email_lower = email.lower()
    for prefix in PUBLIC_PREFIXES:
        if prefix in email_lower:
            return True
    return False


def looks_like_teacher_name(text: str) -> bool:
    text = text.strip()
    if not text or len(text) > 30:
        return False
    m = re.match(r"^([一-鿿]{2,4})", text)
    if not m:
        return False
    if m.group(1) in NAV_KW or text in NAV_KW:
        return False
    return True


def extract_name_from_text(text: str) -> str:
    """从文本开头提取中文姓名"""
    m = re.match(r"^([一-鿿]{2,4})", text.strip())
    return m.group(1) if m else ""


async def collect_links(page) -> list[dict]:
    """收集页面所有链接"""
    return await page.evaluate("""() => {
        const links = [];
        const seen = new Set();
        document.querySelectorAll('a[href]').forEach(a => {
            const text = (a.textContent || '').trim();
            const href = a.href;
            if (!text || !href || seen.has(href)) return;
            if (href.startsWith('javascript:') || href.startsWith('mailto:') || href.endsWith('#')) return;
            seen.add(href);
            links.push({text: text.substring(0, 80), href: href});
        });
        return links;
    }""")


async def scrape_teacher_detail(page, url: str, dept_name: str, default_name: str = "") -> dict:
    """访问教师个人详情页，提取邮箱、姓名、职称"""
    result = {
        "姓名": default_name,
        "邮箱": "",
        "学院": dept_name,
        "职称": "",
        "主页链接": url,
    }
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(0.3)

        page_text = await page.evaluate("() => document.body?.innerText || ''")
        if not page_text:
            return result

        # 提取邮箱
        emails = extract_emails(page_text)
        personal = [e for e in emails if not is_public_email(e)]
        if personal:
            nju = [e for e in personal if "nju.edu.cn" in e.lower()]
            result["邮箱"] = nju[0] if nju else personal[0]

        # 提取姓名
        if not default_name:
            name = await page.evaluate("""() => {
                const title = document.title || '';
                const parts = title.split(/[-–—|｜_\\s]+/);
                for (const p of parts) {
                    const t = p.trim();
                    if (/^[\\u4e00-\\u9fff]{2,3}$/.test(t)) return t;
                }
                for (const sel of ['h1','h2','h3','.name','[class*="name"]','[class*="title"]']) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const t = el.textContent.trim();
                        const m = t.match(/[\\u4e00-\\u9fff]{2,4}/);
                        if (m && t.length <= 40) return t.split(/\\s|-|–|—|\\||｜|：|:/)[0].trim();
                    }
                }
                return '';
            }""")
            if name:
                result["姓名"] = name

        # 提取职称
        titles_found = []
        for t in ["教授", "副教授", "讲师", "助理教授", "研究员", "副研究员",
                   "博导", "硕导", "院士", "博士后", "工程师", "实验师",
                   "高级工程师", "教授级高工"]:
            if t in page_text[:800]:
                titles_found.append(t)
        if titles_found:
            result["职称"] = "、".join(titles_found[:3])

    except Exception:
        pass

    return result


async def scrape_department(browser, dept_name: str, seed_urls: list[str],
                            sem: asyncio.Semaphore) -> list[dict]:
    """爬取一个学院的所有教师"""
    results = []
    seen_urls = set()
    seen_emails = set()

    async with sem:
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        try:
            print(f"\n{'='*50}")
            print(f"🔍 [{dept_name}]")

            for seed_url in seed_urls:
                try:
                    await page.goto(seed_url, wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    continue
                await asyncio.sleep(0.5)

                base_domain = urlparse(seed_url).netloc
                links = await collect_links(page)

                # 筛选教师链接
                candidate_urls = set()
                for link in links:
                    text = link["text"]
                    url = link["href"]
                    if base_domain not in url:
                        continue

                    # 跳过导航
                    is_nav = False
                    for kw in NAV_KW:
                        if kw in text:
                            is_nav = True
                            break
                    if is_nav:
                        continue

                    # 保留含中文姓名的链接
                    name = extract_name_from_text(text)
                    if looks_like_teacher_name(text):
                        candidate_urls.add(url)

                print(f"  📄 {seed_url.split('/')[-2] or seed_url} → 候选教师: {len(candidate_urls)}")

                # 访问每个教师详情页（限制每学院50人）
                for url in list(candidate_urls)[:50]:
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    default_name = extract_name_from_text(
                        urlparse(url).path.split("/")[-1].replace(".htm", "").replace(".html", "")
                    )
                    info = await scrape_teacher_detail(page, url, dept_name, default_name)

                    if info["邮箱"] and info["邮箱"] not in seen_emails:
                        seen_emails.add(info["邮箱"])
                        results.append(info)
                        print(f"    ✅ {info['姓名']} → {info['邮箱']}")
                    elif not info["邮箱"]:
                        results.append(info)

        except Exception as e:
            print(f"  ❌ [{dept_name}] 错误: {e}")
        finally:
            await context.close()

    return results


async def main():
    print("=" * 60)
    print("🎓 测试1 — 南京大学教师邮箱爬取")
    print(f"📁 输出目录: {OUTPUT_DIR}")
    print("=" * 60)

    sem = asyncio.Semaphore(4)
    all_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        for dept_config in DEPT_CONFIGS:
            results = await scrape_department(
                browser, dept_config["name"], dept_config["urls"], sem
            )
            all_results.extend(results)
            print(f"  📊 [{dept_config['name']}] 共: {len(results)} 人")

        await browser.close()

    # 统计
    total = len(all_results)
    has_email = sum(1 for r in all_results if r["邮箱"])
    print(f"\n{'='*60}")
    print(f"📊 总计: {total} 位教师, 有邮箱: {has_email} 人")

    # 保存 CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"南京大学_教师邮箱_raw.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["姓名", "邮箱", "学院", "职称", "主页链接"])
        writer.writeheader()
        writer.writerows(all_results)

    print(f"💾 已保存: {csv_path}")
    return csv_path


if __name__ == "__main__":
    asyncio.run(main())
