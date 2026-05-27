"""南京大学全量教师信息爬虫 v3。

相比 v2 的改进：
1. 预配置师资页面 URL（不再依赖自动发现，太容易失败）
2. 多级 URL 探测：首页找链接 → 预设路径 → 常见模式
3. 改进教师检测：姓名链接 + 列表卡片 + URL 模式兜底 + 全页扫描
4. 分页支持
5. 重试机制（网络错误自动重试 2 次）
6. 更完整的院系配置（35个院系全覆盖）
"""

import asyncio
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

# ============================================================
# NJU 院系配置（35个院系全覆盖，含预配置的师资页面 URL）
# ============================================================

# 已验证可用的院系师资页面路径（通过前两轮爬取验证）
VERIFIED_FACULTY_URLS = {
    "文学院": "https://chin.nju.edu.cn/szdw/zjjs",
    "哲学系": "https://philo.nju.edu.cn/szdw/jsjs",
    "法学院": "https://law.nju.edu.cn/szdw/jsjs",
    "外国语学院": "https://sfs.nju.edu.cn/szdw/jsjs",
    "政府管理学院": "https://public.nju.edu.cn/szdw/jsjs",
    "信息管理学院": "https://im.nju.edu.cn/szdw/jsjs",
    "社会学院": "https://sociology.nju.edu.cn/szdw/jsjs",
    "新闻传播学院": "https://jc.nju.edu.cn/szdw/jsjs",
    "艺术学院": "https://art.nju.edu.cn/szdw/jsjs",
    "马克思主义学院": "https://marxism.nju.edu.cn/szdw/jsjs",
    "体育部": "https://sports.nju.edu.cn/szdw/jsjs",
    "海外教育学院": "https://hwxy.nju.edu.cn/szdw/jsjs",
    "物理学院": "https://physics.nju.edu.cn/szdw/jsjs",
    "天文与空间科学学院": "https://astronomy.nju.edu.cn/szdw/jsjs",
    "化学化工学院": "https://chem.nju.edu.cn/szdw/jsjs",
    "大气科学学院": "https://atmos.nju.edu.cn/szdw/jsjs",
    "商学院": "https://nubs.nju.edu.cn/szdw/jsjs",
    "匡亚明学院": "https://dii.nju.edu.cn/szll/szdw",
    "中华文化研究院": "https://zhwh.nju.edu.cn/szdw",
    "中美文化研究中心": "https://hnc.nju.edu.cn/szdw",
    "计算机科学与技术系": "https://cs.nju.edu.cn/szdw/jsxx",
    "软件学院": "https://software.nju.edu.cn/szll/szdw/index.html",
    "数学学院": "https://math.nju.edu.cn/jzyg/apypl/index.html",
    "教育研究院": "https://edu.nju.edu.cn/8746/list.htm",
    "历史学院": "https://history.nju.edu.cn/28475/list.htm",
    "现代工程与应用科学学院": "https://eng.nju.edu.cn/szdw/list.htm",
    "数字经济与管理学院": "https://sdem.nju.edu.cn/59579/list.htm",
}

# 院系主页（用于未验证 URL 时的探测）
NJU_DEPARTMENTS: list[dict] = [
    # 文科
    {"name": "文学院", "url": "https://chin.nju.edu.cn"},
    {"name": "历史学院", "url": "https://history.nju.edu.cn"},
    {"name": "哲学系", "url": "https://philo.nju.edu.cn"},
    {"name": "法学院", "url": "https://law.nju.edu.cn"},
    {"name": "商学院", "url": "https://nubs.nju.edu.cn"},
    {"name": "外国语学院", "url": "https://sfs.nju.edu.cn"},
    {"name": "政府管理学院", "url": "https://public.nju.edu.cn"},
    {"name": "信息管理学院", "url": "https://im.nju.edu.cn"},
    {"name": "社会学院", "url": "https://sociology.nju.edu.cn"},
    {"name": "新闻传播学院", "url": "https://jc.nju.edu.cn"},
    {"name": "艺术学院", "url": "https://art.nju.edu.cn"},
    {"name": "马克思主义学院", "url": "https://marxism.nju.edu.cn"},
    {"name": "体育部", "url": "https://sports.nju.edu.cn"},
    {"name": "海外教育学院", "url": "https://hwxy.nju.edu.cn"},
    {"name": "匡亚明学院", "url": "https://dii.nju.edu.cn"},
    {"name": "教育研究院", "url": "https://edu.nju.edu.cn"},
    {"name": "中华文化研究院", "url": "https://zhwh.nju.edu.cn"},
    {"name": "中美文化研究中心", "url": "https://hnc.nju.edu.cn"},

    # 理科
    {"name": "数学学院", "url": "https://math.nju.edu.cn"},
    {"name": "物理学院", "url": "https://physics.nju.edu.cn"},
    {"name": "天文与空间科学学院", "url": "https://astronomy.nju.edu.cn"},
    {"name": "化学化工学院", "url": "https://chem.nju.edu.cn"},
    {"name": "大气科学学院", "url": "https://atmos.nju.edu.cn"},
    {"name": "地球科学与工程学院", "url": "https://es.nju.edu.cn"},
    {"name": "地理与海洋科学学院", "url": "https://geo.nju.edu.cn"},
    {"name": "生命科学学院", "url": "https://life.nju.edu.cn"},

    # 工科
    {"name": "计算机科学与技术系", "url": "https://cs.nju.edu.cn"},
    {"name": "软件学院", "url": "https://software.nju.edu.cn"},
    {"name": "人工智能学院", "url": "https://ai.nju.edu.cn"},
    {"name": "电子科学与工程学院", "url": "https://ese.nju.edu.cn"},
    {"name": "现代工程与应用科学学院", "url": "https://eng.nju.edu.cn"},
    {"name": "环境学院", "url": "https://environment.nju.edu.cn"},
    {"name": "建筑与城市规划学院", "url": "https://arch.nju.edu.cn"},
    {"name": "工程管理学院", "url": "https://sme.nju.edu.cn"},

    # 医科
    {"name": "医学院", "url": "https://med.nju.edu.cn"},

    # 交叉/新兴
    {"name": "数字经济与管理学院", "url": "https://sdem.nju.edu.cn"},
    {"name": "南京赫尔辛基大气与地球系统科学学院", "url": "https://nju-atmosphere-helsinki.nju.edu.cn"},
    {"name": "能源与资源学院", "url": "https://energy.nju.edu.cn"},
]

OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
PROGRESS_FILE = OUTPUT_DIR / "nju_scrape_v3_progress.json"

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
AT_PATTERN = re.compile(r"\s*\[at\]\s*|\s*\(at\)\s*|\s*#@\s*|\s*\[@\]\s*", re.IGNORECASE)
MAX_RETRIES = 2


# ============================================================
# 百家姓 + 复姓（复用 v2）
# ============================================================
_COMMON_SURNAMES = set("""
赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张
孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎
鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤
滕殷罗毕郝邬安常乐于时傅皮下齐康伍余元卜顾孟平黄
和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞
熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭
梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯咎管卢莫
经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚
程嵇邢滑裴陆荣翁荀羊於惠甄麴家封芮羿储靳汲邴糜松
井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫
宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄
印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴鬱胥能苍双
闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍卻璩桑桂濮牛寿通
边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容
向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东
欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空
曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逮盍益桓公
""".replace("\n", ""))
_COMMON_SURNAMES.update([
    "欧阳", "太史", "端木", "上官", "司马", "东方", "独孤", "南宫",
    "万俟", "闻人", "夏侯", "诸葛", "尉迟", "公羊", "赫连", "澹台",
    "皇甫", "宗政", "濮阳", "公冶", "太叔", "申屠", "公孙", "慕容",
    "仲孙", "钟离", "长孙", "宇文", "司徒", "鲜于", "司空", "闾丘",
    "子车", "亓官", "司寇", "巫马", "公西", "壤驷", "乐正", "公良",
    "拓跋", "夹谷", "宰父", "谷梁", "段干", "百里", "呼延", "东郭",
    "南门", "羊舌", "微生", "梁丘", "左丘", "东门", "西门",
])

_NOT_PERSON_NAMES = {
    "文艺学", "汉语言", "语言学", "比较文", "中国古", "中国现", "戏剧与",
    "师德师", "师资队", "现任教",
    "文艺", "文学", "汉语", "中文", "外语", "新闻", "传播", "广告",
    "哲学", "宗教", "历史", "考古", "社会", "人类", "经济", "金融",
    "数学", "物理", "化学", "生物", "天文", "地理", "大气", "海洋",
    "地球", "地质", "环境", "生态", "建筑", "规划", "园林", "景观",
    "计算", "软硬", "信息", "通信", "电子", "自动", "材料", "能源",
    "力学", "工程", "航空", "航天", "土木", "水利", "交通", "化工",
    "国际", "公共", "行政", "工商", "会计", "市场", "人力", "物流",
    "法学", "政治", "行政", "图书", "档案", "教育", "心理", "体育",
    "音乐", "美术", "设计", "戏剧", "电影", "舞蹈", "医学", "药学",
    "护理", "口腔", "基础", "临床", "预防", "生命", "基因",
    "学院", "学系", "研究", "方向", "专业", "学位",
    "办公", "财务", "教务", "学工", "团委", "党委",
    "综合", "保障", "后勤", "保卫", "基建",
    "技术", "安全", "服务", "开发", "运营", "维护",
    "协调", "创新", "支撑",
}

NAV_KEYWORDS = [
    "首页", "概况", "简介", "领导", "职能", "制度", "招聘",
    "工作", "通知", "公告", "新闻", "动态", "学术", "科研", "党建",
    "团建", "学生", "招生", "就业", "国际", "合作", "联系", "关于",
    "下载", "办事", "指南", "登录", "注册", "English", "校友",
    "本科", "研究生", "留学", "博士", "博士后", "培训", "暑期",
    "海外", "校庆", "院庆", "百年", "布告", "刊物", "会议", "奖励",
    "项目", "机构", "风采", "活动", "组织", "发展", "历史", "渊源",
    "专业", "设置", "规章", "诚聘", "英才", "培养", "行政", "管理",
    "退休", "兼职", "访问", "客座", "名誉",
    "师资", "现任", "师德", "地址", "研究", "方向", "电话",
    "邮编", "队伍", "人才", "引进", "建设", "学习", "教育",
    "实验", "仪器", "平台", "中心", "实验室", "研究所",
    "导航", "快速", "通道", "友情", "链接", "更多", "详情",
    "专栏", "文献", "著作", "馆藏", "系庆", "论坛",
    "协调", "创新", "重点", "支撑", "专项", "分管", "负责",
    "委员会", "学位", "教学", "指导", "督导",
]

TITLE_KEYWORDS = [
    "教授", "副教授", "讲师", "助理教授", "研究员", "副研究员",
    "高级工程师", "工程师", "院士", "博导", "硕导", "长江学者",
    "杰出青年", "优秀青年", "青年学者", "特聘", "讲座",
    "高级实验师", "实验师", "助理研究员", "研究助理",
    "博士后",
]


# ============================================================
# 工具函数
# ============================================================

def is_valid_chinese_name(text: str) -> bool:
    text = text.strip()
    if not text or text in _NOT_PERSON_NAMES:
        return False
    m = re.fullmatch(r"([一-鿿]{1,2})([一-鿿]{1,2})", text)
    if m:
        return m.group(1) in _COMMON_SURNAMES
    m = re.fullmatch(r"([一-鿿]{2,4})\s*(教授|副教授|讲师|助理教授|研究员|副研究员|院士|博导|硕导)", text)
    if m:
        return m.group(1)[0] in _COMMON_SURNAMES
    return False


def is_nav_link(text: str) -> bool:
    text = text.strip()
    if not text:
        return True
    for kw in NAV_KEYWORDS:
        if kw in text:
            return True
    return False


def parse_at_sign(text: str) -> str:
    return AT_PATTERN.sub("@", text)


def extract_emails(text: str) -> list[str]:
    text = parse_at_sign(text)
    return list(set(EMAIL_PATTERN.findall(text)))


# ============================================================
# URL 探测：找到院系的师资页面
# ============================================================

FACULTY_PATH_CANDIDATES = [
    "/szdw/jsxx", "/szdw/jsjs", "/szdw/zjjs",
    "/szdw", "/szdw/list.htm",
    "/szll/szdw/index.html", "/szll/szdw",
    "/jzyg/apypl/index.html", "/jzyg/list.htm", "/jzyg",
    "/szdw1/szdw", "/szdw1",
    "/xygk/szdw",
    "/szdw1/jsjs",
]


async def probe_faculty_url(page, base_url: str, verified_url: str = None) -> Optional[str]:
    """探测院系的师资页面 URL。先试已知 URL，再试常见路径模式。"""
    # 优先使用已验证的 URL
    if verified_url:
        for attempt in range(MAX_RETRIES):
            try:
                resp = await page.request.get(verified_url)
                if resp and resp.ok:
                    return verified_url
            except Exception:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(1)
        logger.debug(f"已验证 URL 不可达: {verified_url}")

    # 策略1: 在首页找"师资队伍"链接
    try:
        await page.goto(base_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(0.5)

        links = await page.evaluate("""() => {
            const keywords = ['师资队伍', '师资力量', '教师名录', '教师队伍', '人才队伍',
                            'faculty', 'teacher', 'people', 'staff', '教职员工'];
            const results = [];
            document.querySelectorAll('a').forEach(a => {
                const text = (a.textContent || '').trim();
                const href = a.href || '';
                for (const kw of keywords) {
                    if (text.includes(kw) || href.toLowerCase().includes(kw.toLowerCase())) {
                        results.push({text, href});
                        break;
                    }
                }
            });
            return results.slice(0, 10);
        }""")

        for link in links:
            for attempt in range(MAX_RETRIES):
                try:
                    resp = await page.request.get(link["href"])
                    if resp and resp.ok:
                        return link["href"]
                except Exception:
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(0.5)
    except Exception as e:
        logger.debug(f"首页探测失败: {e}")

    # 策略2: 尝试常见路径
    for path in FACULTY_PATH_CANDIDATES:
        test_url = urljoin(base_url, path)
        for attempt in range(MAX_RETRIES):
            try:
                resp = await page.request.get(test_url)
                if resp and resp.ok:
                    return test_url
            except Exception:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(0.5)
            break  # 路径探测不重试多次

    return None


# ============================================================
# 教师检测策略（浏览器端 JS）
# ============================================================

async def find_teacher_links(page, base_domain: str) -> tuple[list[dict], list[dict]]:
    """在页面上找出教师链接和子分类链接。返回 (teacher_links, subcat_links)"""
    surnames_js = json.dumps(list(_COMMON_SURNAMES), ensure_ascii=False)

    result = await page.evaluate("""({baseDomain, surnamesArr}) => {
        const surnameSet = new Set(surnamesArr);
        const teacherLinks = [];
        const subcatLinks = [];
        const seen = new Set();

        const navSet = new Set([
            '首页','概况','简介','领导','职能','制度','招聘','通知','公告','新闻',
            '动态','学术','科研','党建','团建','学生','招生','就业','国际','合作',
            '联系','下载','办事','指南','登录','注册','English','校友','本科','研究生',
            '博士','博士后','培训','暑期','海外','校庆','院庆','百年','历史','渊源',
            '专业','设置','规章','诚聘','英才','培养','行政','管理','退休','兼职',
            '访问','客座','名誉','学习','教育','实验','仪器','平台','中心','实验室',
            '研究所','导航','快速','通道','友情','链接','更多','详情','系庆','论坛',
            '专栏','文献','著作','馆藏','队伍','人才','师资','现任','师德','地址',
            '研究','方向','电话','邮编','协调','创新','重点','支撑','专项',
        ]);

        function isValidName(text) {
            if (/^[\\u4e00-\\u9fff]{2,3}$/.test(text)) {
                return surnameSet.has(text[0]);
            }
            const titleMatch = text.match(/^([\\u4e00-\\u9fff]{2,4})\\s*(教授|副教授|讲师|助理教授|研究员|副研究员|院士|博导|硕导)/);
            if (titleMatch) {
                return surnameSet.has(titleMatch[1][0]);
            }
            return false;
        }

        function containsNavKW(text) {
            if (navSet.has(text)) return true;
            for (const kw of navSet) {
                if (text.includes(kw)) return true;
            }
            return false;
        }

        const mainContent = document.querySelector('main, article, .content, .main, .main-content, .container, #content, #main')
            || document.body;

        mainContent.querySelectorAll('a').forEach(a => {
            const text = (a.textContent || '').trim();
            const href = a.href || '';
            if (!href || seen.has(href) || text.length < 2) return;
            if (href.startsWith('javascript:') || href.startsWith('#') || href.startsWith('mailto:')) return;
            if (/\\.(jpg|png|gif|pdf|doc|docx|xls|xlsx|ppt|pptx|rar|zip)$/i.test(href)) return;

            try { if (!new URL(href).hostname.endsWith(baseDomain)) return; } catch(e) { return; }
            if (containsNavKW(text)) return;

            seen.add(href);

            if (isValidName(text)) {
                teacherLinks.push({text, href});
            } else if (/^[\\u4e00-\\u9fff]{2,15}$/.test(text)) {
                subcatLinks.push({text, href});
            }
        });

        return {teacherLinks, subcatLinks};
    }""", {"baseDomain": base_domain, "surnamesArr": json.loads(surnames_js)})

    return result.get("teacherLinks", []), result.get("subcatLinks", [])


async def find_detail_links_by_url_pattern(page, base_domain: str) -> list[dict]:
    """策略 C: 通过 URL 模式找教师详情链接（兜底方案）。
    NJU 常见的详情页 URL: /iXXXXX.htm, /cXXXXX.htm, /XXXXX/list.htm 下的分页
    """
    result = await page.evaluate("""(baseDomain) => {
        const links = [];
        const seen = new Set();

        document.querySelectorAll('a').forEach(a => {
            const text = (a.textContent || '').trim();
            const href = (a.href || '').trim();
            if (!href || seen.has(href) || !text) return;
            if (href.startsWith('javascript:') || href.startsWith('#') || href.startsWith('mailto:')) return;
            if (/\\.(jpg|png|gif|pdf|doc|xls|ppt|rar|zip)$/i.test(href)) return;

            try { if (!new URL(href).hostname.endsWith(baseDomain)) return; } catch(e) { return; }

            // 匹配 NJU 常见的详情页 URL 模式
            const isDetail = (
                /\\/i\\d+\\.htm/.test(href) ||
                /\\/c\\d+\\.htm/.test(href) ||
                /\\/\\d{4,6}\\/\\d{2}\\/c\\d+/.test(href) ||
                /\\/page\\.htm\\?/.test(href) ||
                /\\/\\d+\\.html?$/.test(href)
            );

            if (isDetail && /[\\u4e00-\\u9fff]/.test(text) && text.length <= 50) {
                seen.add(href);
                links.push({text, href});
            }
        });

        return links;
    }""", base_domain)
    return result


async def find_next_page_url(page) -> Optional[str]:
    """检测分页的'下一页'链接。"""
    result = await page.evaluate("""() => {
        const keywords = ['下一页', '下页', '>', '>>', 'next', '»', '›'];
        const allLinks = document.querySelectorAll('a');
        for (const a of allLinks) {
            const text = (a.textContent || '').trim();
            const href = a.href || '';
            if (!href) continue;
            for (const kw of keywords) {
                if (text === kw || text.includes(kw)) {
                    // 排除指向当前页的
                    if (href !== window.location.href) {
                        return href;
                    }
                }
            }
        }
        return null;
    }""")
    return result


# ============================================================
# 列表页批量提取（策略 A，改进版）
# ============================================================

async def scrape_teacher_list_page(page, dept_name: str) -> list[dict]:
    """从教师列表页批量提取教师信息。"""
    results = []
    seen_names = set()

    cards = await page.evaluate("""() => {
        const results = [];
        const candidates = new Set();

        // 1. 明确的教师容器
        document.querySelectorAll(
            '.teacher-item, .teacher-card, .faculty-item, .faculty-card, ' +
            '.member-item, .member-card, .person-item, .person-card, ' +
            '[class*="teacher"], [class*="faculty"], [class*="member"], [class*="person"]'
        ).forEach(el => candidates.add(el));

        // 2. 表格行
        document.querySelectorAll('table tr:has(td), .list-table tr, .table tr').forEach(el => {
            if (el.querySelectorAll('td').length >= 2) candidates.add(el);
        });

        // 3. 列表项（含姓名+职称/邮箱特征）
        document.querySelectorAll('li').forEach(el => {
            const text = el.textContent.trim();
            if (text.length > 5 && text.length < 300 &&
                /[\\u4e00-\\u9fff]{2,3}/.test(text) &&
                /(教授|副教授|讲师|研究员|@|邮箱|Email|职称)/i.test(text)) {
                candidates.add(el);
            }
        });

        // 4. div/p 含姓名+邮箱（严格匹配）
        document.querySelectorAll('div, p').forEach(el => {
            const text = el.textContent.trim();
            if (text.length > 5 && text.length < 500 &&
                /[\\u4e00-\\u9fff]{2,3}/.test(text) &&
                /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/.test(text) &&
                !/(新闻|通知|公告|动态|活动|学术|讲座|会议|报告|联系|地址|电话|邮编)/.test(text)) {
                candidates.add(el);
            }
        });

        // 提取每个候选项
        candidates.forEach(el => {
            const text = (el.textContent || '').trim();
            if (text.length < 5 || text.length > 500) return;

            const hasChineseName = /[\\u4e00-\\u9fff]{2,3}/.test(text);
            if (!hasChineseName) return;

            let name = (text.match(/[\\u4e00-\\u9fff]{2,3}/) || [''])[0];
            if (/^[\\u4e00-\\u9fff]{2,3}$/.test(name) && /[学系院所部室心]$/.test(name)) {
                name = '';
            }

            const navSet = new Set([
                '首页','概况','简介','领导','职能','制度','招聘','通知','公告','新闻',
                '动态','学术','科研','党建','团建','学生','招生','就业','国际','合作',
                '联系','下载','办事','指南','登录','注册','校友','本科','研究生','博士',
                '博士后','培训','暑期','海外','校庆','院庆','百年','布告','刊物','会议',
                '奖励','项目','机构','风采','活动','组织','发展','历史','渊源','专业',
                '设置','规章','诚聘','英才','培养','行政','管理','退休','兼职','访问',
                '客座','名誉','学习','教育','实验','仪器','平台','中心','实验室','研究所',
                '导航','快速','通道','友情','链接','更多','详情','系庆','论坛','专栏',
                '文献','著作','馆藏','队伍','人才'
            ]);
            if (navSet.has(name)) name = '';

            if (!name) return;

            const emailMatch = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/);
            const email = emailMatch ? emailMatch[0] : '';

            const titleMatch = text.match(/([\\u4e00-\\u9fff]{0,10}(?:教授|副教授|助理教授|讲师|研究员|副研究员|高级工程师|工程师|高级实验师|实验师|院士|博导|硕导|长江学者|杰出青年|优秀青年|博士后)[\\u4e00-\\u9fff]{0,6})/);
            const title = titleMatch ? titleMatch[1] : '';

            const link = el.querySelector('a[href]');
            const href = link ? link.href : '';

            results.push({name, email, title, href});
        });

        return results;
    }""")

    for card in cards:
        name = card.get("name", "")
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        results.append({
            "name": name,
            "email": card.get("email", ""),
            "department": dept_name,
            "title": card.get("title", ""),
            "url": card.get("href", ""),
        })

    return results


# ============================================================
# 详情页抓取（改进版）
# ============================================================

async def scrape_detail_page(page, url: str, dept_name: str, default_name: str = "") -> dict:
    """抓取单个教师详情页。"""
    result = {
        "name": default_name,
        "email": "",
        "department": dept_name,
        "title": "",
        "url": url,
    }

    for attempt in range(MAX_RETRIES):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(0.3)
            break
        except Exception:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(1)
            else:
                return result

    try:
        page_text = await page.evaluate("() => document.body?.innerText || ''")
        if not page_text:
            return result

        # 邮箱提取（排除页脚/导航中的公用邮箱）
        email_info = await page.evaluate("""() => {
            const re = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/gi;
            const excludeSelectors = [
                'footer', '[class*="footer"]', '[class*="bottom"]',
                'nav', 'header', '[class*="header"]', '[class*="nav"]',
                '.sidebar', '[class*="sidebar"]', '.copyright',
                '[class*="contact"]', '[class*="link"]',
            ];
            const excludedEmails = new Set();
            excludeSelectors.forEach(sel => {
                try {
                    document.querySelectorAll(sel).forEach(el => {
                        const found = (el.textContent || '').match(re) || [];
                        found.forEach(e => excludedEmails.add(e.toLowerCase()));
                    });
                } catch(e) {}
            });

            const main = document.querySelector(
                'main, article, .content, .main, .main-content, #content, #main, ' +
                '[class*="teacher"], [class*="faculty"], [class*="profile"], [class*="detail"]'
            );
            const mainText = main ? (main.textContent || '') : '';

            const allText = document.body?.innerText || '';
            const allEmails = [...new Set((allText.match(re) || []).map(e => e.toLowerCase()))];
            const mainEmails = (mainText.match(re) || []).map(e => e.toLowerCase());
            const cleanNju = [...new Set(mainEmails.filter(e =>
                e.includes('nju.edu.cn') && !excludedEmails.has(e)
            ))];

            return {all: allEmails, cleanNju: cleanNju, excluded: [...excludedEmails]};
        }""")

        if email_info:
            clean_nju = email_info.get("cleanNju", [])
            result["email"] = clean_nju[0] if clean_nju else ""

        if not result["email"]:
            emails = extract_emails(page_text)
            if emails:
                nju_emails = [e for e in emails if "nju.edu.cn" in e.lower()]
                result["email"] = nju_emails[0] if nju_emails else emails[0]

        # 姓名提取（多策略）
        name = await page.evaluate("""() => {
            for (const sel of ['h1', 'h2', 'h3']) {
                const el = document.querySelector(sel);
                if (el) {
                    const t = el.textContent.trim();
                    const m = t.match(/^[\\u4e00-\\u9fff]{2,4}/);
                    if (m && t.length <= 30) return t.split(/\\s|-|–|—|\\||｜/)[0].trim();
                }
            }
            for (const sel of ['.name', '.teacher-name', '.title', '[class*="name"]', '[class*="title"]']) {
                const el = document.querySelector(sel);
                if (el) {
                    const t = el.textContent.trim();
                    const m = t.match(/[\\u4e00-\\u9fff]{2,4}/);
                    if (m && t.length <= 30) return t.split(/\\s|-|–|—|\\||｜/)[0].trim();
                }
            }
            const title = document.title || '';
            const parts = title.split(/[-–—|｜_\\s]+/);
            for (const p of parts) {
                const m = p.match(/^[\\u4e00-\\u9fff]{2,3}$/);
                if (m) return p.trim();
            }
            return '';
        }""")
        if name and not result["name"]:
            result["name"] = name.strip()

        # 职称提取（改进：识别更多职称类型）
        for line in page_text.split("\n"):
            line = line.strip()
            if len(line) > 80:
                continue
            for kw in TITLE_KEYWORDS:
                if kw in line:
                    result["title"] = line
                    break
            if result["title"]:
                break

    except Exception as e:
        logger.debug(f"详情页抓取失败 {url}: {e}")

    return result


# ============================================================
# 院系爬取主逻辑
# ============================================================

async def scrape_department(context, dept: dict) -> list[dict]:
    """爬取一个院系的所有教师。改进的多级策略。"""
    dept_name = dept["name"]
    base_url = dept["url"]

    results = []
    page = await context.new_page()

    try:
        logger.info(f"正在抓取: {dept_name} ({base_url})")
        base_domain = urlparse(base_url).netloc

        # Step 1: 找到师资页面 URL
        verified_url = VERIFIED_FACULTY_URLS.get(dept_name)
        faculty_url = await probe_faculty_url(page, base_url, verified_url)

        if not faculty_url:
            logger.warning(f"{dept_name}: 未找到师资页面")
            return results

        logger.info(f"{dept_name}: 师资页面 → {faculty_url}")

        # Step 2: 收集所有子页面 URL
        urls_to_visit = [faculty_url]

        try:
            await page.goto(faculty_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(0.8)
        except Exception:
            logger.warning(f"{dept_name}: 师资页面访问失败，继续用 URL 探测结果")

        # 找子页面（教授/副教授/讲师等子分类，以及分页）
        sub_pages = await page.evaluate("""(baseDomain) => {
            const keywords = ['现任教师', '教师名录', '专任教师', '教师列表',
                            '教授', '副教授', '讲师', '助理教授', '研究人员'];
            const urls = [];
            const seen = new Set();
            document.querySelectorAll('a').forEach(a => {
                const text = (a.textContent || '').trim();
                const href = a.href || '';
                if (!href || seen.has(href)) return;
                try { if (!new URL(href).hostname.endsWith(baseDomain)) return; } catch(e) { return; }
                for (const kw of keywords) {
                    if (text.includes(kw) && text.length <= 15) {
                        seen.add(href);
                        urls.push(href);
                        break;
                    }
                }
            });
            return urls.slice(0, 15);
        }""", base_domain)

        urls_to_visit.extend(sub_pages)

        # 处理分页
        next_url = await find_next_page_url(page)
        while next_url and len(urls_to_visit) < 30:
            if next_url not in urls_to_visit:
                urls_to_visit.append(next_url)
                try:
                    await page.goto(next_url, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(0.5)
                    next_url = await find_next_page_url(page)
                except Exception:
                    break
            else:
                break

        # 去重+去锚点
        seen_urls_temp = set()
        clean_urls = []
        for u in urls_to_visit:
            base = u.split("#")[0]
            if base not in seen_urls_temp:
                seen_urls_temp.add(base)
                clean_urls.append(base)
        urls_to_visit = clean_urls
        logger.info(f"{dept_name}: 共 {len(urls_to_visit)} 个页面需要扫描")

        # Step 3: 逐个访问子页面提取教师信息
        all_teacher_links = []
        seen_card_names = set()
        pending_cards = []

        for url in urls_to_visit:
            for attempt in range(MAX_RETRIES):
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    await asyncio.sleep(0.3)
                    break
                except Exception:
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(1)

            # 策略 A: 列表页批量提取
            cards = await scrape_teacher_list_page(page, dept_name)
            for card in cards:
                if card["name"] in seen_card_names:
                    continue
                seen_card_names.add(card["name"])
                if card["url"] and (not card["email"] or not card["title"]):
                    pending_cards.append(card)
                else:
                    results.append(card)

            # 策略 B: 教师链接识别
            teacher_links, subcat_links = await find_teacher_links(page, base_domain)
            all_teacher_links.extend(teacher_links)

            # 子分类页面中的教师
            for subcat in subcat_links[:5]:
                try:
                    await page.goto(subcat["href"], wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(0.3)
                    sub_teachers, _ = await find_teacher_links(page, base_domain)
                    all_teacher_links.extend(sub_teachers)
                except Exception:
                    pass

            # 策略 C: URL 模式兜底
            detail_urls = await find_detail_links_by_url_pattern(page, base_domain)
            for d in detail_urls:
                all_teacher_links.append(d)

        # 去重教师链接
        seen_urls = set(r["url"] for r in results if r["url"])
        seen_names = set(r["name"] for r in results if r["name"])
        unique_links = []
        for link in all_teacher_links:
            if link["href"] not in seen_urls:
                seen_urls.add(link["href"])
                name = link["text"].strip()
                name_match = re.match(r"([一-鿿]{2,3})", name)
                teacher_name = name_match.group(1) if name_match else name
                if teacher_name not in seen_names:
                    seen_names.add(teacher_name)
                    unique_links.append(link)

        # Step 4: 访问详情页补充信息
        for card in pending_cards:
            if card["url"]:
                detail = await scrape_detail_page(page, card["url"], dept_name, card["name"])
                if detail["email"] and not card["email"]:
                    card["email"] = detail["email"]
                if detail["title"] and not card["title"]:
                    card["title"] = detail["title"]
            results.append(card)

        for link in unique_links:
            name = link["text"].strip()
            name_match = re.match(r"([一-鿿]{2,3})", name)
            teacher_name = name_match.group(1) if name_match else name
            detail = await scrape_detail_page(page, link["href"], dept_name, teacher_name)
            if not detail["name"]:
                detail["name"] = teacher_name
            results.append(detail)

    except Exception as e:
        logger.error(f"{dept_name}: 抓取出错: {e}")
    finally:
        await page.close()

    return results


# ============================================================
# 主函数
# ============================================================

async def scrape_all_departments():
    """主函数：爬取所有 35 个院系的教师信息。"""
    from playwright.async_api import async_playwright

    OUTPUT_DIR.mkdir(exist_ok=True)

    # 断点续传
    progress = {"completed": [], "all_results": []}
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                progress = json.load(f)
            logger.info(f"已加载进度，已完成 {len(progress['completed'])} 个院系")
        except Exception:
            pass

    completed = set(progress["completed"])
    all_results = progress["all_results"]
    pending = [d for d in NJU_DEPARTMENTS if d["name"] not in completed]

    logger.info(f"总计 {len(NJU_DEPARTMENTS)} 个院系，已完成 {len(completed)}，待处理 {len(pending)}")

    if not pending:
        logger.info("所有院系已完成！")
        return all_results

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            ignore_https_errors=True,
        )

        try:
            for i, dept in enumerate(pending):
                logger.info(f"[{i+1}/{len(pending)}] {dept['name']}")
                dept_results = await scrape_department(context, dept)
                all_results.extend(dept_results)
                completed.add(dept["name"])

                with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                    json.dump({"completed": list(completed), "all_results": all_results}, f, ensure_ascii=False, indent=2)

                logger.info(f"{dept['name']}: {len(dept_results)} 人 (累计 {len(all_results)})")
                await asyncio.sleep(1)
        finally:
            await browser.close()

    return all_results


def clean_results(results: list[dict]) -> list[dict]:
    """后处理清理：过滤非人名、批量邮箱检测、格式修复。"""
    # Step 1: 姓氏验证过滤
    valid = []
    for r in results:
        name = r.get("name", "").strip()
        if not name:
            continue
        if name in ("师资队", "现任教", "中国古", "中国现", "戏剧与", "比较文",
                     "文艺学", "汉语言", "语言学", "师德师", "地址", "本科生"):
            continue
        if not is_valid_chinese_name(name):
            if re.fullmatch(r"[一-鿿]{2,4}", name) and not is_nav_link(name):
                valid.append(r)
            continue
        valid.append(r)

    # Step 2: 批量邮箱检测
    dept_email_count: dict[str, dict[str, int]] = {}
    for r in valid:
        dept = r.get("department", "未知")
        email = r.get("email", "").lower()
        if not email:
            continue
        dept_email_count.setdefault(dept, {})
        dept_email_count[dept][email] = dept_email_count[dept].get(email, 0) + 1

    dept_total: dict[str, int] = {}
    for r in valid:
        dept = r.get("department", "未知")
        dept_total[dept] = dept_total.get(dept, 0) + 1

    bulk_emails: dict[str, set] = {}
    for dept, counts in dept_email_count.items():
        threshold = max(4, int(dept_total.get(dept, 1) * 0.3))
        bulk = {email for email, cnt in counts.items() if cnt >= threshold}
        if bulk:
            bulk_emails[dept] = bulk
            logger.info(f"  批量邮箱检测 [{dept}]: {bulk} (阈值≥{threshold}次)")

    # Step 3: 清理
    # 非个人邮箱前缀
    non_personal_prefixes = ['webmaster', 'admin', 'info@', 'contact@', 'postmaster',
                             'mailto@', 'abuse@', 'no-reply', 'noreply', 'support@',
                             'office@', 'service@', 'hr@', 'jobs@', 'master@']

    cleaned = []
    for r in valid:
        r.pop("_all_emails", None)
        r.pop("_nju_emails", None)
        dept = r.get("department", "未知")
        email = r.get("email", "").lower().strip()

        # 邮箱域名修复
        if email:
            email = re.sub(r'@nju\.ed$', '@nju.edu.cn', email)
            email = re.sub(r'@nju\.edu$', '@nju.edu.cn', email)
            r["email"] = email

        # 批量邮箱清除
        if email and dept in bulk_emails and email in bulk_emails[dept]:
            r["email"] = ""

        # 非个人邮箱过滤
        if r.get("email"):
            for prefix in non_personal_prefixes:
                if r["email"].lower().startswith(prefix):
                    r["email"] = ""
                    break

        # 邮箱格式验证
        if r.get("email") and "@" not in str(r.get("email", "")):
            r["email"] = ""

        cleaned.append(r)

    return cleaned


def export_results(results: list[dict]) -> Path:
    """导出并返回文件路径。"""
    from agent.exporter import export_csv, export_xlsx

    deduped = clean_results(results)

    # 按姓名+院系去重
    seen = set()
    final = []
    for r in deduped:
        key = (r.get("name", ""), r.get("department", ""))
        if key not in seen:
            seen.add(key)
            final.append(r)

    csv_path = export_csv(final, "南京大学_教师名录")
    xlsx_path = export_xlsx(final, "南京大学_教师名录")

    # 统计
    with_email = sum(1 for r in final if r.get("email"))
    with_title = sum(1 for r in final if r.get("title"))
    dept_counts = {}
    for r in final:
        d = r.get("department", "未知")
        dept_counts[d] = dept_counts.get(d, 0) + 1

    logger.info(f"===== 汇总 =====")
    logger.info(f"总教师: {len(final)} | 有邮箱: {with_email} | 有职称: {with_title} | 院系: {len(dept_counts)}")
    for dept, count in sorted(dept_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {dept}: {count}")

    return xlsx_path


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    print("=" * 60)
    print("  南京大学全量教师信息爬虫 v3")
    print(f"  院系数: {len(NJU_DEPARTMENTS)}")
    print(f"  已验证师资URL: {len(VERIFIED_FACULTY_URLS)}")
    print("=" * 60)

    results = await scrape_all_departments()

    if results:
        path = export_results(results)
        print(f"\n✅ 完成！输出文件: {path}")
        print(f"   共 {len(results)} 条记录")
    else:
        print("\n⚠️ 未抓取到任何数据")

    if PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()


if __name__ == "__main__":
    asyncio.run(main())
