"""南京理工大学计算机学院教师邮箱爬取 v2 — 使用 Playwright 浏览器自动化。

策略:
  1. 通过 API 获取学院列表（已知计算机学院 collegeId=7）
  2. 用 Playwright 打开教师列表页，等待 AJAX 加载完成
  3. 提取所有教师姓名和详情页链接
  4. 逐个访问详情页提取邮箱
"""

import asyncio
import re
import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "outputs" / "njust_cs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PAGE_TIMEOUT = 30000
PROFILE_TIMEOUT = 15000
MAX_TEACHERS = 200

HEADERS = ["序号", "姓名", "邮箱", "学院", "职称", "主页链接"]

# 学院公共邮箱特征
ADMIN_PREFIXES = [
    "webmaster", "admin", "office", "info", "master", "root", "postmaster",
    "bgs", "dangzheng", "yuanban", "wxyxz", "xwcb",
]


def _extract_emails(text: str) -> list[str]:
    pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    return list(set(re.findall(pattern, text)))


def _parse_at_sign(text: str) -> str:
    text = re.sub(r"\s*\[at\]\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(at\)\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*#@\s*", "@", text)
    text = re.sub(r"\s*\[@\]\s*", "@", text)
    text = re.sub(r"\s*\(@\)\s*", "@", text)
    return text


def _is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email))


def _is_admin_email(email: str) -> bool:
    el = email.lower()
    for p in ADMIN_PREFIXES:
        if el.startswith(p + "@"):
            return True
    return False


def _extract_title(text: str) -> str:
    titles = [
        "教授", "副教授", "助理教授", "讲师", "研究员", "副研究员",
        "助理研究员", "工程师", "高级工程师", "院士",
        "长江学者", "杰青", "优青", "青年教授",
    ]
    found = [t for t in titles if t in text]
    return max(found, key=len) if found else ""


async def main():
    from playwright.async_api import async_playwright

    all_teachers = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        # === 步骤1：打开计算机学院教师列表页 ===
        org_name = quote("计算机科学与技术学院", safe="")
        list_url = (
            f"https://teacher.njust.edu.cn/94/list.htm"
            f"?wp_tw_orgId=7"
            f"&wp_tw_displayStyle=2"
            f"&wp_tw_complete=1"
            f"&wp_tw_orgName={org_name}"
        )

        logger.info(f"📌 打开教师列表: {list_url}")
        await page.goto(list_url, wait_until="networkidle", timeout=PAGE_TIMEOUT)
        await asyncio.sleep(3)

        # 截图验证
        await page.screenshot(path=str(OUTPUT_DIR / "list_page.png"))
        logger.info("已截图保存: list_page.png")

        # 获取页面内容
        body_text = await page.evaluate("() => document.body.innerText")
        logger.info(f"页面文本长度: {len(body_text)}")

        # === 步骤2：尝试多个策略提取教师列表 ===
        teacher_entries = []

        # 策略A：等待 AJAX 加载后查找教师卡片/链接
        await asyncio.sleep(3)  # 再等等 AJAX

        # 尝试截取 AJAX 请求和响应
        teacher_entries = await page.evaluate("""() => {
            const entries = [];
            const seen = new Set();

            // 查找教师卡片（通常是 news_box / news_title 结构）
            document.querySelectorAll('.news_box, .news, .news_title a, .teacher-item, .teacher-card').forEach(el => {
                const a = el.tagName === 'A' ? el : el.querySelector('a');
                if (!a || !a.href) return;
                const text = a.textContent.trim();
                if (text.length >= 2 && text.length <= 20 && !seen.has(a.href)) {
                    seen.add(a.href);
                    entries.push({name: text, url: a.href});
                }
            });

            // 如果没找到，尝试所有合理的链接
            if (entries.length === 0) {
                document.querySelectorAll('a').forEach(a => {
                    const text = a.textContent.trim();
                    const href = a.href;
                    if (!href || seen.has(href)) return;
                    if (text.length >= 2 && text.length <= 15 &&
                        !['首页','返回','登录','帮助','更多','查看','English'].includes(text)) {
                        seen.add(href);
                        entries.push({name: text, url: href});
                    }
                });
            }

            return entries;
        }""")

        logger.info(f"策略A: 找到 {len(teacher_entries)} 个条目")

        # 策略B：如果上面没找到教师，尝试翻页按钮或直接解析AJAX响应
        if len(teacher_entries) < 10:
            # 尝试监听 XHR 响应
            logger.info("尝试策略B: 拦截 AJAX 响应...")

            # 直接在页面中获取通过 AJAX 注入的HTML
            html_after = await page.evaluate("""() => {
                const container = document.querySelector('#searchTea');
                return container ? container.innerHTML.slice(0, 3000) : 'NO CONTAINER';
            }""")
            logger.info(f"searchTea 内容(前3000): {html_after[:500]}")

            # Check for other containers
            all_html = await page.evaluate("""() => {
                const ids = ['searchTea', 'news_list', 'teach_list', 'wp-paralist', 'search_list'];
                const result = {};
                ids.forEach(id => {
                    const el = document.getElementById(id) || document.querySelector('.' + id);
                    result[id] = el ? el.innerHTML.length : -1;
                });
                return result;
            }""")
            logger.info(f"容器状态: {json.dumps(all_html)}")

            # 尝试在页面上找到所有可见文字来验证
            visible_text = await page.evaluate("""() => {
                return document.body.innerText.slice(0, 2000);
            }""")
            logger.info(f"可见文本:\n{visible_text}")

        # === 步骤3：访问详情页提取邮箱 ===
        logger.info(f"\n开始处理 {len(teacher_entries[:MAX_TEACHERS])} 位教师...")

        for i, entry in enumerate(teacher_entries[:MAX_TEACHERS]):
            name = entry["name"]
            profile_url = entry["url"]

            # 跳过明显不是教师页面的链接
            skip_patterns = ["login.jsp", "main.htm", "main.psp", "javascript:", "#"]
            if any(p in profile_url for p in skip_patterns):
                continue

            logger.info(f"  [{i+1}/{len(teacher_entries[:MAX_TEACHERS])}] {name} → {profile_url[:100]}")

            try:
                profile_page = await context.new_page()
                try:
                    await profile_page.goto(profile_url, wait_until="domcontentloaded", timeout=PROFILE_TIMEOUT)
                    await asyncio.sleep(1.5)

                    profile_text = await profile_page.evaluate("() => document.body.innerText")
                    profile_text = _parse_at_sign(profile_text)

                    emails = _extract_emails(profile_text)
                    valid_emails = [e for e in emails if _is_valid_email(e) and not _is_admin_email(e)]

                    title = _extract_title(profile_text)

                    if valid_emails:
                        for email in valid_emails:
                            teacher = {
                                "name": name,
                                "email": email,
                                "department": "计算机科学与工程学院",
                                "title": title,
                                "url": profile_url,
                            }
                            all_teachers.append(teacher)
                            logger.info(f"    ✅ {name} <{email}> [{title}]")
                    else:
                        logger.info(f"    ⚠️ {name} — 无个人邮箱")
                        # 仍然记录，但邮箱为空
                        teacher = {
                            "name": name,
                            "email": "",
                            "department": "计算机科学与工程学院",
                            "title": title,
                            "url": profile_url,
                        }
                        all_teachers.append(teacher)
                finally:
                    await profile_page.close()
            except Exception as e:
                logger.warning(f"    ❌ 失败 {name}: {str(e)[:100]}")

        await context.close()
        await browser.close()

    # === 去重 ===
    seen = set()
    unique = []
    for t in all_teachers:
        key = (t["email"], t["name"])
        if key not in seen:
            seen.add(key)
            unique.append(t)

    logger.info(f"\n{'='*60}")
    logger.info(f"总计: {len(unique)} 位教师（去重后）")
    with_email = [t for t in unique if t["email"]]
    logger.info(f"有邮箱: {len(with_email)} 位")
    logger.info(f"无邮箱: {len(unique) - len(with_email)} 位")

    # === 导出 CSV ===
    if unique:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = OUTPUT_DIR / f"南京理工大学_计算机学院_教师邮箱_{ts}.csv"

        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(HEADERS)
            for i, t in enumerate(unique, 1):
                writer.writerow([
                    i, t["name"], t["email"], t["department"], t["title"], t["url"]
                ])

        logger.info(f"CSV 已保存: {csv_path}")

        # 打印统计
        titles = {}
        for t in unique:
            title = t.get("title", "未知")
            titles[title] = titles.get(title, 0) + 1
        logger.info("职称分布:")
        for title, count in sorted(titles.items(), key=lambda x: -x[1]):
            logger.info(f"  {title}: {count}人")

        # 预览
        logger.info("前20条:")
        for t in unique[:20]:
            logger.info(f"  {t['name']} <{t['email']}> [{t['title']}]")

    return unique


if __name__ == "__main__":
    asyncio.run(main())
