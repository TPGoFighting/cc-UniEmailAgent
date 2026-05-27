"""补全缺失的14个南京大学院系 — 深层爬取教师个人邮箱 v2。

改进：
- 强化的导航过滤，避免将导航菜单识别为教师姓名
- 教师列表页识别（只有在包含大量姓名链接的页面才提取）
- 清除已爬取的错误记录，重新开始
"""

import asyncio
import re
import csv
import json
import random
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from collections import Counter

# ——— 缺失的14个院系及其 URL ———
# 基于已验证的URL模式
TARGET_DEPTS: dict[str, str] = {
    "化学化工学院": "https://chem.nju.edu.cn",
    "电子科学与工程学院": "https://ese.nju.edu.cn",
    "环境学院": "https://environ.nju.edu.cn",
    "地理与海洋科学学院": "https://sgos.nju.edu.cn",
    "大气科学学院": "https://atmos.nju.edu.cn",
    "医学院": "https://med.nju.edu.cn",
    "建筑与城市规划学院": "https://arch.nju.edu.cn",
    "人工智能学院": "https://ai.nju.edu.cn",
    "现代工程与应用科学学院": "https://eng.nju.edu.cn",
    "历史学院": "https://history.nju.edu.cn",
    "地球科学与工程学院": "https://es.nju.edu.cn",
    "生命科学学院": "https://life.nju.edu.cn",
    "软件学院": "https://software.nju.edu.cn",
    "中美文化研究中心": "https://hnc.nju.edu.cn",
}

OUTPUT_DIR = Path(__file__).parent / "outputs"
PROGRESS_FILE = OUTPUT_DIR / "scrape_14_progress.json"
PAGE_TIMEOUT = 25000  # ms
PROFILE_TIMEOUT = 12000  # ms
MAX_TEACHERS_PER_DEPT = 50

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
NAME_CLEAN_RE = re.compile(r"^[一-鿿]{2,4}$")

# 公共邮箱前缀
ADMIN_PREFIXES = {
    "wxyxz", "xwcb", "bgs", "dangzheng", "office", "yuanban",
    "webmaster", "admin", "info", "master", "root", "postmaster",
    "bgsdz", "ybdz", "hdb", "jzcg",
}

# ⭐ 关键：必须过滤的导航/非教师文本
STRICT_NAV_BLACKLIST = {
    # 学院/站点通用导航
    "学校主页", "学院首页", "网站首页", "返回首页", "设为首页",
    "加入收藏", "联系我们", "后台管理", "登录系统",
    # 学院名称导航
    "化学学院", "化工学院", "电子学院", "环境学院", "地理学院",
    # 页面导航
    "学院概况", "历史沿革", "组织机构", "院长致辞", "现任领导",
    "院系领导", "党群组织", "行政部门", "规章制度", "办事指南",
    "诚聘英才", "人才招聘", "校友名录", "校友风采", "校友活动",
    "百年院庆", "校友之家",
    # 教学/培养导航
    "人才培养", "本科生", "研究生", "博士后", "留学生",
    "暑期班", "培训班", "海外班", "专业设置", "学位授予",
    "课程设置", "教学大纲", "招生简章", "招生培养",
    # 科研导航
    "科学研究", "学术研究", "科研项目", "科研奖励", "院办刊物",
    "学术会议", "学术机构", "研究方向", "成果速递", "成果展示",
    # 学生工作
    "学生工作", "党团建设", "学工布告", "学生活动", "学子风采",
    # 学科/专业名称
    "无机化学", "分析化学", "有机化学", "物理化学", "高分子化学",
    "生物化学", "环境化学", "化学工程", "材料化学",
    "电子工程", "通信工程", "光电工程", "微电子",
    "环境工程", "给排水", "环境科学",
    "地理科学", "遥感科学", "地图学", "GIS",
    "大气科学", "气象学", "气候学",
    "临床医学", "基础医学", "预防医学", "口腔医学",
    "人工智能", "机器学习", "计算机科学", "软件工程",
    "建筑学", "城市规划", "风景园林",
    # 师资页面导航
    "师资队伍", "教师名录", "现任教师", "退休教师", "荣休教师",
    "教师主页", "导师介绍", "导师简介",
    # 其他
    "友情链接", "网站地图", "版权信息", "相关链接",
    "English", "中文", "英文",
}

# 页面上需要包含的教师列表特征词（确信这是教师列表页）
TEACHER_LIST_MARKERS = ["教授", "副教授", "讲师", "研究员"]

def ts():
    return datetime.now().strftime("%H:%M:%S")


def is_admin_email(email: str) -> bool:
    email_lower = email.lower()
    local = email_lower.split("@")[0]
    for prefix in ADMIN_PREFIXES:
        if email_lower.startswith(prefix + "@"):
            return True
    # 过于简短的前缀（2个字母以下）
    if len(local) <= 2 and local.isalpha():
        return True
    return False


def recover_email(text: str) -> str:
    """恢复反爬邮箱格式。"""
    patterns = [
        (r"\s*\[at\]\s*", "@"),
        (r"\s*\(at\)\s*", "@"),
        (r"\s*#@\s*", "@"),
        (r"\s*\[@\]\s*", "@"),
        (r"\s*\(@\)\s*", "@"),
    ]
    for pat, rep in patterns:
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)
    return text


def is_teacher_name_link(text: str) -> bool:
    """严格判断文本是否为教师姓名链接。"""
    text = text.strip()
    # 必须是2-4个汉字
    if not NAME_CLEAN_RE.match(text):
        return False
    # 在导航黑名单中 → 不是教师
    if text in STRICT_NAV_BLACKLIST:
        return False
    # 包含导航关键词
    for kw in STRICT_NAV_BLACKLIST:
        if text in kw or kw in text:
            # 部分匹配：需要小心
            # "化学" 在 "化学化工学院" 中 → 导航
            # "化学" 在 "化学工程" 中 → 学科名，非人名
            pass
    return True


async def goto_safe(page, url: str, timeout=PAGE_TIMEOUT) -> bool:
    """安全地访问页面，返回是否成功。"""
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        if resp and resp.status >= 500:
            return False
        await asyncio.sleep(1.5 + random.random())
        return True
    except Exception:
        return False


async def extract_page_teacher_count(page) -> int:
    """估计当前页面上有多少个教师姓名链接。"""
    count = await page.evaluate("""() => {
        const navBlacklist = new Set(['学校主页','学院首页','网站首页','返回首页','设为首页',
            '加入收藏','联系我们','后台管理','登录系统','化学学院','化工学院','电子学院',
            '环境学院','地理学院','学院概况','历史沿革','组织机构','院长致辞','现任领导',
            '院系领导','党群组织','行政部门','规章制度','办事指南','诚聘英才','人才招聘',
            '校友名录','校友风采','校友活动','百年院庆','校友之家','人才培养','本科生',
            '研究生','博士后','留学生','暑期班','培训班','海外班','专业设置','学位授予',
            '课程设置','教学大纲','招生简章','招生培养','科学研究','学术研究','科研项目',
            '科研奖励','院办刊物','学术会议','学术机构','研究方向','成果速递','成果展示',
            '学生工作','党团建设','学工布告','学生活动','学子风采','无机化学','分析化学',
            '有机化学','物理化学','高分子化学','生物化学','环境化学','化学工程','材料化学',
            '电子工程','通信工程','光电工程','微电子','环境工程','给排水','环境科学',
            '地理科学','遥感科学','地图学','GIS','大气科学','气象学','气候学','临床医学',
            '基础医学','预防医学','口腔医学','人工智能','机器学习','计算机科学','软件工程',
            '建筑学','城市规划','风景园林','师资队伍','教师名录','现任教师','退休教师',
            '荣休教师','教师主页','导师介绍','导师简介','友情链接','网站地图','版权信息',
            'English','中文','英文','English','中文',
        ]);

        let count = 0;
        document.querySelectorAll('a').forEach(a => {
            const text = (a.textContent || '').trim();
            const href = a.href || '';
            if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;
            if (href.endsWith('.pdf') || href.endsWith('.doc')) return;
            if (href.startsWith('mailto:')) return;
            if (href.includes('beian.miit.gov.cn')) return;

            // 匹配中文姓名格式
            if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text) && !navBlacklist.has(text)) {
                count++;
            }
        });
        return count;
    }""")
    return count or 0


async def find_faculty_subpages(page, dept_url: str) -> list[dict]:
    """在学院主页中查找所有可能指向教师列表的链接（包括子目录页面）。"""
    links = await page.evaluate("""() => {
        const results = [];
        const seen = new Set();

        // 师资相关关键词
        const keywords = ['师资', '教师', 'faculty', 'staff', '人员', '教授', '博导',
            '硕导', '导师', '教职工', '名录', '教师名录', '教师主页', '导师介绍',
            '教师名单', '在职教师', '专任教师', '师资力量', '师资概况', 'szdw',
            'szll', 'teacher', 'teachers', 'faculty', 'js', 'jzg',
        ];

        document.querySelectorAll('a').forEach(a => {
            const text = (a.textContent || '').trim();
            const href = a.href || '';
            if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;
            if (href.endsWith('.pdf') || href.endsWith('.doc')) return;
            if (seen.has(href)) return;

            for (const kw of keywords) {
                const textLower = text.toLowerCase();
                const hrefLower = href.toLowerCase();
                if (textLower.includes(kw) || hrefLower.includes(kw)) {
                    seen.add(href);
                    results.push({text, href});
                    break;
                }
            }
        });

        // 按优先级排序：精确匹配 > 包含
        const priorityTerms = ['教师名录', '教师名单', '在职教师', '现任教师',
            '师资队伍', '教师主页', '专任教师', '导师介绍', 'personnel'];
        results.sort((a, b) => {
            let scoreA = 0, scoreB = 0;
            for (const term of priorityTerms) {
                if (a.text.includes(term)) scoreA += 10;
                if (b.text.includes(term)) scoreB += 10;
                if (a.href.includes(term)) scoreA += 5;
                if (b.href.includes(term)) scoreB += 5;
            }
            return scoreB - scoreA;
        });

        return results.slice(0, 15);
    }""")
    return links


async def extract_teachers_from_page(page, context, dept_name: str) -> list[dict]:
    """从教师列表页提取教师条目并访问详情页。"""
    # 先统计有多少教师姓名链接（用于判断是不是教师列表页）
    teacher_count_estimate = await extract_page_teacher_count(page)
    print(f"    估计教师姓名链接数: {teacher_count_estimate}")

    # 提取教师姓名链接
    entries = await page.evaluate("""() => {
        const navBlacklist = [
            '学校主页','学院首页','网站首页','返回首页','设为首页',
            '加入收藏','联系我们','后台管理','登录系统','化学学院','化工学院',
            '电子学院','环境学院','地理学院','学院概况','历史沿革','组织机构',
            '院长致辞','现任领导','院系领导','党群组织','行政部门','规章制度',
            '办事指南','诚聘英才','人才招聘','校友名录','校友风采','校友活动',
            '百年院庆','校友之家','人才培养','本科生','研究生','博士后',
            '留学生','暑期班','培训班','海外班','专业设置','学位授予',
            '课程设置','教学大纲','招生简章','招生培养','科学研究','学术研究',
            '科研项目','科研奖励','院办刊物','学术会议','学术机构','研究方向',
            '成果速递','成果展示','学生工作','党团建设','学工布告','学生活动',
            '学子风采','无机化学','分析化学','有机化学','物理化学','高分子化学',
            '生物化学','环境化学','化学工程','材料化学','电子工程','通信工程',
            '光电工程','微电子','环境工程','给排水','环境科学','地理科学',
            '遥感科学','地图学','GIS','大气科学','气象学','气候学',
            '临床医学','基础医学','预防医学','口腔医学','人工智能','机器学习',
            '计算机科学','软件工程','建筑学','城市规划','风景园林','师资队伍',
            '教师名录','现任教师','退休教师','荣休教师','教师主页','导师介绍',
            '导师简介','友情链接','网站地图','版权信息','相关链接',
            'English','中文','英文',
            // 更多常见导航
            '学科建设','合作交流','国际合作','社会服务','新闻速递','通知公告',
            '学术动态','人才队伍','党建思政','团学工作','校友工作','信息公开',
            '下载中心','资料下载','教学资源','相关下载',
            // 常见学术分类页标签
            '新闻中心','学院新闻','学术活动','报告讲座','教务通知','学工通知',
            '公示公告','招聘信息','访问学者','讲座教授',
        ];
        const navSet = new Set(navBlacklist);

        const entries = [];
        const seen = new Set();

        // 策略1：表格中查找（最可能包含教师信息）
        document.querySelectorAll('table tr').forEach(row => {
            const links = row.querySelectorAll('a');
            const cells = row.querySelectorAll('td, th');
            if (links.length >= 1 && cells.length >= 2) {
                const firstLink = links[0];
                const text = (firstLink.textContent || '').trim();
                const href = firstLink.href || '';
                if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;
                if (href.endsWith('.pdf') || href.endsWith('.doc')) return;
                if (href.includes('beian.miit.gov.cn')) return;
                if (seen.has(href)) return;

                // 必须是中文姓名格式
                if (!/^[\\u4e00-\\u9fff]{2,4}$/.test(text)) return;
                // 不在黑名单中
                if (navSet.has(text)) return;

                seen.add(href);

                // 从同行获取职称
                let title = '';
                for (let i = 1; i < Math.min(cells.length, 5); i++) {
                    const ct = (cells[i].textContent || '').trim();
                    const tm = ct.match(/(教授|副教授|助理教授|讲师|研究员|副研究员|助理研究员|工程师|高级工程师|院士)/);
                    if (tm) { title = tm[1]; break; }
                }
                entries.push({name: text, url: href, title});
            }
        });

        // 策略2：列表结构中查找
        if (entries.length <= 2) {
            document.querySelectorAll('ul li, ol li, div.list-item, div.teacher-item, div.member, div.card').forEach(item => {
                const links = item.querySelectorAll('a');
                if (links.length === 0) return;
                const firstLink = links[0];
                const text = (firstLink.textContent || '').trim();
                const href = firstLink.href || '';
                if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;
                if (href.endsWith('.pdf')) return;
                if (seen.has(href)) return;
                if (!/^[\\u4e00-\\u9fff]{2,4}$/.test(text)) return;
                if (navSet.has(text)) return;

                seen.add(href);
                const itemText = (item.textContent || '').trim();
                let title = '';
                const tm = itemText.match(/(教授|副教授|助理教授|讲师|研究员|副研究员|助理研究员|工程师|院士)/);
                if (tm) title = tm[1];
                entries.push({name: text, url: href, title});
            });
        }

        return entries.slice(0, 60);
    }""")

    if not entries:
        return []

    print(f"    找到 {len(entries)} 个教师条目")

    # 逐个访问详情页
    results = []
    for i, entry in enumerate(entries[:MAX_TEACHERS_PER_DEPT]):
        try:
            profile_page = await context.new_page()
            try:
                await profile_page.goto(
                    entry["url"], wait_until="domcontentloaded", timeout=PROFILE_TIMEOUT
                )
                await asyncio.sleep(0.8)

                # 获取页面文本
                body_text = await profile_page.evaluate("() => document.body.innerText || ''")
                body_text = recover_email(body_text)

                # mailto链接
                mailto_list = await profile_page.evaluate("""() => {
                    const emails = [];
                    document.querySelectorAll('a[href^="mailto:"]').forEach(a => {
                        const email = a.getAttribute('href')
                            .replace('mailto:', '')
                            .split('?')[0].trim();
                        if (email) emails.push(email);
                    });
                    return emails;
                }""")

                # 合并所有邮箱
                all_emails = set()
                for e in EMAIL_RE.findall(body_text):
                    all_emails.add(e)
                for e in mailto_list:
                    all_emails.add(e)

                # 过滤公共邮箱
                valid = [e for e in all_emails if EMAIL_RE.match(e) and not is_admin_email(e)]

                # 提取职称
                title = entry.get("title", "")
                if not title:
                    title_text = await profile_page.evaluate("""() => {
                        const body = document.body.innerText;
                        const titles = ['教授','副教授','助理教授','讲师','研究员',
                            '副研究员','助理研究员','工程师','高级工程师','院士',
                            '博导','硕导','长江学者','杰青','优青','青年学者',
                            '特聘教授','讲座教授'];
                        for (const t of titles) {
                            if (body.includes(t)) return t;
                        }
                        return '';
                    }""")
                    title = title_text

                result = {
                    "name": entry["name"],
                    "email": valid[0] if valid else "",
                    "department": dept_name,
                    "title": title,
                    "url": entry["url"],
                }

                # 只保留有邮箱的 或者 看起来是真正教师页面（有职称信息）的
                if valid or title:
                    results.append(result)
                    status = "✅" if valid else "❌无邮箱"
                else:
                    # 可能不是真正的教师页面，仍然保留但标记
                    results.append(result)
                    status = "❓疑似非教师"

                print(f"    [{i+1}/{min(len(entries), MAX_TEACHERS_PER_DEPT)}] {entry['name']:4s} {status}")

            finally:
                await profile_page.close()
        except Exception as e:
            # 即使出错也保留记录
            results.append({
                "name": entry["name"],
                "email": "",
                "department": dept_name,
                "title": entry.get("title", ""),
                "url": entry["url"],
            })
            print(f"    [{i+1}/{min(len(entries), MAX_TEACHERS_PER_DEPT)}] {entry['name']:4s} ❌异常")

    return results


async def scrape_department(page, context, dept_name: str, dept_url: str) -> list[dict]:
    """爬取单个学院。"""
    print(f"\n{'='*50}")
    print(f"[{ts()}] 🏫 {dept_name}")

    # Step 1: 访问主页
    if not await goto_safe(page, dept_url):
        print(f"  ❌ 无法访问 {dept_url}")
        return []
    print(f"  ✅ 主页访问成功")

    # Step 2: 找师资入口
    faculty_links = await find_faculty_subpages(page, dept_url)
    print(f"  🔗 找到 {len(faculty_links)} 个可能的师资链接")

    # Step 3: 逐个尝试师资链接，找到真正的教师列表页
    all_results = []
    visited_pages = set()

    for fl_idx, fl in enumerate(faculty_links[:10]):  # 最多试10个链接
        target_url = fl["href"]
        if target_url in visited_pages:
            continue
        visited_pages.add(target_url)

        print(f"  [{fl_idx+1}] 尝试: {fl['text']} → {target_url[:80]}")
        if not await goto_safe(page, target_url):
            continue

        # 检查是否是教师列表页
        count = await extract_page_teacher_count(page)
        if count < 3 and fl_idx < len(faculty_links) - 1:
            print(f"    ⏭️ 只有{count}个姓名链接，跳过（不是教师列表页）")
            continue

        # ⭐ 在访问详情页之前，先检查该页面是否有分页
        # 处理分页
        page_num = 1
        while page_num <= 5:  # 最多5页
            if page_num > 1:
                # 查找"下一页"链接
                next_url = await page.evaluate("""() => {
                    const links = document.querySelectorAll('a');
                    for (const a of links) {
                        const text = a.textContent.trim();
                        if (text === '下一页' || text === '>' || text === '>>' ||
                            text === 'next' || text.includes('下页')) {
                            return a.href;
                        }
                    }
                    // 分页数字链接
                    for (const a of links) {
                        const text = a.textContent.trim();
                        if (/^\\d+$/.test(text)) {
                            const parent = a.parentElement;
                            if (parent && parent.classList.contains('pagination')) {
                                return a.href;
                            }
                        }
                    }
                    return null;
                }""")
                if next_url and next_url != page.url:
                    print(f"    📄 翻到第{page_num}页: {next_url[:80]}")
                    if not await goto_safe(page, next_url):
                        break
                else:
                    break

            results = await extract_teachers_from_page(page, context, dept_name)
            all_results.extend(results)
            page_num += 1

        # 如果找到了足够多的教师，就跳出
        if len(all_results) >= 10:
            break

    # 去重（按URL）
    seen_urls = set()
    unique_results = []
    for r in all_results:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            unique_results.append(r)

    with_email = sum(1 for r in unique_results if r["email"])
    print(f"  📊 {dept_name}: {len(unique_results)}位教师, {with_email}个有邮箱")
    return unique_results


async def main():
    print(f"[{ts()}] 🚀 补全爬虫 v2 — 14个院系")

    # 清除旧进度（因为之前v1有导航错误）
    progress = {"completed_depts": [], "all_results": []}

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

        try:
            for dept_name, dept_url in TARGET_DEPTS.items():
                if dept_name in progress["completed_depts"]:
                    continue

                try:
                    results = await scrape_department(page, context, dept_name, dept_url)
                except Exception as e:
                    print(f"  ❌ {dept_name} 异常: {e}")
                    results = []

                # 过滤掉明显不是教师记录的条目（既没邮箱也没职称）
                results = [r for r in results if r.get("email") or r.get("title")]

                progress["completed_depts"].append(dept_name)
                progress["all_results"].extend(results)

                # 增量保存
                with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                    json.dump(progress, f, ensure_ascii=False, indent=2)
                print(f"  💾 进度: {len(progress['completed_depts'])}/14 ({len(progress['all_results'])}条记录)")

        finally:
            await context.close()
            await browser.close()

    # ——— 导出 ———
    all_results = progress["all_results"]

    # ⭐ 最终清洗：移除邮箱和职称都为空的记录（很可能是导航链接）
    before = len(all_results)
    all_results = [r for r in all_results if r.get("email") or r.get("title")]
    print(f"\n[{ts()}] 清洗: {before} → {len(all_results)} (移除无邮箱+无职称的疑似导航记录)")

    print(f"\n{'='*50}")
    print(f"[{ts()}] 🎉 完成!")
    print(f"[{ts()}] {len(progress['completed_depts'])} 院系, {len(all_results)} 位教师")

    with_email = sum(1 for r in all_results if r.get("email"))
    print(f"[{ts()}] 有邮箱: {with_email}/{len(all_results)}")

    # 保存 CSV
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"南京大学_补全14院系_{ts_str}.csv"

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["序号", "姓名", "邮箱", "学院", "职称", "主页链接"])
        for i, r in enumerate(all_results, 1):
            writer.writerow([
                i,
                r.get("name", ""),
                r.get("email", ""),
                r.get("department", ""),
                r.get("title", ""),
                r.get("url", ""),
            ])

    print(f"[{ts()}] CSV: {csv_path}")

    # 按学院统计
    dept_counter = Counter(r.get("department", "") for r in all_results)
    for dept, count in dept_counter.most_common():
        email_count = sum(1 for r in all_results if r.get("department") == dept and r.get("email"))
        print(f"  {dept}: {count}人, {email_count}有邮箱")

    print(f"\n[{ts()}] 进度文件: {PROGRESS_FILE}")


if __name__ == "__main__":
    from playwright.async_api import async_playwright
    asyncio.run(main())
