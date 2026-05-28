"""诊断东南大学问题学院 — 查看列表页实际结构"""
import asyncio
import re
import sys
from playwright.async_api import async_playwright

PROBLEM_DEPTS = [
    ("土木工程学院", ["https://civil.seu.edu.cn/10475/list.htm", "https://civil.seu.edu.cn/szdw/list.htm"]),
    ("机械工程学院", ["https://me.seu.edu.cn/szll/list.htm", "https://me.seu.edu.cn/21792/list.htm"]),
    ("能源与环境学院", ["http://power.seu.edu.cn/9216/list.htm", "http://power.seu.edu.cn/9226/list.htm"]),
    ("电子科学与工程学院", ["http://electronic.seu.edu.cn/szllx/list.htm", "https://electronic.seu.edu.cn/27342/list.htm"]),
    ("外国语学院", ["https://sfl.seu.edu.cn/9851/list.htm", "https://sfl.seu.edu.cn/szdw/list.htm"]),
    ("生物科学与医学工程学院", ["https://bme.seu.edu.cn/499/list.htm", "https://bme.seu.edu.cn/szdw/list.htm"]),
    ("化学化工学院", ["https://chem.seu.edu.cn/js/list.htm", "https://chem.seu.edu.cn/szdw/list.htm"]),
    ("仪器科学与工程学院", ["https://ins.seu.edu.cn/45076/list.htm", "https://ins.seu.edu.cn/szdw/list.htm"]),
    ("艺术学院", ["https://arts.seu.edu.cn/szdw_25730/list.htm", "https://arts.seu.edu.cn/25733/list.htm"]),
    ("法学院", ["https://law.seu.edu.cn/9121/list.htm", "https://law.seu.edu.cn/szdw/list.htm"]),
    ("医学院", ["https://med.seu.edu.cn/8693/list.htm", "https://med.seu.edu.cn/szdw/list.htm"]),
    ("吴健雄学院", ["https://wjx.seu.edu.cn/21376/list.htm"]),
    ("马克思主义学院", ["https://marxism.seu.edu.cn/23294/list.htm", "https://marxism.seu.edu.cn/szdw/list.htm"]),
    ("统计与数据科学学院", ["https://stat.seu.edu.cn/szll_61997/list.htm"]),
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

async def diagnose(context, dept_name, urls):
    print(f"\n{'='*60}")
    print(f"【{dept_name}】")
    page = await context.new_page()
    for url in urls:
        try:
            print(f"  尝试: {url}")
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            status = resp.status if resp else "N/A"
            await asyncio.sleep(2)

            # 获取所有链接
            links = await page.evaluate("""() => {
                const links = [];
                document.querySelectorAll('a').forEach(a => {
                    const text = a.textContent.trim().substring(0, 50);
                    const href = a.href || '';
                    if (href && !href.startsWith('javascript:') && href !== '#') {
                        links.push({text, href: href.substring(0, 120)});
                    }
                });
                return links;
            }""")

            # 检查可能的中文人名链接 (2-4个汉字)
            cn_name_links = []
            for l in links:
                text = l["text"].strip()
                if re.match(r'^[一-鿿]{2,4}$', text):
                    cn_name_links.append(l)

            # 也查找包含"教师"、"教授"、"师资"等关键词的链接
            teacher_links = [l for l in links if any(kw in l["text"] for kw in ["教授","教师","师资","导师","博士","讲师","研究员","工程师","博导","硕导","人才"])]

            # 检查页面中的邮箱
            body = await page.evaluate("() => document.body.innerText")
            emails = EMAIL_RE.findall(body)

            # 查找教师列表区域
            has_teacher_section = await page.evaluate("""() => {
                const body = document.body.innerText;
                return body.includes('教师') || body.includes('师资') || body.includes('教授') || body.includes('导师');
            }""")

            print(f"    HTTP状态: {status}, 总链接数: {len(links)}")
            print(f"    中文姓名链接: {len(cn_name_links)}")
            print(f"    教师相关链接: {len(teacher_links)}")
            print(f"    页面邮箱数: {len(emails)}")
            print(f"    含教师关键词: {has_teacher_section}")

            if cn_name_links:
                print(f"    示例姓名链接: {cn_name_links[:5]}")

            if teacher_links:
                print(f"    教师相关链接样本: {teacher_links[:5]}")

            if emails:
                print(f"    示例邮箱: {emails[:5]}")

            # 如果找到了人名链接，说明这个URL有效
            if len(cn_name_links) >= 3:
                print(f"    ✅ 有效URL: {url}")

        except Exception as e:
            print(f"    ❌ 错误: {e}")

    await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        )
        for dept_name, urls in PROBLEM_DEPTS:
            await diagnose(context, dept_name, urls)
        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
