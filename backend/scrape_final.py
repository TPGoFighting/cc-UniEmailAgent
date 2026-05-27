"""
最后一轮快速清理 + 补抓小脚本
只针对问题最严重的学院
"""
import asyncio
import csv
import re
import os
from datetime import datetime
from playwright.async_api import async_playwright

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

# 公共邮箱
PUBLIC_SET = {
    'history@nju.edu.cn', 'imnju@nju.edu.cn', 'sxydw@nju.edu.cn',
    'webmaster@nju.edu.cn', 'xgdw@nju.edu.cn',
    'zhanghao@nju.edu.cn', 'fxshen@nju.edu.cn', 'wangyuxuan@nju.edu.cn',
    'office@nju.edu.cn', 'info@nju.edu.cn', 'admin@nju.edu.cn',
}


def extract_personal_email(page_text):
    # 优先邮箱标签
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

    # 恢复反爬
    text = re.sub(r'\[at\]|\(at\)|#@|\[@\]', '@', page_text, flags=re.IGNORECASE)
    text = re.sub(r'\s*@\s*', '@', text)
    all_emails = EMAIL_RE.findall(text)
    for email in all_emails:
        email_lower = email.lower()
        if email_lower not in PUBLIC_SET:
            return email_lower
    return ""


async def scrape_history_college(browser):
    """历史学院 - 直接从教师名录表页获取"""
    print("\n=== 历史学院 ===")
    context = await browser.new_context(viewport={"width": 1280, "height": 900})
    page = await context.new_page()
    results = []

    # 历史学院的教师列表页有这些子页面
    sub_pages = [
        "https://history.nju.edu.cn/28475/list.htm",  # 教师名录
        "https://history.nju.edu.cn/28475/list2.htm",  # 第2页
        "https://history.nju.edu.cn/28475/list3.htm",
        "https://history.nju.edu.cn/28475/list4.htm",
    ]

    teacher_links = []
    for sp in sub_pages:
        try:
            await page.goto(sp, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

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
                # 教师姓名：2-4个汉字
                if re.match(r'^[一-鿿·]{2,4}$', text) and 'history.nju.edu.cn' in href:
                    if href not in {t['href'] for t in teacher_links}:
                        teacher_links.append({"name": text, "href": href})

            print(f"  {sp} → +{len(teacher_links)} 教师链接")
        except Exception as e:
            print(f"  {sp} 失败: {e}")

    print(f"  共 {len(teacher_links)} 个教师")

    for i, t in enumerate(teacher_links):
        try:
            await page.goto(t["href"], wait_until="networkidle", timeout=20000)
            await asyncio.sleep(0.6)

            page_text = await page.evaluate("() => document.body?.innerText || ''")
            email = extract_personal_email(page_text)
            title = ""
            for tt in ['教授', '副教授', '助理教授', '讲师']:
                if tt in page_text[:3000]:
                    title = tt
                    break

            if email:
                results.append({"姓名": t["name"], "邮箱": email, "学院": "历史学院", "职称": title, "主页链接": t["href"]})
                print(f"  ✓ [{i+1}] {t['name']} → {email}")
            else:
                print(f"  ✗ [{i+1}] {t['name']} 无邮箱")
        except Exception as e:
            pass

    await context.close()
    print(f"  历史学院: {len(results)} 人")
    return results


async def scrape_chem_college(browser):
    """化学化工学院"""
    print("\n=== 化学化工学院 ===")
    context = await browser.new_context(viewport={"width": 1280, "height": 900})
    page = await context.new_page()
    results = []

    # 化学化工学院教师个人页面的列表URL
    # 从szll页面进入子分类
    await page.goto("https://chem.nju.edu.cn/szll/list.htm", wait_until="networkidle", timeout=30000)
    await asyncio.sleep(2)

    # 获取所有教师个人链接
    links = await page.evaluate("""() => {
        const links = document.querySelectorAll('a[href]');
        return Array.from(links).map(a => ({
            text: (a.textContent || '').trim(),
            href: a.href
        }));
    }""")

    teacher_links = []
    seen = set()
    for link in links:
        text = link["text"]
        href = link["href"]
        # chem.nju.edu.cn/xxx/list.htm 格式的个人页面
        if re.match(r'^[一-鿿·]{2,4}$', text) and 'chem.nju.edu.cn' in href:
            if href not in seen:
                seen.add(href)
                teacher_links.append({"name": text, "href": href})

    # 如果不够，找子目录链接
    if len(teacher_links) < 20:
        print(f"  第一轮: {len(teacher_links)} 个, 探索子目录...")
        for link in links:
            if any(kw in link["text"] for kw in ['教授', '副教授', '讲师', '教师']) and 'chem.nju.edu.cn' in link["href"]:
                try:
                    await page.goto(link["href"], wait_until="networkidle", timeout=20000)
                    await asyncio.sleep(1)
                    sub_links = await page.evaluate("""() => {
                        const links = document.querySelectorAll('a[href]');
                        return Array.from(links).map(a => ({
                            text: (a.textContent || '').trim(),
                            href: a.href
                        }));
                    }""")
                    for sl in sub_links:
                        if re.match(r'^[一-鿿·]{2,4}$', sl["text"]) and 'chem.nju.edu.cn' in sl["href"]:
                            if sl["href"] not in seen:
                                seen.add(sl["href"])
                                teacher_links.append({"name": sl["text"], "href": sl["href"]})
                except:
                    pass

    print(f"  共 {len(teacher_links)} 个教师")

    for i, t in enumerate(teacher_links):
        try:
            await page.goto(t["href"], wait_until="networkidle", timeout=20000)
            await asyncio.sleep(0.6)
            page_text = await page.evaluate("() => document.body?.innerText || ''")
            email = extract_personal_email(page_text)
            title = ""
            for tt in ['教授', '副教授', '助理教授', '讲师', '研究员', '院士']:
                if tt in page_text[:3000]:
                    title = tt
                    break

            if email:
                results.append({"姓名": t["name"], "邮箱": email, "学院": "化学化工学院", "职称": title, "主页链接": t["href"]})
                print(f"  ✓ [{i+1}] {t['name']} → {email}")
            else:
                print(f"  ✗ [{i+1}] {t['name']} 无邮箱")

            if len(results) >= 20:
                break
        except Exception as e:
            pass

    await context.close()
    print(f"  化学化工学院: {len(results)} 人")
    return results


async def main():
    print("最后一轮快速补抓")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        history_results = await scrape_history_college(browser)
        chem_results = await scrape_chem_college(browser)

        await browser.close()

    # 保存
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(OUTPUT_DIR, f"南京大学_最后一轮补抓_{timestamp}.csv")
    all_results = history_results + chem_results

    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=["姓名", "邮箱", "学院", "职称", "主页链接"])
        writer.writeheader()
        for r in all_results:
            writer.writerow(r)

    print(f"\n保存: {csv_path}")
    print(f"历史学院: {len(history_results)} 人")
    print(f"化学化工: {len(chem_results)} 人")
    print(f"总计: {len(all_results)} 人")


if __name__ == "__main__":
    asyncio.run(main())
