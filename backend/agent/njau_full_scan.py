#!/usr/bin/env python3
"""全面扫描 NJAU 页面获取所有教师名和数据"""
import asyncio, json, re
from playwright.async_api import async_playwright

async def scan_page(label, url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080})
        page = await context.new_page()

        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(5)

        # 等待教师名称出现
        try:
            await page.wait_for_function("""() => {
                const text = document.body.innerText;
                const matches = text.match(/^[\\u4e00-\\u9fff]{2,4}$/gm);
                return matches && matches.length > 10;
            }", {timeout: 10000})
        except:
            pass

        # 获取页面结构中所有的教师姓名
        teachers = await page.evaluate("""() => {
            const results = [];

            // 方法1: 查找所有文本节点中的2-4汉字词
            function walkText(node) {
                if (node.nodeType === 3) { // text node
                    const text = node.textContent.trim();
                    if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text)) {
                        const parent = node.parentElement;
                        if (parent) {
                            // 检查父元素是否在可见区域
                            const style = window.getComputedStyle(parent);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {
                                // 检查是否在导航区
                                const navParents = parent.closest('#nav, .nav, .header, #header, .footer, #footer, .menu, .sidebar');
                                const isInNav = navParents !== null;
                                const link = parent.tagName === 'A' ? parent.href : (parent.querySelector('a') ? parent.querySelector('a').href : '');
                                const tag = parent.tagName.toLowerCase();
                                results.push({
                                    name: text,
                                    tag: tag,
                                    href: link ? link.substring(0, 150) : '',
                                    inNav: isInNav,
                                    parentClass: (parent.className || '').substring(0, 50),
                                    parentId: parent.id || ''
                                });
                            }
                        }
                    }
                }
                for (let child of node.childNodes) {
                    if (child.nodeType !== 1 || (child.tagName !== 'SCRIPT' && child.tagName !== 'STYLE')) {
                        walkText(child);
                    }
                }
            }
            walkText(document.body);

            return results;
        }""")

        # 过滤导航区和非教师名
        NAV_NAMES = {'首页','学院概况','学院简介','现任领导','历任领导','机构设置','联系我们',
                'English','加入收藏','设为首页','网站首页','学校主页','南农主页','旧版回顾',
                '怀念旧版','学科师资','师资队伍','人才培养','科学研究','学生工作','党建思政',
                '下载中心','师资队伍','合作交流','社会服务','招生就业','学校概况','学科建设',
                '教育教学','科学研究','合作交流','学院公告','学术报告','通知公告','师资力量',
                '师资概况','全部','教授','副教授','讲师','研究员','副研究员','助研','博士后',
                '实验师','工程师','博导','硕导','院长','书记','主任','所长','教师','导师',
                '硕士','博士','本科','专家','人才','团队','队伍','方向','概况','新闻','通知',
                '公告','信息','公开','管理','机构','系统','登录','注册','搜索','重置','更多',
                '返回','详情','查看','地址','电话','邮箱','邮编','版权','备案','关于','网站',
                'English','英文','中文','旧版','首页','末页','下一页','上一页','共条','当前',
                '当前位置','首页','学科建设','社会服务','党建','工会','校友','捐赠','联系'}

        valid = []
        nav_filtered = 0
        for t in teachers:
            n = t['name']
            if n in NAV_NAMES:
                nav_filtered += 1
                continue
            # Filter single chars, duplicates, etc
            if len(n) < 2 and n not in '上一页下一页末页首页共条':
                continue
            valid.append(t)

        # 去重
        seen = set()
        unique = []
        for t in valid:
            if t['name'] not in seen:
                seen.add(t['name'])
                unique.append(t)

        print(f"\n{'='*60}")
        print(f"【{label}】{url}")
        print(f"导航过滤: {nav_filtered}, 有效教师: {len(unique)}")
        if unique:
            print(f"前10个: {', '.join(t['name'] for t in unique[:10])}")
            # Count by tag type
            tag_counts = {}
            for t in unique:
                tag_counts[t['tag']] = tag_counts.get(t['tag'], 0) + 1
            print(f"标签分布: {tag_counts}")
            # 有链接的
            with_link = sum(1 for t in unique if t.get('href'))
            print(f"含链接: {with_link}")

        await browser.close()
        return {"label": label, "total": len(unique), "teachers": unique[:5]}

async def main():
    sites = [
        ("农学院", "https://nx.njau.edu.cn/jsfc_nxx.jsp?urltype=tree.TreeTempUrl&wbtreeid=1227"),
        ("植保学院", "https://plant.njau.edu.cn/zwbhxy_all.jsp?urltype=tree.TreeTempUrl&wbtreeid=1192"),
        ("草业学院", "https://cyxy.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1348"),
        ("资环学院", "https://re.njau.edu.cn/jsfc2.jsp?urltype=tree.TreeTempUrl&wbtreeid=1325"),
        ("工学院", "https://coe.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1140"),
        ("信息管理", "https://info.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1076"),
        ("经济管理", "https://economy.njau.edu.cn/xksz/szdw1/nyjjxx.htm"),
        ("食品学院", "https://food.njau.edu.cn/szdw/zrjs1/azcfl.htm"),
        ("人文学院", "https://xrw.njau.edu.cn/szdw/kxjssx.htm"),
        ("理学院", "https://cos.njau.edu.cn/szdw3/szdw2/js.htm"),
        ("金融学院", "https://finance.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1230"),
        ("马克思学院", "https://szb.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1143"),
        ("外国语学院", "https://foreign.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1124"),
    ]
    for label, url in sites:
        await scan_page(label, url)

asyncio.run(main())
