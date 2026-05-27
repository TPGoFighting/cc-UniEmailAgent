"""北京邮电大学教师邮箱爬取 — 多策略反爬绕过 (修复版)"""

import asyncio
import csv
import re
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PAGE_TIMEOUT = 60000
PROFILE_TIMEOUT = 15000


def extract_emails(text: str) -> list[str]:
    return list(set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)))


def is_admin_email(email: str) -> bool:
    email_l = email.lower()
    for pat in [r"^webmaster@", r"^admin@", r"^office@", r"^info@",
                r"^master@", r"^root@", r"^postmaster@", r"^bgs@"]:
        if re.match(pat, email_l):
            return True
    for pf in ["wxyxz", "xwcb", "office", "yuanban", "bgs"]:
        if email_l.startswith(pf + "@"):
            return True
    return False


def parse_at_sign(text: str) -> str:
    for pat, repl in [(r"\s*\[at\]\s*", "@"), (r"\s*\(at\)\s*", "@"),
                       (r"\s*#@\s*", "@"), (r"\s*\[@\]\s*", "@"), (r"\s*\(@\)\s*", "@")]:
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
    return text


async def crawl_with_stealth():
    """使用 Chromium + playwright-stealth"""
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    output_dir = Path(__file__).parent / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_teachers = []
    errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="zh-CN",
        )
        page = await context.new_page()

        # Apply stealth
        stealth = Stealth()
        await stealth.apply_stealth_async(page)

        try:
            # ——— 访问计算机学院师资页面 ———
            logger.info("=== Chrome+Stealth: 访问计算机学院师资页面 ===")
            resp = await page.goto("https://scs.bupt.edu.cn/szjs1.htm", wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
            logger.info(f"HTTP 状态: {resp.status}")

            # 关键: 等待 JS 挑战完成
            await asyncio.sleep(10)

            body_text = await page.evaluate("() => document.body?.innerText || ''")
            html = await page.content()
            title = await page.title()
            logger.info(f"标题: '{title}'")
            logger.info(f"文本长度: {len(body_text)}, HTML长度: {len(html)}")

            if len(body_text) < 50:
                logger.warning(f"⚠️ 页面内容过少，反爬未突破")
                logger.info(f"HTML 前 1500 字符:\n{html[:1500]}")
                # 保存 HTML 供检查
                with open(output_dir / f"bupt_blocked_{ts}.html", "w", encoding="utf-8") as f:
                    f.write(html)
                await browser.close()
                return

            logger.info(f"✅ 成功突破反爬! 文本前 500 字符:\n{body_text[:500]}")

            # ——— 提取链接 ———
            links = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a')).map(a => ({
                    text: (a.textContent||'').trim().substring(0, 80),
                    href: (a.href || '')
                })).filter(l => l.text && l.href && !l.href.startsWith('javascript:'));
            }""")

            logger.info(f"发现 {len(links)} 个链接")

            # 分类
            center_links = []
            teacher_names = []
            all_other = []

            nav_kw = ["概况", "简介", "新闻", "通知", "公告", "招生", "培养",
                      "就业", "学位", "学科", "党建", "工会", "校友", "捐赠",
                      "首页", "返回", "copyright", "登录", "English"]

            for l in links:
                text = l["text"]
                if any(kw in text for kw in ["中心", "研究所", "实验室", "师资", "教师", "导师", "教授"]):
                    center_links.append(l)
                elif re.match(r"^[一-鿿]{2,4}$", text) and not any(kw in text for kw in nav_kw):
                    teacher_names.append(l)
                else:
                    all_other.append(l)

            logger.info(f"\n=== 链接分类 ===")
            logger.info(f"研究中心/师资: {len(center_links)}")
            for l in center_links[:20]:
                logger.info(f"  [{l['text']}] → {l['href']}")

            logger.info(f"\n教师姓名链接: {len(teacher_names)}")
            for l in teacher_names[:30]:
                logger.info(f"  [{l['text']}] → {l['href']}")

            logger.info(f"\n其他链接: {len(all_other)}")
            for l in all_other[:30]:
                logger.info(f"  [{l['text']}] → {l['href']}")

            # ——— 策略A: 如果找到研究中心链接，从各中心爬取 ———
            if center_links:
                logger.info(f"\n{'='*60}")
                logger.info(f"策略A: 遍历 {min(len(center_links), 15)} 个研究中心")
                logger.info(f"{'='*60}")

                for i, cl in enumerate(center_links[:15]):
                    cname = cl["text"]
                    curl = cl["href"]
                    logger.info(f"\n[{i+1}] 访问: {cname}")

                    try:
                        await page.goto(curl, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                        await asyncio.sleep(5)

                        ct = await page.evaluate("() => document.body?.innerText || ''")
                        logger.info(f"  文本长度: {len(ct)}")

                        if len(ct) < 30:
                            logger.warning(f"  页面加载失败(反爬)")
                            continue

                        # 提取教师姓名链接
                        names = await page.evaluate("""() => {
                            const results = [];
                            const seen = new Set();
                            document.querySelectorAll('a').forEach(a => {
                                const t = (a.textContent||'').trim();
                                const h = a.href;
                                if (!h || seen.has(h)) return;
                                if (/^[\\u4e00-\\u9fff]{2,4}$/.test(t) && t.length >= 2) {
                                    seen.add(h);
                                    results.push({name: t, url: h});
                                }
                            });
                            return results.slice(0, 50);
                        }""")

                        logger.info(f"  找到 {len(names)} 个教师姓名")

                        # 访问教师详情页
                        for j, entry in enumerate(names[:25]):
                            name = entry["name"]
                            profile_url = entry["url"]

                            try:
                                pp = await context.new_page()
                                try:
                                    await pp.goto(profile_url, wait_until="domcontentloaded",
                                                 timeout=PROFILE_TIMEOUT)
                                    await asyncio.sleep(1)

                                    ptext = await pp.evaluate("() => document.body?.innerText || ''")
                                    ptext = parse_at_sign(ptext)

                                    emails = [e for e in extract_emails(ptext) if not is_admin_email(e)]

                                    if emails:
                                        title = ""
                                        for tk in ["教授", "副教授", "助理教授", "讲师",
                                                   "研究员", "副研究员", "院士", "博导", "硕导"]:
                                            if tk in ptext:
                                                title = tk
                                                break

                                        all_teachers.append({
                                            "name": name, "email": emails[0],
                                            "department": cname, "title": title,
                                            "url": profile_url,
                                        })
                                        logger.info(f"    ✅ {name} → {emails[0]} [{title}]")
                                    else:
                                        pass  # 静默跳过无邮箱的
                                finally:
                                    await pp.close()
                            except Exception:
                                pass

                    except Exception as e:
                        logger.error(f"  中心页面失败: {str(e)[:100]}")
                        errors.append(f"{cname}: {str(e)[:100]}")

            # ——— 策略B: 如果有直接教师姓名链接，查看详情 ———
            if teacher_names and not all_teachers:
                logger.info(f"\n{'='*60}")
                logger.info(f"策略B: 遍历 {len(teacher_names)} 个教师姓名")
                logger.info(f"{'='*60}")

                for entry in teacher_names[:50]:
                    name = entry["name"]
                    profile_url = entry["href"]
                    try:
                        pp = await context.new_page()
                        try:
                            await pp.goto(profile_url, wait_until="domcontentloaded",
                                         timeout=PROFILE_TIMEOUT)
                            await asyncio.sleep(0.8)

                            ptext = await pp.evaluate("() => document.body?.innerText || ''")
                            ptext = parse_at_sign(ptext)

                            emails = [e for e in extract_emails(ptext) if not is_admin_email(e)]

                            if emails:
                                title = ""
                                for tk in ["教授", "副教授", "助理教授", "讲师",
                                           "研究员", "副研究员", "院士", "博导", "硕导"]:
                                    if tk in ptext:
                                        title = tk
                                        break

                                all_teachers.append({
                                    "name": name, "email": emails[0],
                                    "department": "计算机学院", "title": title,
                                    "url": profile_url,
                                })
                                logger.info(f"  ✅ {name} → {emails[0]} [{title}]")
                        finally:
                            await pp.close()
                    except Exception:
                        pass

            # ——— 保存结果 ———
            logger.info(f"\n{'='*60}")
            logger.info(f"爬取完成: {len(all_teachers)} 位教师")
            logger.info(f"{'='*60}")

            if all_teachers:
                # 去重
                seen = set()
                unique = []
                for t in all_teachers:
                    if t["email"] not in seen:
                        seen.add(t["email"])
                        unique.append(t)
                logger.info(f"去重后: {len(unique)} 位")

                csv_path = output_dir / f"北京邮电大学_计算机学院_教师邮箱_{ts}.csv"
                with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=["姓名", "邮箱", "学院", "职称", "主页链接"])
                    writer.writeheader()
                    writer.writerows(unique)
                logger.info(f"✅ CSV 已保存: {csv_path}")

                for t in unique[:15]:
                    logger.info(f"  {t['name']} <{t['email']}> [{t['department']}] {t['title']}")
            else:
                logger.warning("❌ 未能提取到任何教师邮箱")

            if errors:
                err_path = output_dir / f"北京邮电大学_error_{ts}.log"
                with open(err_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(errors))
                logger.info(f"错误日志: {err_path}")

            # 截图
            await page.screenshot(path=str(output_dir / f"bupt_result_{ts}.png"))

        except Exception as e:
            logger.error(f"致命错误: {e}", exc_info=True)
        finally:
            await browser.close()

    return all_teachers


async def main():
    teachers = await crawl_with_stealth()
    if teachers:
        logger.info(f"\n最终结果: {len(teachers)} 位教师")
    else:
        logger.info("\n⚠️  爬取失败 - 需要进一步调整反爬策略")


if __name__ == "__main__":
    asyncio.run(main())
