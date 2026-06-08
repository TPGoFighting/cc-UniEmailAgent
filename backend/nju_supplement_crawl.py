"""
南京大学增量爬取脚本 — 专门补爬邮箱率低的学院
"""
import asyncio
import re
import csv
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path(r"D:\Work\test\UniEmailAgent\backend\outputs\a468ea4c-1347-4a08-adc8-696eb43df27c")
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# 邮箱恢复
def restore_email(text):
    text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
    text = text.replace('[@]', '@').replace('(#)', '@')
    text = re.sub(r'(\w)#(\w)', r'\1@\2', text)  # wyb#nju.edu.cn -> wyb@nju.edu.cn
    return text

async def crawl_gov_school(context):
    """政府管理学院 — 所有数据在一页上"""
    print("📋 爬取: 政府管理学院")
    results = []
    page = await context.new_page()
    try:
        url = "https://public.nju.edu.cn/szdw/qzjs/azy/index.html"
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        # 获取页面完整文本
        text = await page.evaluate('() => document.body.innerText')
        text = restore_email(text)

        # 解析教师条目
        # 格式: "姓名 职称\n\n系别：xxx\n\n研究领域：xxx\n\n电子邮件：xxx@..."
        # 用分块解析
        rows = await page.evaluate('''() => {
            const items = [];
            // 找所有系别标题 (h3/h4 or strong)
            const dept_sections = document.querySelectorAll('.content, .main, .article, .entry');
            const main = document.querySelector('.content, .main, .article, .entry, #content, #main');
            const root = main || document.body;

            // Get all text blocks with teacher info
            const blocks = root.innerText.split('\\n\\n');
            return blocks.filter(b => b.trim().length > 0).slice(0, 500);
        }''')

        # More targeted extraction using JavaScript
        teachers = await page.evaluate('''() => {
            const all_text = document.body.innerText;
            const lines = all_text.split('\\n');
            const teachers = [];
            let current_dept = '';

            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim();
                // Detect department headers
                if (/系$/.test(line) && line.length < 10) {
                    current_dept = line;
                    continue;
                }
                // Detect teacher name line: Chinese name followed by title
                const nameMatch = line.match(/^([\\u4e00-\\u9fff]{2,4})\\s+(.+)$/);
                if (nameMatch) {
                    const name = nameMatch[1];
                    const title = nameMatch[2].trim();
                    // Collect email from following lines
                    let email = '';
                    for (let j = i + 1; j < Math.min(i + 10, lines.length); j++) {
                        const nextLine = lines[j].trim();
                        const emailMatch = nextLine.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/);
                        if (emailMatch) {
                            email = emailMatch[0].toLowerCase();
                            break;
                        }
                    }
                    // Skip navigation keywords
                    const navKws = ['概况','新闻','通知','公告','招生','联系我们','首页','返回','更多','下载','党建','工会','校友'];
                    if (!navKws.some(k => name.includes(k))) {
                        teachers.push({name, title, email, dept: current_dept});
                    }
                }
            }
            return teachers;
        }''')

        print(f"  找到 {len(teachers)} 位教师")
        for t in teachers[:5]:
            print(f"    {t['name']} | {t['title']} | {t['email'] or '❌无'} | {t['dept']}")

        for t in teachers:
            if t['email']:
                results.append({
                    'name': t['name'],
                    'email': t['email'].lower(),
                    'department': '政府管理学院',
                    'title': t['title'],
                    'url': url
                })
            else:
                results.append({
                    'name': t['name'],
                    'email': '',
                    'department': '政府管理学院',
                    'title': t['title'],
                    'url': url
                })

        print(f"  ✅ 政府管理学院: {len(results)} 条, {sum(1 for r in results if r['email'])} 邮箱")
    except Exception as e:
        print(f"  ❌ 政府管理学院: {e}")
    finally:
        await page.close()
    return results


async def crawl_dafls(context, school_name, department):
    """外国语学院 + 大学外语部 — 共用 dafls.nju.edu.cn 教师系统"""
    print(f"📋 爬取: {school_name}")
    results = []
    page = await context.new_page()
    try:
        # 先获取教师列表页（从sfs或dwb的szdw入口）
        if school_name == "外国语学院":
            list_url = "https://sfs.nju.edu.cn/szdw/yyx/index.html"
        else:
            list_url = "https://dafls.nju.edu.cn/szdw/js/list.htm"

        await page.goto(list_url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        # 获取所有教师链接
        teacher_links = await page.evaluate('''() => {
            const links = [];
            document.querySelectorAll('a[href*="page.htm"]').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href;
                if (text && /^[\\u4e00-\\u9fff]{2,4}$/.test(text)) {
                    links.push({name: text, url: href});
                }
            });
            return links;
        }''')

        print(f"  找到 {len(teacher_links)} 位教师")

        # 进入每个教师详情页
        for i, teacher in enumerate(teacher_links):
            try:
                dp = await context.new_page()
                await dp.goto(teacher['url'], wait_until='domcontentloaded', timeout=15000)
                await asyncio.sleep(0.5)

                body = await dp.evaluate('() => document.body.innerText')
                body = restore_email(body)
                emails = EMAIL_RE.findall(body)

                # 提取职称
                title = ''
                title_kw = ['教授','副教授','讲师','研究员','工程师','博导','硕导','助理教授','博士后','实验师']
                for kw in title_kw:
                    if kw in body[:1000]:
                        # Find the closest title word
                        pass

                title = await page.evaluate('''() => {
                    const body = document.body.innerText.substring(0, 2000);
                    const kws = ['教授','副教授','助理教授','讲师','研究员','副研究员','工程师','高级工程师','博导','硕导'];
                    for (const kw of kws) {
                        if (body.includes(kw)) return kw;
                    }
                    return '';
                }''')

                email = emails[0].lower() if emails else ''

                results.append({
                    'name': teacher['name'],
                    'email': email,
                    'department': department,
                    'title': title,
                    'url': teacher['url']
                })

                if (i+1) % 10 == 0:
                    print(f"    进度: {i+1}/{len(teacher_links)}, 邮箱: {sum(1 for r in results if r['email'])}")

                await dp.close()
            except Exception as e:
                # Single teacher fail doesn't stop the whole crawl
                results.append({
                    'name': teacher['name'],
                    'email': '',
                    'department': department,
                    'title': '',
                    'url': teacher['url']
                })
                continue

        print(f"  ✅ {school_name}: {len(results)} 条, {sum(1 for r in results if r['email'])} 邮箱")
    except Exception as e:
        print(f"  ❌ {school_name}列表页: {e}")
    finally:
        await page.close()
    return results


async def crawl_history(context):
    """历史学院"""
    print("📋 爬取: 历史学院")
    results = []
    page = await context.new_page()
    try:
        await page.goto("https://history.nju.edu.cn/szdw/", wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        teacher_links = await page.evaluate('''() => {
            const links = [];
            document.querySelectorAll('a[href*="page.htm"]').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href;
                if (text && /^[\\u4e00-\\u9fff]{2,4}$/.test(text)) {
                    links.push({name: text, url: href});
                }
            });
            return links;
        }''')

        print(f"  找到 {len(teacher_links)} 位教师")

        for i, teacher in enumerate(teacher_links):
            try:
                dp = await context.new_page()
                await dp.goto(teacher['url'], wait_until='domcontentloaded', timeout=15000)
                await asyncio.sleep(0.5)

                body = await dp.evaluate('() => document.body.innerText')
                body = restore_email(body)
                emails = EMAIL_RE.findall(body)

                title = await dp.evaluate('''() => {
                    const body = document.body.innerText.substring(0, 2000);
                    const kws = ['教授','副教授','助理教授','讲师','研究员','副研究员','工程师','高级工程师','博导','硕导'];
                    for (const kw of kws) {
                        if (body.includes(kw)) return kw;
                    }
                    return '';
                }''')

                email = emails[0].lower() if emails else ''

                results.append({
                    'name': teacher['name'],
                    'email': email,
                    'department': '历史学院',
                    'title': title,
                    'url': teacher['url']
                })

                if (i+1) % 10 == 0:
                    print(f"    进度: {i+1}/{len(teacher_links)}")

                await dp.close()
            except Exception as e:
                results.append({
                    'name': teacher['name'],
                    'email': '',
                    'department': '历史学院',
                    'title': '',
                    'url': teacher['url']
                })
                continue

        print(f"  ✅ 历史学院: {len(results)} 条, {sum(1 for r in results if r['email'])} 邮箱")
    except Exception as e:
        print(f"  ❌ 历史学院: {e}")
    finally:
        await page.close()
    return results


async def crawl_chem(context):
    """化学化工学院"""
    print("📋 爬取: 化学化工学院")
    results = []
    page = await context.new_page()
    try:
        await page.goto("https://chem.nju.edu.cn/szdw/", wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        text = await page.evaluate('() => document.body.innerText')
        text = restore_email(text)
        emails_in_page = set(EMAIL_RE.findall(text))

        # The page shows teacher names with dates - check if clickable
        teachers = await page.evaluate('''() => {
            const items = [];
            document.querySelectorAll('a[href*="page.htm"], a[href*="szdw"]').forEach(a => {
                const text = a.textContent.trim();
                if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text) && a.href) {
                    items.push({name: text, url: a.href});
                }
            });
            return items;
        }''')

        print(f"  找到 {len(teachers)} 个链接, 页面内联邮箱: {len(emails_in_page)}")

        # Try each teacher link
        for i, teacher in enumerate(teachers[:50]):
            try:
                dp = await context.new_page()
                await dp.goto(teacher['url'], wait_until='domcontentloaded', timeout=15000)
                await asyncio.sleep(0.5)

                body = await dp.evaluate('() => document.body.innerText')
                body = restore_email(body)
                emails = EMAIL_RE.findall(body)

                title = await dp.evaluate('''() => {
                    const body = document.body.innerText.substring(0, 2000);
                    const kws = ['教授','副教授','助理教授','讲师','研究员','副研究员','工程师','高级工程师','博导','硕导'];
                    for (const kw of kws) {
                        if (body.includes(kw)) return kw;
                    }
                    return '';
                }''')

                email = emails[0].lower() if emails else ''

                results.append({
                    'name': teacher['name'],
                    'email': email,
                    'department': '化学化工学院',
                    'title': title,
                    'url': teacher['url']
                })
                await dp.close()
            except:
                results.append({
                    'name': teacher['name'],
                    'email': '',
                    'department': '化学化工学院',
                    'title': '',
                    'url': teacher['url']
                })
                continue

        print(f"  ✅ 化学化工学院: {len(results)} 条, {sum(1 for r in results if r['email'])} 邮箱")
    except Exception as e:
        print(f"  ❌ 化学化工学院: {e}")
    finally:
        await page.close()
    return results


async def main():
    all_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )

        # 按批次并行爬取，每次最多3个学院
        batches = [
            # 第一批：政府管理学院（单页提取）+ 历史学院（详情页）
            [crawl_gov_school(context), crawl_history(context)],
            # 第二批：外国语学院（详情页）
            [crawl_dafls(context, "外国语学院", "外国语学院")],
        ]

        for batch_idx, batch in enumerate(batches):
            print(f"\n===== 开始第 {batch_idx+1} 批爬取 =====")
            batch_results = await asyncio.gather(*batch)
            for r in batch_results:
                all_results.extend(r)
            print(f"===== 第 {batch_idx+1} 批完成，累计 {len(all_results)} 条 =====")

        await browser.close()

    # 写入CSV
    output_file = OUTPUT_DIR / "南京大学_增量爬取_新数据.csv"
    fieldnames = ['序号', '姓名', '邮箱', '学院', '职称', '主页链接']
    with open(output_file, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, r in enumerate(all_results, 1):
            writer.writerow({
                '序号': i,
                '姓名': r['name'],
                '邮箱': r['email'],
                '学院': r['department'],
                '职称': r['title'],
                '主页链接': r['url']
            })

    print(f"\n{'='*60}")
    print(f"✅ 全部完成! 共 {len(all_results)} 条记录")
    print(f"   有邮箱: {sum(1 for r in all_results if r['email'])} 条")
    print(f"   输出: {output_file}")

    # 按学院统计
    from collections import Counter, defaultdict
    dept_counts = Counter()
    dept_emails = Counter()
    for r in all_results:
        dept_counts[r['department']] += 1
        if r['email']:
            dept_emails[r['department']] += 1

    print("\n各学院统计:")
    for dept, total in sorted(dept_counts.items(), key=lambda x: -x[1]):
        em = dept_emails.get(dept, 0)
        rate = em/total*100 if total > 0 else 0
        print(f"  {dept}: {total} 人, {em} 邮箱 ({rate:.1f}%)")


if __name__ == "__main__":
    asyncio.run(main())
