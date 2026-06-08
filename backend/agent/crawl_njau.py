#!/usr/bin/env python3
"""南京农业大学教师邮箱全量爬取 - V2 改进版"""
import asyncio, re, csv, os, sys
from datetime import datetime
from playwright.async_api import async_playwright

TASK_ID = "5b98cb68-6571-4ae4-81f8-31e61b538dfd"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exporter import get_task_dir
OUTPUT_DIR = get_task_dir(TASK_ID)

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

ALL_DEPTS = [
    ("农学院", "https://nx.njau.edu.cn/jsfc_nxx.jsp?urltype=tree.TreeTempUrl&wbtreeid=1227"),
    ("植物保护学院", "https://plant.njau.edu.cn/zwbhxy_all.jsp?urltype=tree.TreeTempUrl&wbtreeid=1192"),
    ("园艺学院-果树学科", "https://yyxy.njau.edu.cn/szdw/gsxk.htm"),
    ("园艺学院-蔬菜学科", "https://yyxy.njau.edu.cn/szdw/scxk.htm"),
    ("园艺学院-茶学学科", "https://yyxy.njau.edu.cn/szdw/cxxk.htm"),
    ("园艺学院-观赏园艺学科", "https://yyxy.njau.edu.cn/szdw/gsyyxk.htm"),
    ("园艺学院-中药学科", "https://yyxy.njau.edu.cn/szdw/zyxk.htm"),
    ("园艺学院-设施园艺学科", "https://yyxy.njau.edu.cn/szdw/ssyyxk.htm"),
    ("园艺学院-风景园林学科", "https://yyxy.njau.edu.cn/szdw/fjylxk.htm"),
    ("动物医学院", "https://cvm.njau.edu.cn/xksz/szdw.htm"),
    ("动物科技学院", "https://dky.njau.edu.cn/xksz/jsml.htm"),
    ("草业学院", "https://cyxy.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1348"),
    ("资源与环境科学学院", "https://re.njau.edu.cn/jsfc2.jsp?urltype=tree.TreeTempUrl&wbtreeid=1325"),
    ("生命科学学院", "https://lfc.njau.edu.cn/szdw.htm"),
    ("理学院", "https://cos.njau.edu.cn/szdw3/szdw2/js.htm"),
    ("食品科学技术学院", "https://food.njau.edu.cn/szdw/zrjs1/azcfl.htm"),
    ("工学院", "https://coe.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1140"),
    ("信息管理学院", "https://info.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1076"),
    ("智慧农业学院", "https://ai.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1164"),
    ("经济管理学院", "https://economy.njau.edu.cn/xksz/szdw1/nyjjxx.htm"),
    ("公共管理学院", "https://clm.njau.edu.cn/2022/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1480"),
    ("人文与社会发展学院", "https://xrw.njau.edu.cn/szdw/kxjssx.htm"),
    ("外国语学院", "https://foreign.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1124"),
    ("金融学院", "https://finance.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1230"),
    ("马克思主义学院", "https://szb.njau.edu.cn/jsfc.jsp?urltype=tree.TreeTempUrl&wbtreeid=1143"),
    ("体育部", "https://sports.njau.edu.cn/szdw/szdw.htm"),
    ("前沿交叉研究院", "https://aais.njau.edu.cn/szll.htm"),
]

PUBLIC_PREFIXES = [
    'webmaster', 'admin', 'office', 'info', 'master', 'root', 'postmaster',
    'wxyxz', 'xwcb', 'bgs', 'dangzheng', 'yuanban', 'dangban', 'renshi',
    'jiaowu', 'xuegong', 'tuanwei', 'yanjiusheng', 'gysj', 'gyyz', 'glxb',
    'service', 'support', 'help', 'notice', 'news', 'web', 'host', 'nobody',
    'zhibao', 'cyxy', 'coe@',
]

# 完整的导航名黑名单
NAV_SET = frozenset({
    '首页','学院概况','学院简介','现任领导','历任领导','机构设置','联系我们',
    'English','加入收藏','设为首页','网站首页','学校主页','南农主页','旧版回顾',
    '怀念旧版','学科师资','师资队伍','人才培养','科学研究','学生工作','党建思政',
    '下载中心','合作交流','社会服务','招生就业','学科建设','教育教学',
    '师资力量','师资概况','全部','教授','副教授','讲师','研究员','副研究员',
    '助研','博士后','实验师','工程师','博导','硕导','院长','书记','主任','所长',
    '教师','导师','硕士','博士','本科','专家','人才','团队','队伍','方向','概况',
    '新闻','通知','公告','信息','公开','管理','机构','系统','登录','注册','搜索',
    '重置','更多','返回','详情','查看','地址','电话','邮箱','邮编','版权','备案',
    '关于','网站','英文','中文','旧版','末页','下一页','上一页','共条','当前',
    '当前位置','社会服务','党建','工会','校友','捐赠','联系',
    '学院沿革','学院公告','学术报告','招聘信息','杰出人才','创新团队',
    '规章制度','政策文件','人才引进','教师招聘','博士后招聘','院长信箱','书记信箱',
    '师德师风','教师风采','教师党建','教工之家','退休教师','曾在学院工作过的教师',
    '教学辅助','荣休教师','研究生导师','博士生导师','硕士生导师',
    '导师介绍','导师名录','上页','下页','当前页','页次','条记录',
    '植物病理学系','昆虫学系','农药科学系','团队建设','两学一做',
    '学院首页','学科介绍','二级学科','招生','就业','名师','风采','教辅','行政',
    '实验中心','中心','国家级','省部级','重点','开放课题','年报',
    '重大项目','科研成果','科技奖励','科研基地','科研平台',
    '思想理论','党章党规','上级文件','制度建设','党群工作','学生工作','校友之窗',
    '科研方向','人才队伍','人才工程','人才计划','高层次人才','人才招聘',
    '招聘','诚聘','千人计划','国家杰青','国家优青','青年英才','紫金学者',
    '钟山学者','钟山','学者','讲座','论坛','报告','活动','实践','基地',
    '平台','基金','出国','留学','考试','课程','教学','学科方向',
    '基础数学系','应用数学系','统计与精算系','物理系','化学系','数学',
    '化学','物理','统计学','光学工程','材料科学与工程',
    '学院办公室','科研办公室','研究生办公室','本科教学办公室','学生工作办公室',
    '党委办公室','行政办公室','财务','资产','安全','简报','部门','委员会',
    '职能','标志','报名','注册','系统','空间','预约','教师登录','微服务',
    '教务处','研究生院','财务处','标志','报名','注册','系统','空间','预约',
})


def clean_anti_spam(text):
    text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
    text = text.replace('#@', '@')
    return text


async def crawl_dept(context, dept_name, url):
    """改进版 - 使用 DOM 文本节点遍历提取教师名"""
    page = await context.new_page()
    records = []

    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(4)

        # 使用 DOM 遍历提取所有2-4汉字名（在非导航区域的可见文本节点中）
        teacher_names = await page.evaluate("""() => {
            const navAreas = new Set();
            document.querySelectorAll('#nav, .nav, .header, #header, .footer, #footer, .menu, .banner, #banner, .sidebar, .friendLink, .copyRight, .aban, script, style').forEach(el => {
                navAreas.add(el);
            });
            function isInNav(node) {
                let p = node.parentElement;
                while (p) {
                    if (navAreas.has(p)) return true;
                    p = p.parentElement;
                }
                return false;
            }
            const names = new Set();
            function walk(node) {
                if (node.nodeType === 3) {
                    const parent = node.parentElement;
                    if (!parent || isInNav(node)) return;
                    const style = window.getComputedStyle(parent);
                    if (style.display === 'none' || style.visibility === 'hidden') return;
                    const text = node.textContent.replace(/[\\s\\u00a0]+/g, ' ').trim();
                    if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text)) {
                        names.add(text);
                    }
                }
                for (let child of node.childNodes) {
                    if (child.nodeType !== 1 || (child.tagName !== 'SCRIPT' && child.tagName !== 'STYLE')) {
                        walk(child);
                    }
                }
            }
            walk(document.body);
            return Array.from(names);
        }""")

        # 过滤导航名
        names = [n for n in teacher_names if n not in NAV_SET]

        # 获取页面文本中的邮箱
        body_text = await page.evaluate("() => document.body.innerText")
        cleaned = clean_anti_spam(body_text)
        all_emails = [e.lower() for e in EMAIL_RE.findall(cleaned)]

        # 过滤公共邮箱
        teacher_emails = []
        for e in all_emails:
            prefix = e.split('@')[0]
            if not any(prefix == p or prefix.startswith(p) for p in PUBLIC_PREFIXES):
                teacher_emails.append(e)
        teacher_emails = list(set(teacher_emails))

        # 匹配邮箱到附近的教师名
        name_email = {}
        for email in teacher_emails:
            idx = cleaned.lower().find(email)
            if idx >= 0:
                before = cleaned[max(0,idx-80):idx]
                after = cleaned[idx+len(email):idx+len(email)+80]
                nearby = re.findall(r'[一-鿿]{2,4}', before + after)
                for n in nearby:
                    if n in names:
                        name_email[n] = email
                        break

        for name in names:
            records.append({
                'name': name,
                'email': name_email.get(name, ''),
                'dept': dept_name,
                'title': '',
                'url': url
            })

    except Exception as e:
        pass
    finally:
        await page.close()

    return records


async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )

        all_records = []
        for i in range(0, len(ALL_DEPTS), 3):
            batch = ALL_DEPTS[i:i+3]
            tasks = [crawl_dept(context, name, url) for name, url in batch]
            batch_results = await asyncio.gather(*tasks)

            for (dept_name, _), records in zip(batch, batch_results):
                email_count = sum(1 for r in records if r['email'])
                print(f"  ✅ {dept_name:25s} | {len(records):3d}教师 | {email_count}邮箱")
                all_records.extend(records)

        # 去重（同名保留有邮箱的）
        seen = {}
        for r in all_records:
            name = r['name']
            if name in seen:
                if r['email'] and not seen[name]['email']:
                    seen[name] = r
                elif r['email'] and seen[name]['email']:
                    if r['dept'] not in seen[name]['dept']:
                        seen[name]['dept'] += f"、{r['dept']}"
            else:
                seen[name] = r

        final = list(seen.values())
        email_count = sum(1 for r in final if r['email'])

        print(f"\n{'='*60}")
        print(f"爬取完成! 总计: {len(final)}教师, 含邮箱: {email_count} ({email_count/len(final)*100:.1f}%)")

        # 各学院统计
        print(f"\n{'学院':25s} {'教师数':6s} {'有邮箱':6s}")
        print('-' * 45)
        dept_stats = {}
        for r in final:
            d = r['dept'].split('、')[0]
            if d not in dept_stats:
                dept_stats[d] = {'total': 0, 'email': 0}
            dept_stats[d]['total'] += 1
            if r['email']:
                dept_stats[d]['email'] += 1
        for d, s in sorted(dept_stats.items(), key=lambda x: -x[1]['total']):
            print(f"{d:25s} {s['total']:6d} {s['email']:6d}")

        # 导出
        filename = f"南京农业大学_全部教师邮箱_{timestamp}.csv"
        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['序号', '姓名', '邮箱', '学院', '职称', '主页链接'])
            for i, r in enumerate(final, 1):
                writer.writerow([i, r['name'], r['email'], r['dept'],
                               r.get('title', ''), r.get('url', '')])

        print(f"\n输出: {filepath}")
        print(f"\n[FILES]")
        print(f"{filename} | CSV 表格")
        print(f"[/FILES]")

        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
