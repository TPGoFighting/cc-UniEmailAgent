#!/usr/bin/env python3
"""探索 NJAU 教师详情页 URL 模式和直接获取邮箱的可能性"""
import asyncio
import re
from playwright.async_api import async_playwright

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
ANTI_AT_RE = re.compile(r'\s*[\[\(]?\s*(?:at|@)\s*[\]\)]?\s*', re.IGNORECASE)

async def find_teacher_detail_urls(context, label, list_url, wait_sel=None):
    """尝试从列表页找到教师详情页URL"""
    page = await context.new_page()
    result = {"label": label, "url": list_url, "teachers": [], "emails_on_page": [], "error": None}

    try:
        await page.goto(list_url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        # 获取页面文本中的邮箱
        text = await page.evaluate("() => document.body.innerText")
        result["emails_on_page"] = EMAIL_RE.findall(text)

        # 查找教师名及其可能链接
        teacher_info = await page.evaluate("""() => {
            const results = [];
            // 先找直接有 href 的 a 链接
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.replace(/\\s+/g, ' ').trim();
                const href = a.href;
                if (text && href && /^[\\u4e00-\\u9fff]{2,4}$/.test(text)) {
                    if (!href.startsWith('javascript') && href !== '#') {
                        results.push({name: text, href: href, type: 'direct_link'});
                    }
                }
            });

            // 找文本中2-4汉字的名字（可能包裹在span/td等非a标签中）
            // 特别找 h1, h2, h3, h4, strong, span, td, div 中的名字
            const tags = ['h1', 'h2', 'h3', 'h4', 'strong', 'span', 'td', 'div', 'li', 'p'];
            tags.forEach(tag => {
                document.querySelectorAll(tag).forEach(el => {
                    const text = el.textContent.replace(/\\s+/g, ' ').trim();
                    if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text) && !el.closest('a')) {
                        // Check not already found
                        if (!results.some(r => r.name === text)) {
                            // Check parent for links
                            const parent = el.parentElement;
                            const link = parent ? parent.querySelector('a') : null;
                            results.push({
                                name: text,
                                href: link ? link.href : '',
                                tag: tag,
                                type: link ? 'parent_link' : 'text_only'
                            });
                        }
                    }
                });
            });

            return results;
        }""")

        # 过滤掉导航链接
        NAV_KW = ['首页', '学院概况', '简介', '领导', '机构', '联系', '师资队伍',
                  '学科', '研究', '通知', '公告', '新闻', '招生', '就业', '搜索',
                  'English', '收藏', '登录', '注册', '返回', '更多', '详情', '查看',
                  '下载', '硕士', '本科', '行政', '管理', '教职', '荣休', '访问',
                  '党建', '工会', '校友', '捐赠', '网站', '地图', '人才培养',
                  '科学研究', '合作交流', '社会服务', '学校概况', '学科建设',
                  '本科', '研究', '教辅', '博士后', '实验', '全部', '导师',
                  '在职', '兼职', '专任', '离退休', '教工', '队伍']

        teachers = [t for t in teacher_info if t['name'] not in NAV_KW
                   and not any(kw in t['name'] for kw in NAV_KW)
                   and len(t['name']) >= 2]

        # 去重
        seen = set()
        unique_teachers = []
        for t in teachers:
            if t['name'] not in seen:
                seen.add(t['name'])
                unique_teachers.append(t)

        result["teachers"] = unique_teachers

    except Exception as e:
        result["error"] = str(e)
    finally:
        await page.close()
        return result

async def check_teacher_detail_page(context, name, url):
    """访问教师详情页提取邮箱"""
    if not url or url == 'about:blank':
        return {"name": name, "emails": [], "error": "no_url"}

    page = await context.new_page()
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(2)
        text = await page.evaluate("() => document.body.innerText")

        # 反爬恢复
        text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
        text = text.replace('#@', '@')

        emails = EMAIL_RE.findall(text)
        await page.close()
        return {"name": name, "emails": emails, "url": url}
    except Exception as e:
        await page.close()
        return {"name": name, "emails": [], "error": str(e)}

async def main():
    # 测试几所有不同结构的学院
    test_sites = [
        # JSP 型 - 可能有 AJAX 加载的详情页
        ("农学院", "https://nx.njau.edu.cn/jsfc_nxx.jsp?urltype=tree.TreeTempUrl&wbtreeid=1227"),
        ("植保学院", "https://plant.njau.edu.cn/zwbhxy_all.jsp?urltype=tree.TreeTempUrl&wbtreeid=1192"),
        # 静态 HTML 型
        ("园艺-果树", "https://yyxy.njau.edu.cn/szdw/gsxk.htm"),
        ("园艺-蔬菜", "https://yyxy.njau.edu.cn/szdw/scxk.htm"),
        ("动物医学院", "https://cvm.njau.edu.cn/xksz/szdw.htm"),
        ("动物科技", "https://dky.njau.edu.cn/xksz/jsml.htm"),
        ("食品学院", "https://food.njau.edu.cn/szdw/zrjs1/azcfl.htm"),
        ("人文学院", "https://xrw.njau.edu.cn/szdw/kxjssx.htm"),
        ("理学院", "https://cos.njau.edu.cn/szdw3/szdw2/js.htm"),
        ("信息管理", "https://info.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1076"),
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})

        # 第一步：探索所有学院，提取教师名和链接
        tasks = [find_teacher_detail_urls(context, label, url) for label, url in test_sites]
        results = await asyncio.gather(*tasks)

        total_teachers = 0
        for r in results:
            status = '✅'
            if r.get('error'):
                status = '❌ ' + r['error'][:30]
            teacher_count = len(r['teachers'])
            total_teachers += teacher_count
            direct_links = sum(1 for t in r['teachers'] if t.get('href'))
            print(f"{status} {r['label']:15s} | 教师:{teacher_count:3d} | 含链接:{direct_links:3d} | 页面邮箱:{len(r['emails_on_page'])}")

        print(f"\n总计: {total_teachers} 教师")

        # 第二步：对有 direct_link 的教师，尝试进入详情页提取邮箱
        print("\n\n=== 第二步：尝试提取详情页邮箱 ===")
        teacher_to_check = []
        for r in results:
            for t in r['teachers']:
                if t.get('href') and not t['href'].startswith('http://www.njau.edu.cn/') and not t['href'].startswith('https://www.njau.edu.cn/'):
                    # 跳过导航链接和faculty.njau.edu.cn（维护中）
                    if 'faculty.njau' not in t['href']:
                        teacher_to_check.append((t['name'], t['href']))

        # 取前10个测试
        sample = teacher_to_check[:10]
        print(f"测试 {len(sample)} 个教师详情页...")
        detail_tasks = [check_teacher_detail_page(context, name, url) for name, url in sample]
        detail_results = await asyncio.gather(*detail_tasks)

        for dr in detail_results:
            status = f"邮箱: {dr['emails']}" if dr['emails'] else f"无邮箱: {dr.get('error', 'unknown')}"
            print(f"  {dr['name']:10s} -> {status}")

        await browser.close()

asyncio.run(main())
