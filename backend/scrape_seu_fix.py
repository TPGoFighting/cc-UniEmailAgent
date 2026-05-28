"""东南大学 — 零产出学院修复爬虫。

修复内容：
1. 修正错误 URL（如"师资概况"→"教师名录"/"全体教师"）
2. 兼容多种链接文本格式（纯姓名、姓名+职称、姓名(备注)）
3. 支持多级子页面（教研室→教师列表→详情页）
"""

import asyncio
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from collections import Counter

from playwright.async_api import async_playwright

TASK_ID = "bda95480-ec96-4bd7-bc18-05f797e28dd4"
OUTPUT_DIR = Path(__file__).parent / "outputs" / TASK_ID

PAGE_TIMEOUT = 25000
PROFILE_TIMEOUT = 12000
MAX_TEACHERS_PER_DEPT = 200

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

ADMIN_EMAILS = {
    "webmaster", "admin", "office", "info", "master", "root", "postmaster",
    "wxyxz", "xwcb", "bgs", "dangzheng", "yuanban", "radio", "seuradiojob",
    "dzxy", "seuem", "seutc_official", "ysxy", "slst", "deanoffice_seuarch",
    "jupiter", "seueexb", "cyber", "zscq", "seuyzb", "gsyz",
}

NAV_WORDS = {
    '首页','概况','新闻','通知','公告','招生','培养','就业','学位','学科',
    '科研','学术','党建','工会','校友','捐赠','图书馆','校园','地图','网站',
    '登录','邮箱','联系我们','欢迎','返回','更多','详情','查看','下载',
    '学院','大学','管理','后台','English','日本語',
    '人才引进','人才招聘','院长书记','信箱','相关链接','联系方式',
    '学校首页','学校主页','收藏本站','旧版入口','暑期学校','平湖芳草',
    '下载专区','捐赠通道','院长邮箱','院内文档','标识系统',
    '院系设置','教师教学','技术转移','海外教育','仪器设备','化工时刊',
    '尾页','网站首页','招生信息','教师登录','现任领导','历任领导','办公电话',
    '院长寄语','组织机构','学科建设','历史沿革','学院简介','学院介绍',
    '组织框架','系所设置','学科组织','本院概况','本院简介','学院简况',
    '学院概述','学院架构','快捷入口','学术论文','专利成果','获奖成果',
    '课程改革','牵头学科','学位管理','出国交流','答辩公示',
    '本科生','研究生','学生工作','党群工作','人才培养','人才培养',
    '科学研究','人才引进','校友天地','合作交流','诚聘英才',
    '拔尖基地','教学管理','本科生培','研究生培','鲁汶国际','项目介绍',
    '规章制度','学生自我','教职工','教师教学','发展中心','教师查询',
    '教师风采','专任教师','客座教授','教师简介','兼职教授',
    '离退休','荣休','知名专家','知名学者','全体教师','硕博导师',
    '各系名单','国家高层次','人才','参观预约','博士后','博士','硕士',
    '助手','助理','秘书','处长','科长','主任','书记','馆长',
    '师资修改','管理入口','个人中心','师资维护','师资概况','师资队伍',
    '师资力量','教师名录','教授风采','杰出人才','杰出教师',
    '声影机械','行政服务','资料下载','常用下载','培养动态',
    '招生动态','行政机构','系所介绍','学院治理','学院新闻','学术信息',
    '重要通知','教务信息','图片新闻','党群组织','关工委工作',
    '学术委员会','教学委员会','学术委员会','学位评定',
    '本科生培养','研究生培养','重点科研平台','广纳英才',
    '两院院士','人才职称','硕博导师','客座教授','兼职教授',
    '实验中心','院机关','硕士导师','博士导师','博士生导师','硕士生导师',
    '在站博士后','专职科研岗','职业规划导师','学系','附属医院',
    '研究进展','科研平台','重点实验室','留学生培养',
    '本科生事务','研究生事务','理论学习指南','学院宣传片',
    '学系部门名单','实验教学中心','医学教育发展中心',
    '全员合影','参观活动','会议活动','院徽','百年党史',
    '教师活动照片','大合唱照片','东大土木历史人物','教职工名录',
    '建筑工程系','建设与房地产系','工程力学系','桥隧与地下工程系',
    '市政工程系','智慧建造与运维系','全职博士后',
    '学术团体任职','退休教职工','本科生教育',
    '本科生教学','研究生培养','院庆专栏',
    '国家级人才','科技成果','学术年专栏','电子信息',
    '院长信箱','书记院长','English Version','Version English',
    '组织架构','发展历程','学科设置','专业介绍','基地建设',
    '学术动态','科学研究','科研概况','科研通知','科研基地',
    '党群工作','学术交流','科研机构','培养动态','招生动态',
    '教育管理','教育评估','教务管理','学位工作','学科评估',
    '研究生招生','留学生招生','成人教育','远程教育',
    '科研成果','科研项目','科研奖励','科研团队',
    '学院刊物','教授风采','特色专业','重点专业',
    '高端培训','历史人物','行政服务','大事记',
    '联系我们','英文版','EN','en','ENGLISH',
    '登录','账号','密码','注册','忘记密码','验证码',
    '首页','上一页','下一页','尾页','第','页','共',
    '博士生导师','硕士生导师','教师名录','在职教师',
    '全体教师','兼职教授','院士','客座教授',
    '政法','法学','教研室',
}


def is_admin_email(email: str) -> bool:
    low = email.lower()
    for p in ADMIN_EMAILS:
        if low.startswith(p + "@") or p in low.split("@")[0]:
            return True
    return False


def extract_name_from_link(text: str) -> str | None:
    """从链接文本中提取教师姓名。支持多种格式：
    - "陈从颜" → "陈从颜"
    - "翟军勇 博士 教授 博士生导师" → "翟军勇"
    - "刘志红(兼)" → "刘志红"
    - "李鹏（动画）" → "李鹏"
    """
    # 去除零宽字符
    text = text.replace("​", "").replace("‌", "").replace("‍", "")
    text = text.strip()

    # 括号内容先去掉
    text = re.sub(r'[（(][^)）]*[)）]', '', text).strip()

    if not text:
        return None

    # 如果第一个词是2-4个汉字的中文名
    m = re.match(r'^([一-鿿·]{2,4})', text)
    if m:
        name = m.group(1)
        # 排除导航词
        if name not in NAV_WORDS and not any(w in name for w in NAV_WORDS):
            return name

    return None


def extract_title(text: str) -> str:
    """从详情页文本中提取职称。"""
    m = re.search(r"职称[：:]\s*(.+?)(?:\n|$|。|；|研究方向|邮箱|电话|办公室)", text)
    if m:
        raw = m.group(1).strip()
        mapping = {"正高": "教授", "副高": "副教授", "中级": "讲师",
                   "初级": "助教", "正高级": "教授", "副高级": "副教授"}
        return mapping.get(raw, raw)[:20]

    for t in ["长江学者", "杰青", "优青", "院士",
              "教授", "研究员", "高级工程师",
              "副教授", "副研究员",
              "助理教授", "助理研究员",
              "讲师", "工程师", "博导", "硕导"]:
        if t in text:
            return t
    return ""


def normalize_name(name: str) -> str:
    return name.replace("​", "").replace("‌", "").replace("‍", "").strip()


async def extract_teacher_links(page) -> list[dict]:
    """提取教师链接 — 改进版，兼容多种文本格式。"""
    return await page.evaluate("""() => {
        const navWords = new Set(['首页','概况','新闻','通知','公告','招生','培养','就业',
            '学位','学科','科研','学术','党建','工会','校友','捐赠','图书馆',
            '校园','地图','网站','登录','邮箱','联系我们','欢迎','返回','更多',
            '详情','查看','下载','学院','大学','管理','后台','English',
            '人才引进','人才招聘','院长书记','信箱','相关链接','联系方式',
            '学校首页','学校主页','收藏本站','旧版入口','暑期学校','平湖芳草',
            '下载专区','捐赠通道','院长邮箱','院内文档','标识系统',
            '院系设置','教师教学','技术转移','海外教育','仪器设备',
            '尾页','网站首页','招生信息','教师登录','现任领导','历任领导','办公电话',
            '院长寄语','组织机构','学科建设','历史沿革','学院简介','学院介绍',
            '组织框架','系所设置','学科组织','本院概况','本院简介','学院简况',
            '学院概述','学院架构','快捷入口','学术论文','专利成果','获奖成果',
            '课程改革','牵头学科','学位管理','出国交流','答辩公示',
            '本科生','研究生','学生工作','党群工作','人才培养',
            '科学研究','人才引进','校友天地','合作交流','诚聘英才',
            '拔尖基地','教学管理','本科生培','研究生培','规章制度',
            '学生自我','教职工','教师教学','发展中心','教师查询',
            '教师风采','专任教师','客座教授','教师简介','兼职教授',
            '离退休','荣休','知名专家','知名学者','全体教师','硕博导师',
            '各系名单','国家高层次','人才','参观预约','博士后',
            '师资修改','管理入口','个人中心','师资维护','师资概况','师资队伍',
            '师资力量','教师名录','教授风采','杰出人才','杰出教师',
            '声影机械','行政服务','资料下载','常用下载','培养动态',
            '招生动态','行政机构','系所介绍','学院治理','学院新闻','学术信息',
            '重要通知','教务信息','图片新闻','党群组织','关工委工作',
            '学术委员会','教学委员会','学位评定',
            '本科生培养','研究生培养','重点科研平台','广纳英才',
            '两院院士','人才职称','博导','硕导','客座教授',
            '实验中心','院机关','硕士导师','博士导师','博士生导师','硕士生导师',
            '在站博士后','专职科研岗','职业规划导师','学系','附属医院',
            '研究进展','科研平台','重点实验室','留学生培养','本科生事务',
            '研究生事务','理论学习指南','学院宣传片','学系部门名单',
            '实验教学中心','医学教育发展中心','全员合影','参观活动',
            '会议活动','院徽','百年党史','教师活动照片','大合唱照片',
            '东大土木历史人物','教职工名录','建筑工程系','建设与房地产系',
            '工程力学系','桥隧与地下工程系','市政工程系','智慧建造与运维系',
            '全职博士后','学术团体任职','退休教职工','本科生教育',
            '本科生教学','研究生培养','院庆专栏','国家级人才','科技成果',
            '学术年专栏','电子信息','院长信箱','书记院长',
            '组织架构','发展历程','学科设置','专业介绍','基地建设',
            '学术动态','科研概况','科研通知','科研基地','党群工作',
            '学术交流','科研机构','培养动态','招生动态',
            '科研成果','科研项目','科研奖励','科研团队',
            '学院刊物','特色专业','重点专业','高端培训','历史人物',
            '大事记','英文版','登录','账号','密码','注册','忘记密码',
            '首页','上一页','下一页','尾页','第','页','共',
            '具体','查看','详情','更多','全部','点击','链接',
        ]);

        const results = [];
        const seenHrefs = new Set();

        document.querySelectorAll('a').forEach(a => {
            let text = a.textContent.trim()
                .replace(/\\u200b/g, '').replace(/\\u200c/g, '').replace(/\\u200d/g, '').trim();
            const href = a.href || '';
            if (!href || href.startsWith('javascript:') || href === '#') return;
            if (href.includes('webplus') || href.includes('_teacherHome') || href.includes('login')) return;
            if (href.includes('list.htm') && !href.includes('szdw') && !href.includes('teacher')
                && !href.includes('jsazc') && !href.includes('zrjs') && !href.includes('xscz')) return;

            // 去掉括号内容
            const cleaned = text.replace(/[（(][^)）]*[)）]/g, '').replace(/\\s/g, '');
            if (cleaned.length < 2 || cleaned.length > 20) return;

            // 看前2-4个字符是否是中文名
            const nameMatch = cleaned.match(/^([\\u4e00-\\u9fff]{2,4})/);
            if (!nameMatch) return;
            const possibleName = nameMatch[1];
            if (navWords.has(possibleName)) return;
            if (navWords.has(cleaned)) return;

            // 排除纯导航链接（链接文本整个都是导航词）
            if (navWords.has(text.trim())) return;

            // 排除不包含教师特征的链接（包含秘书、科长等）
            if (/秘书|科长|处长|主任|书记|馆长/.test(text)) return;

            if (!seenHrefs.has(href)) {
                seenHrefs.add(href);
                results.push({
                    name: possibleName,
                    fullText: text.trim(),
                    url: href
                });
            }
        });
        return results;
    }""")


async def scrape_profile(profile_page, url: str, name: str, dept: str) -> dict | None:
    """访问教师详情页提取邮箱。"""
    try:
        await profile_page.goto(url, wait_until="domcontentloaded", timeout=PROFILE_TIMEOUT)
        await asyncio.sleep(0.8)
        text = await profile_page.evaluate("() => document.body.innerText")
        emails = [e.lower() for e in EMAIL_RE.findall(text) if not is_admin_email(e)]
        if emails:
            return {
                "name": normalize_name(name),
                "email": emails[0],
                "department": dept,
                "title": extract_title(text),
                "url": url,
            }
    except Exception:
        pass
    return None


async def scrape_one_dept(context, dept_name: str, urls: list[str]) -> list[dict]:
    """爬取单个学院，支持多页面。"""
    print(f"\n{'='*50}")
    print(f"[{dept_name}] 开始...")
    sys.stdout.flush()

    page = await context.new_page()
    profile_page = await context.new_page()
    results = []
    seen_emails = set()
    seen_names = set()

    try:
        all_entries = []
        for url in urls:
            try:
                print(f"  访问: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                await asyncio.sleep(2)

                entries = await extract_teacher_links(page)
                print(f"    提取: {len(entries)} 个教师链接")
                for e in entries[:5]:
                    print(f"      示例: [{e['name']}] {e['fullText'][:40]} → {e['url'][:80]}")
                all_entries.extend(entries)

                # 尝试翻页
                page_links = await page.evaluate("""() => {
                    const links = [];
                    document.querySelectorAll('a').forEach(a => {
                        const t = a.textContent.trim();
                        if (/^\\d+$/.test(t) && a.href.includes('list')) {
                            links.push(a.href);
                        }
                    });
                    return [...new Set(links)].slice(0, 20);
                }""")
                if page_links:
                    print(f"    发现分页: {len(page_links)} 页")

            except Exception as e:
                print(f"  页面错误: {e}")

        # 去重
        seen_urls = set()
        unique = []
        for e in all_entries:
            if e["url"] not in seen_urls:
                seen_urls.add(e["url"])
                unique.append(e)

        print(f"  去重后: {len(unique)} 位，开始访问详情页...")
        sys.stdout.flush()

        count = 0
        for i, entry in enumerate(unique[:MAX_TEACHERS_PER_DEPT]):
            if entry["name"] in seen_names:
                continue
            seen_names.add(entry["name"])

            result = await scrape_profile(profile_page, entry["url"], entry["name"], dept_name)
            if result and result.get("email") and result["email"] not in seen_emails:
                seen_emails.add(result["email"])
                results.append(result)
                count += 1
                if count <= 5 or count % 25 == 0:
                    print(f"    [{count}] {result['name']} <{result['email']}> {result['title']}")
                    sys.stdout.flush()
            if (i + 1) % 30 == 0:
                await asyncio.sleep(0.5)

        print(f"  完成: {len(results)} 位教师(有邮箱)")

    except Exception as e:
        print(f"  学院错误: {e}")
    finally:
        await page.close()
        await profile_page.close()

    sys.stdout.flush()
    return results


# 修正后的学院 URL 列表
FIXED_DEPARTMENTS = [
    # === 之前 URL 错误的 ===
    ("机械工程学院", [
        "https://me.seu.edu.cn/xscz/list.htm",  # 教师名录(正确URL)
    ]),
    ("土木工程学院", [
        "https://civil.seu.edu.cn/1087/list.htm",  # 师资队伍
        "https://civil.seu.edu.cn/zrjs/list.htm",  # 教职工名录
        "https://civil.seu.edu.cn/38465/list.htm",  # 建筑工程系
        "https://civil.seu.edu.cn/38466/list.htm",  # 建设与房地产系
        "https://civil.seu.edu.cn/38467/list.htm",  # 工程力学系
        "https://civil.seu.edu.cn/38468/list.htm",  # 桥隧与地下工程系
        "https://civil.seu.edu.cn/38469/list.htm",  # 市政工程系
        "https://civil.seu.edu.cn/zhjzyywx/list.htm",  # 智慧建造与运维系
    ]),
    ("自动化学院", [
        "https://automation.seu.edu.cn/32668/list.htm",  # 全体教师
        "https://automation.seu.edu.cn/32669/list.htm",  # 院士
        "https://automation.seu.edu.cn/32670/list.htm",  # 博士生导师
        "https://automation.seu.edu.cn/32671/list.htm",  # 硕士生导师
    ]),
    ("仪器科学与工程学院", [
        "https://ins.seu.edu.cn/szdw/list.htm",  # 尝试替代URL
        "https://ins.seu.edu.cn/45081/list.htm",
    ]),
    ("法学院", [
        "https://law.seu.edu.cn/9125/list.htm",  # 在职教师
        "https://law.seu.edu.cn/9133/list.htm",  # 法理法史教研室
        "https://law.seu.edu.cn/9137/list.htm",  # 宪法学与行政法教研室
        "https://law.seu.edu.cn/9141/list.htm",  # 刑法教研室
        "https://law.seu.edu.cn/9145/list.htm",  # 民商法教研室
        "https://law.seu.edu.cn/9148/list.htm",  # 国际法教研室
        "https://law.seu.edu.cn/gcfjyswyxspywxw/list.htm",  # 工程法教研室
    ]),
    ("医学院", [
        "https://med.seu.edu.cn/8694/list.htm",  # 博士生导师
        "https://med.seu.edu.cn/8695/list.htm",  # 硕士生导师
    ]),
    ("生物科学与医学工程学院", [
        "https://bme.seu.edu.cn/505/list.htm",  # 两院院士
        "https://bme.seu.edu.cn/61856/list.htm",  # 人才职称
        "https://bme.seu.edu.cn/62489/list.htm",  # 硕博导师
        "https://bme.seu.edu.cn/61858/list.htm",  # 生物医学工程系
        "https://bme.seu.edu.cn/61859/list.htm",  # 生物信息工程系
        "https://bme.seu.edu.cn/61860/list.htm",  # 智能医学工程系
        "https://bme.seu.edu.cn/61861/list.htm",  # 脑与学习科学系
    ]),
    ("艺术学院", [
        "https://arts.seu.edu.cn/szdw_25730/list.htm",  # 师资力量(原URL，重试)
    ]),
    # === 之前结果偏低的 ===
    ("能源与环境学院", [
        "https://power.seu.edu.cn/9216/list.htm",
        "https://power.seu.edu.cn/9232/list.htm",
    ]),
    ("外国语学院", [
        "https://sfl.seu.edu.cn/9851/list.htm",
        "https://sfl.seu.edu.cn/9852/list.htm",
    ]),
    ("化学化工学院", [
        "https://chem.seu.edu.cn/js/list.htm",
    ]),
    ("交通学院", [
        "https://tc.seu.edu.cn/58248/list.htm",
    ]),
    ("吴健雄学院", [
        "https://wjx.seu.edu.cn/21376/list.htm",
    ]),
    ("统计与数据科学学院", [
        "https://stat.seu.edu.cn/szll_61997/list.htm",
    ]),
    ("网络空间安全学院", [
        "https://cyber.seu.edu.cn/18189/list.htm",
    ]),
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        )

        all_new = []
        for dept_name, urls in FIXED_DEPARTMENTS:
            try:
                teachers = await scrape_one_dept(context, dept_name, urls)
                if teachers:
                    all_new.extend(teachers)
                    print(f"  >>> {dept_name}: 新增 {len(teachers)} 位")
            except Exception as e:
                print(f"  >>> {dept_name} 整体异常: {e}")
            await asyncio.sleep(1)

        await context.close()
        await browser.close()

    # 保存新抓取结果
    if all_new:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = OUTPUT_DIR / f"seu_fix_{ts}.json"
        path.write_text(json.dumps({"count": len(all_new), "teachers": all_new},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n修复抓取总计: {len(all_new)} 位")
        for t in all_new[:5]:
            print(f"  {t['name']} <{t['email']}> {t['department']} {t['title']}")

        dept_counts = Counter(t["department"] for t in all_new)
        for dept, cnt in dept_counts.most_common():
            print(f"  {dept}: {cnt} 位")
    else:
        print("无新数据")

    print(f"\n结果保存到: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
