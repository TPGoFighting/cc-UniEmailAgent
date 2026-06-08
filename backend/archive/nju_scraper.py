"""南京大学全量教师信息爬虫 v2。

改进策略：
1. 先访问各院系官网的"师资队伍"页面
2. 智能识别教师姓名链接（排除导航链接）
3. 支持两级结构：研究方向子页面 → 教师列表
4. 支持内联列表（无详情页，信息直接在列表页上）
5. 逐个教师详情页提取：姓名、邮箱、学院、职称、主页网址
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

# ============================================================
# NJU 院系配置
# ============================================================
NJU_DEPARTMENTS: list[dict] = [
    # 文科
    {"name": "文学院", "url": "https://chin.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/zjjs", "/szdw/jsjs"]},
    {"name": "历史学院", "url": "https://history.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "哲学系", "url": "https://philo.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "法学院", "url": "https://law.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "商学院", "url": "https://nubs.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "外国语学院", "url": "https://sfs.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "政府管理学院", "url": "https://public.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "信息管理学院", "url": "https://im.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "社会学院", "url": "https://sociology.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "新闻传播学院", "url": "https://jc.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "艺术学院", "url": "https://art.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "马克思主义学院", "url": "https://marxism.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "体育部", "url": "https://sports.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "海外教育学院", "url": "https://hwxy.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "匡亚明学院", "url": "https://dii.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "教育研究院", "url": "https://edu.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "中华文化研究院", "url": "https://zhwh.nju.edu.cn", "faculty_paths": ["/szdw"]},
    {"name": "中美文化研究中心", "url": "https://hnc.nju.edu.cn", "faculty_paths": ["/szdw"]},

    # 理科
    {"name": "数学学院", "url": "https://math.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "物理学院", "url": "https://physics.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "天文与空间科学学院", "url": "https://astronomy.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "化学化工学院", "url": "https://chem.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "大气科学学院", "url": "https://atmos.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "地球科学与工程学院", "url": "https://es.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "地理与海洋科学学院", "url": "https://geo.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "生命科学学院", "url": "https://life.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},

    # 工科
    {"name": "计算机科学与技术系", "url": "https://cs.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsxx"]},
    {"name": "软件学院", "url": "https://software.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "人工智能学院", "url": "https://ai.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "电子科学与工程学院", "url": "https://ese.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "现代工程与应用科学学院", "url": "https://eng.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "环境学院", "url": "https://environment.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "建筑与城市规划学院", "url": "https://arch.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},
    {"name": "工程管理学院", "url": "https://sme.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},

    # 医科
    {"name": "医学院", "url": "https://med.nju.edu.cn", "faculty_paths": ["/szdw", "/szdw/jsjs"]},

    # 交叉/新兴
    {"name": "数字经济与管理学院", "url": "https://sdem.nju.edu.cn", "faculty_paths": ["/szdw"]},
    {"name": "南京赫尔辛基大气与地球系统科学学院", "url": "https://nju-atmosphere-helsinki.nju.edu.cn", "faculty_paths": ["/szdw"]},
    {"name": "能源与资源学院", "url": "https://energy.nju.edu.cn", "faculty_paths": ["/szdw"]},
]

OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
PROGRESS_FILE = OUTPUT_DIR / "nju_scrape_progress.json"

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
AT_PATTERN = re.compile(r"\s*\[at\]\s*|\s*\(at\)\s*|\s*#@\s*|\s*\[@\]\s*", re.IGNORECASE)

# ============================================================
# 中文百家姓 — 用于验证人名（top 200+ 姓氏 + 复姓，覆盖 95%+ 人口）
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
# 补充常见 1-2 字复姓
_COMMON_SURNAMES.update([
    "欧阳", "太史", "端木", "上官", "司马", "东方", "独孤", "南宫",
    "万俟", "闻人", "夏侯", "诸葛", "尉迟", "公羊", "赫连", "澹台",
    "皇甫", "宗政", "濮阳", "公冶", "太叔", "申屠", "公孙", "慕容",
    "仲孙", "钟离", "长孙", "宇文", "司徒", "鲜于", "司空", "闾丘",
    "子车", "亓官", "司寇", "巫马", "公西", "壤驷", "乐正", "公良",
    "拓跋", "夹谷", "宰父", "谷梁", "段干", "百里", "呼延", "东郭",
    "南门", "羊舌", "微生", "梁丘", "左丘", "东门", "西门",
])


def is_valid_chinese_name(text: str) -> bool:
    """基于姓氏验证判断是否像中文人名。"""
    text = text.strip()
    if not text:
        return False
    # 特定词语排除（有合法姓氏但不是人名）
    if text in _NOT_PERSON_NAMES:
        return False
    # 纯中文名 2-3 字且首字是常见姓氏
    m = re.fullmatch(r"([一-鿿]{1,2})([一-鿿]{1,2})", text)
    if m:
        surname = m.group(1)
        if surname in _COMMON_SURNAMES:
            return True
    # 含职称后缀: "张三名 教授" 或 "张三教授"
    m = re.fullmatch(r"([一-鿿]{2,4})\s*(教授|副教授|讲师|助理教授|研究员|副研究员|院士|博导|硕导)", text)
    if m:
        name_part = m.group(1)
        surname = name_part[0] if name_part else ""
        return surname in _COMMON_SURNAMES
    return False


# ============================================================
# 特定非人名词语 — 有合法姓氏首字但不是人名的常见词
# ============================================================
_NOT_PERSON_NAMES = {
    # 学科/方向（容易截断为2-3字的）
    "文艺学", "汉语言", "语言学", "比较文", "中国古", "中国现", "戏剧与",
    "师德师", "师资队", "现任教",
    # 有合法姓氏首字但不是人名的词
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
    # 常见组织机构词汇
    "学院", "学系", "研究", "方向", "专业", "学位",
    "办公", "财务", "教务", "学工", "团委", "党委",
    "综合", "保障", "后勤", "保卫", "基建",
    # 其他
    "技术", "安全", "服务", "开发", "运营", "维护",
    "协调", "创新", "支撑",
    # 教师分类/标签/表头被截断（实际数据中出现的）
    "准聘助", "特任副", "长聘副", "特聘教", "荣退教", "专职科", "在职教",
    "姓名单", "个人邮", "电子邮", "按职称", "课题组", "跨学科", "斯坦福",
    "简报", "副高", "正高", "中级", "初级",
    "施毅院", "院长", "书记", "主任", "副主任",
    # 常见职称作为独立链接文本（用于分类筛选页，不是人名）
    "教授", "副教授", "讲师", "研究员", "工程师", "助教",
    "博导", "硕导", "院士", "助理", "特聘", "名誉",
    # 邮箱/联系方式页面标签
    "邮箱", "电话", "传真", "地址", "邮编", "联系方",
    # 更多可能截断的
    "办事指", "下载中", "新闻动", "学术动", "科研动",
    "人才招", "师资队", "学科建", "专业设", "师德师",
    "党政", "工会", "关工", "校友", "基金",
    "学工", "团委", "党委", "教务", "财务", "后勤",
    "招生", "就业", "国际", "合作",
    "办公", "保障",
}


# ============================================================
# 导航链接关键词 — 链接文本含这些词的跳过
# ============================================================
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


def is_nav_link(text: str) -> bool:
    """判断链接文本是否为导航链接（非教师名）。"""
    text = text.strip()
    if not text:
        return True
    for kw in NAV_KEYWORDS:
        if kw in text:
            return True
    return False


def is_likely_person_name(text: str) -> bool:
    """判断文本是否像人名（调用姓氏验证版本）。"""
    return is_valid_chinese_name(text)


def parse_at_sign(text: str) -> str:
    return AT_PATTERN.sub("@", text)


def extract_emails(text: str) -> list[str]:
    text = parse_at_sign(text)
    return list(set(EMAIL_PATTERN.findall(text)))


async def find_faculty_page(page, base_url: str, faculty_paths: list[str]) -> Optional[str]:
    """找到院系的师资队伍页面。"""
    faculty_keywords = ["师资队伍", "师资力量", "教师名录", "教师队伍", "人才队伍",
                        "faculty", "teacher", "people", "staff"]

    # 策略1：在当前页面上找"师资队伍"链接
    try:
        links = await page.evaluate("""(keywords) => {
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
        }""", faculty_keywords)

        if links:
            for link in links:
                try:
                    resp = await page.request.get(link["href"])
                    if resp and resp.ok:
                        return link["href"]
                except Exception:
                    continue
    except Exception:
        pass

    # 策略2：尝试预设路径
    for path in faculty_paths:
        test_url = urljoin(base_url, path)
        try:
            resp = await page.request.get(test_url)
            if resp and resp.ok:
                return test_url
        except Exception:
            continue

    return None


async def find_teacher_links(page, base_domain: str) -> tuple[list[dict], list[dict]]:
    """在师资页面上找出教师链接和子分类链接。

    返回: (teacher_links, subcategory_links)
    - teacher_links: 教师姓名链接（直接指向教师详情页）
    - subcategory_links: 子分类链接（研究方向/教研室 → 内含教师列表）
    """
    # 构建 JS 端的姓氏集合
    surnames_js = json.dumps(list(_COMMON_SURNAMES), ensure_ascii=False)
    not_names_js = json.dumps(list(_NOT_PERSON_NAMES), ensure_ascii=False)
    nav_kw_js = json.dumps([
        "首页","概况","简介","领导","职能","制度","招聘","工作","通知",
        "公告","新闻","动态","学术","科研","党建","团建","学生","招生","就业",
        "国际","合作","联系","关于","下载","办事","指南","登录","注册","English",
        "校友","本科","研究生","留学","博士","博士后","培训","暑期","海外","校庆",
        "院庆","百年","布告","刊物","会议","奖励","项目","机构","风采","活动",
        "组织","发展","历史","渊源","专业","设置","规章","诚聘","英才","培养",
        "行政","管理","退休","兼职","访问","客座","名誉","队伍建设","人才引进",
        "学习","贯彻","八项","精神","政绩","主题","教育","实验","仪器","平台",
        "中心","实验室","研究所","导航","快速","通道","友情","链接","更多","详情",
        "系庆","论坛","专栏","文献","著作","馆藏",
        "师资","现任","师德","地址","研究","方向","电话","邮编",
        "协调","创新","重点","支撑","专项",
    ], ensure_ascii=False)

    result = await page.evaluate("""({baseDomain, surnamesArr, navKW, notNamesArr}) => {
        const surnameSet = new Set(surnamesArr);
        const notNameSet = new Set(notNamesArr);
        const teacherLinks = [];
        const subcatLinks = [];
        const seen = new Set();
        const navSet = new Set(navKW);

        function isValidName(text) {
            // 排除已知非人名词
            if (notNameSet.has(text)) return false;
            // 1. 纯中文 2-3 字且首字是常见姓氏
            if (/^[\\u4e00-\\u9fff]{2,3}$/.test(text)) {
                return surnameSet.has(text[0]);
            }
            // 2. 含职称后缀
            const titleMatch = text.match(/^([\\u4e00-\\u9fff]{2,4})\\s*(教授|副教授|讲师|助理教授|研究员|副研究员|院士|博导|硕导)/);
            if (titleMatch) {
                return surnameSet.has(titleMatch[1][0]);
            }
            return false;
        }

        function containsNavKW(text) {
            // 全词匹配或关键词出现在文本中
            if (navSet.has(text)) return true;
            for (const kw of navSet) {
                if (text.includes(kw)) return true;
            }
            return false;
        }

        const mainContent = document.querySelector('main, article, .content, .main, .main-content, .container, #content, #main')
            || document.body;

        const allLinks = mainContent.querySelectorAll('a');

        allLinks.forEach(a => {
            const text = (a.textContent || '').trim();
            const href = a.href || '';
            if (!href || seen.has(href) || text.length < 2) return;
            if (href.startsWith('javascript:') || href.startsWith('#') || href.startsWith('mailto:')) return;
            if (/\\\\.(jpg|png|gif|pdf|doc|docx|xls|xlsx|ppt|pptx|rar|zip)$/i.test(href)) return;

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
    }""", {"baseDomain": base_domain, "surnamesArr": json.loads(surnames_js), "navKW": json.loads(nav_kw_js), "notNamesArr": json.loads(not_names_js)})

    return result.get("teacherLinks", []), result.get("subcatLinks", [])


async def find_teacher_links_in_list_page(page) -> list[dict]:
    """在教师列表页（子分类页）中找出教师链接。"""
    surnames_js = json.dumps(list(_COMMON_SURNAMES), ensure_ascii=False)
    not_names_js = json.dumps(list(_NOT_PERSON_NAMES), ensure_ascii=False)

    result = await page.evaluate("""({surnamesArr, notNamesArr}) => {
        const surnameSet = new Set(surnamesArr);
        const notNameSet = new Set(notNamesArr);
        const links = [];
        const seen = new Set();

        function isValidName(text) {
            if (notNameSet.has(text)) return false;
            if (/^[\\u4e00-\\u9fff]{2,3}$/.test(text)) {
                return surnameSet.has(text[0]);
            }
            const titleMatch = text.match(/^([\\u4e00-\\u9fff]{2,4})\\s*(教授|副教授|讲师|助理教授|研究员|副研究员|院士|博导|硕导)/);
            if (titleMatch) {
                return surnameSet.has(titleMatch[1][0]);
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
            if (/\\\\.(jpg|png|gif|pdf|doc|docx|xls|xlsx|ppt|pptx|rar|zip)$/i.test(href)) return;

            seen.add(href);

            if (isValidName(text)) {
                links.push({text, href});
            }
        });

        return links;
    }""", {"surnamesArr": json.loads(surnames_js), "notNamesArr": json.loads(not_names_js)})
    return result


async def scrape_detail_page(page, url: str, dept_name: str, default_name: str = "") -> dict:
    """抓取单个教师详情页。"""
    result = {
        "name": default_name,
        "email": "",
        "department": dept_name,
        "title": "",
        "url": url,
    }

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(0.3)

        page_text = await page.evaluate("() => document.body?.innerText || ''")
        if not page_text:
            return result

        # 邮箱 — 从主内容区域提取，排除页脚/导航的公用邮箱
        email_info = await page.evaluate("""() => {
            const re = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/gi;

            // 1. 排除区域（页脚、导航、版权栏）中的邮箱
            const excludeSelectors = [
                'footer', '[class*="footer"]', '[id*="footer"]',
                'nav', '[class*="nav-bar"]',
                '.copyright', '[class*="copyright"]',
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

            // 2. 主内容区域（教师资料区域）
            const main = document.querySelector(
                'main, article, .content, .main, .main-content, ' +
                '#content, #main, .wp, .article-content, ' +
                '[class*="teacher"], [class*="faculty"], [class*="profile"], [class*="detail"], ' +
                '[class*="intro"], [class*="resume"], [class*="con"]'
            );
            const mainText = main ? (main.textContent || '') : '';

            // 3. 所有页面邮箱
            const allText = document.body?.innerText || '';
            const allEmails = [...new Set((allText.match(re) || []).map(e => e.toLowerCase()))];

            // 4. 主内容区的 NJU 邮箱（排除公用邮箱）
            const mainEmails = (mainText.match(re) || []).map(e => e.toLowerCase());
            const cleanNju = [...new Set(mainEmails.filter(e =>
                e.includes('nju.edu.cn') && !excludedEmails.has(e)
            ))];

            return {
                all: allEmails,
                cleanNju: cleanNju,
                excluded: [...excludedEmails],
            };
        }""")

        # 优先使用主内容区的非公用邮箱
        if email_info:
            clean_nju = email_info.get("cleanNju", [])
            result["email"] = clean_nju[0] if clean_nju else ""

        # 兜底：如果上一步没找到，从全页文本提取
        if not result["email"]:
            emails = extract_emails(page_text)
            if emails:
                nju_emails = [e for e in emails if "nju.edu.cn" in e.lower()]
                result["email"] = nju_emails[0] if nju_emails else emails[0]

        # 姓名 — 多种策略
        name = await page.evaluate("""() => {
            // 策略1: h1/h2 标题
            for (const sel of ['h1', 'h2', 'h3']) {
                const el = document.querySelector(sel);
                if (el) {
                    const t = el.textContent.trim();
                    const m = t.match(/^[\\u4e00-\\u9fff]{2,4}/);
                    if (m && t.length <= 30) return t.split(/\\s|-|–|—|\\||｜/)[0].trim();
                }
            }
            // 策略2: class 含 name/title
            for (const sel of ['.name', '.teacher-name', '.title', '[class*="name"]', '[class*="title"]']) {
                const el = document.querySelector(sel);
                if (el) {
                    const t = el.textContent.trim();
                    const m = t.match(/[\\u4e00-\\u9fff]{2,4}/);
                    if (m && t.length <= 30) return t.split(/\\s|-|–|—|\\||｜/)[0].trim();
                }
            }
            // 策略3: 页面 title
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

        # 职称
        title_keywords = [
            "教授", "副教授", "讲师", "助理教授", "研究员", "副研究员",
            "高级工程师", "工程师", "院士", "博导", "硕导", "长江学者",
            "杰出青年", "优秀青年", "青年学者", "特聘", "讲座",
        ]
        for line in page_text.split("\n"):
            line = line.strip()
            if len(line) > 50:
                continue
            for kw in title_keywords:
                if kw in line:
                    result["title"] = line
                    break
            if result["title"]:
                break

    except Exception as e:
        logger.debug(f"详情页抓取失败 {url}: {e}")

    return result


async def scrape_teacher_list_page(page, dept_name: str) -> list[dict]:
    """从教师列表页提取教师信息。尝试多种策略：
    1. 特殊的教师卡片容器
    2. 表格行 (tr)
    3. 列表项 (li)
    4. 包含教师信息的 div
    """
    results = []
    seen_names = set()

    # 策略1: 从各种容器中提取
    cards = await page.evaluate("""() => {
        const results = [];

        // 收集所有可能的候选元素
        const candidates = new Set();

        // 1. 明确的教师容器
        document.querySelectorAll(
            '.teacher-item, .teacher-card, .faculty-item, .faculty-card, ' +
            '.member-item, .member-card, .person-item, .person-card, ' +
            '[class*="teacher"], [class*="faculty"], [class*="member"], [class*="person"]'
        ).forEach(el => candidates.add(el));

        // 2. 表格行（常见教师列表格式）
        document.querySelectorAll('table tr:has(td), .list-table tr, .table tr').forEach(el => {
            if (el.querySelectorAll('td').length >= 2) candidates.add(el);
        });

        // 3. 列表项
        document.querySelectorAll('li').forEach(el => {
            const text = el.textContent.trim();
            // 包含姓名+职称/邮箱特征的 li
            if (text.length > 5 && text.length < 300 &&
                /[\\u4e00-\\u9fff]{2,3}/.test(text) &&
                /(教授|副教授|讲师|研究员|@|邮箱|Email|职称)/i.test(text)) {
                candidates.add(el);
            }
        });

        // 4. div 中包含姓名+邮箱/职称（严格匹配，防止假阳性）
        document.querySelectorAll('div, p').forEach(el => {
            const text = el.textContent.trim();
            // 必须包含邮箱且长度合理
            if (text.length > 5 && text.length < 500 &&
                /[\\u4e00-\\u9fff]{2,3}/.test(text) &&
                /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/.test(text) &&
                !/(新闻|通知|公告|动态|活动|学术|讲座|会议|报告|联系|地址|电话|邮编)/.test(text)) {
                candidates.add(el);
            }
        });

        // 提取每个候选项的信息
        candidates.forEach(el => {
            const text = (el.textContent || '').trim();
            if (text.length < 5 || text.length > 500) return;

            const hasChineseName = /[\\u4e00-\\u9fff]{2,3}/.test(text);
            if (!hasChineseName) return;

            // 提取姓名（取第一个2-3字中文）
            const nameMatch = text.match(/[\\u4e00-\\u9fff]{2,3}/);
            let name = nameMatch ? nameMatch[0] : '';

            // 过滤非人名：以 学/系/院/所/部/室/心 结尾的2-3字词
            if (/^[\\u4e00-\\u9fff]{2,3}$/.test(name) && /[学系院所部室心]$/.test(name)) {
                name = '';
            }

            // 过滤导航词
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

            // 提取邮箱
            const emailMatch = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/);
            const email = emailMatch ? emailMatch[0] : '';

            // 提取职称（保留完整职称文本）
            const titleMatch = text.match(/([\\u4e00-\\u9fff]{0,10}(?:教授|副教授|助理教授|讲师|研究员|副研究员|高级工程师|工程师|院士|博导|硕导|长江学者|杰出青年|优秀青年)[\\u4e00-\\u9fff]{0,6})/);
            const title = titleMatch ? titleMatch[1] : '';

            // 提取详情页链接
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


async def scrape_department(context, dept: dict) -> list[dict]:
    """爬取一个院系的所有教师。多级策略：
    1. 找师资页面 → 找"现任教师"等子页面 → 列表提取 → 详情页补充
    """
    dept_name = dept["name"]
    base_url = dept["url"]
    faculty_paths = dept.get("faculty_paths", ["/szdw"])

    results = []
    page = await context.new_page()

    try:
        logger.info(f"正在抓取: {dept_name} ({base_url})")
        base_domain = urlparse(base_url).netloc

        # Step 1: 打开院系首页
        try:
            await page.goto(base_url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(1.0)
        except Exception as e:
            logger.warning(f"{dept_name}: 首页访问失败: {e}")
            return results

        # Step 2: 找到师资页面
        faculty_url = await find_faculty_page(page, base_url, faculty_paths)
        if not faculty_url:
            logger.warning(f"{dept_name}: 未找到师资页面")
            return results

        # Step 3: 收集所有教师列表子页面的 URL
        urls_to_visit = [faculty_url]

        try:
            await page.goto(faculty_url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(1.0)
        except Exception as e:
            logger.warning(f"{dept_name}: 师资页面访问失败: {e}")
            return results

        # 在当前页面找"现任教师/教师名录/专任教师"等子页面
        sub_pages = await page.evaluate("""(baseDomain) => {
            const keywords = ['现任教师', '教师名录', '专任教师', '教师列表',
                            '教授', '副教授', '讲师', '助理教授'];
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
        # 去重并去除锚点
        seen_urls_temp = set()
        clean_urls = []
        for u in urls_to_visit:
            base = u.split("#")[0]
            if base not in seen_urls_temp:
                seen_urls_temp.add(base)
                clean_urls.append(base)
        urls_to_visit = clean_urls
        logger.info(f"{dept_name}: 共 {len(urls_to_visit)} 个页面需要扫描")

        # Step 4: 逐个访问子页面，提取教师
        # 分两阶段：先收集所有链接（在列表页上），再访问详情页
        all_teacher_links = []
        seen_card_names = set()
        pending_cards = []  # 暂存卡片结果，延迟访问详情页

        for url in urls_to_visit:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(0.3)

                # 阶段 A: 在列表页上收集信息（不离开此页面）
                # A1: 卡片提取（不访问详情页）
                cards = await scrape_teacher_list_page(page, dept_name)
                for card in cards:
                    if card["name"] in seen_card_names:
                        continue
                    seen_card_names.add(card["name"])
                    if card["url"] and (not card["email"] or not card["title"]):
                        pending_cards.append(card)
                    else:
                        results.append(card)

                # A2: 提取教师链接（此时还在列表页上！）
                teacher_links, subcat_links = await find_teacher_links(page, base_domain)
                all_teacher_links.extend(teacher_links)

                # 子分类页面中的教师
                for subcat in subcat_links[:5]:
                    try:
                        await page.goto(subcat["href"], wait_until="domcontentloaded", timeout=15000)
                        await asyncio.sleep(0.3)
                        sub_teachers = await find_teacher_links_in_list_page(page)
                        all_teacher_links.extend(sub_teachers)
                    except Exception:
                        pass

            except Exception as e:
                logger.debug(f"{dept_name}: 子页面访问失败 {url[-40:]}: {e}")

        # 阶段 B: 访问详情页补充信息（对卡片和链接）
        for card in pending_cards:
            detail = await scrape_detail_page(page, card["url"], dept_name, card["name"])
            if detail["email"] and not card["email"]:
                card["email"] = detail["email"]
            if detail["title"] and not card["title"]:
                card["title"] = detail["title"]
            results.append(card)

        # 去重教师链接
        seen_urls = set(r["url"] for r in results if r["url"])
        seen_names = set(r["name"] for r in results if r["name"])
        logger.info(f"{dept_name}: 卡片已覆盖 {len(results)} 人, 待处理链接 {len(all_teacher_links)} 个")
        unique_links = []
        for link in all_teacher_links:
            if link["href"] not in seen_urls:
                seen_urls.add(link["href"])
                # 从链接文本提取姓名
                name = link["text"].strip()
                name_match = re.match(r"([一-鿿]{2,3})", name)
                teacher_name = name_match.group(1) if name_match else name
                if teacher_name not in seen_names:
                    seen_names.add(teacher_name)
                    unique_links.append(link)

        # Step 5: 访问还没被列表提取覆盖的教师详情页
        for i, link in enumerate(unique_links):
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


async def scrape_all_departments():
    """主函数：爬取所有院系的教师信息。"""
    from playwright.async_api import async_playwright

    OUTPUT_DIR.mkdir(exist_ok=True)

    # 加载进度（支持断点续传）
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

                # 保存进度
                with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                    json.dump({"completed": list(completed), "all_results": all_results}, f, ensure_ascii=False, indent=2)

                logger.info(f"{dept['name']}: {len(dept_results)} 人 (累计 {len(all_results)})")
                await asyncio.sleep(1)
        finally:
            await browser.close()

    return all_results


def clean_results(results: list[dict]) -> list[dict]:
    """后处理清理：过滤非人名条目 + 批量邮箱检测。"""
    # 第一步：姓氏验证过滤
    valid = []
    for r in results:
        name = r.get("name", "").strip()
        if not name:
            continue
        if not is_valid_chinese_name(name):
            # 后备：有上下文佐证的稀有姓氏名（有个人邮箱/真实职称/详情页链接）
            has_context = bool(
                r.get("email") or r.get("title") or r.get("url")
            )
            # 网址得像是详情页（路径较长）而非子分类页
            url = r.get("url", "")
            is_detail_url = bool(url) and (
                "/" + "20" in url  # 含年份目录，如 /20190926/i34658.html
                or re.search(r"/[a-z0-9_]+\.(html|htm|shtml|php|jsp|aspx)", url, re.I)
                or len(re.sub(r"https?://[^/]+", "", url)) > 30
            )
            if (has_context or is_detail_url) and re.fullmatch(r"[一-鿿]{2,4}", name):
                valid.append(r)
            continue
        valid.append(r)

    # 第二步：检测批量/部门级邮箱
    # 统计每个部门中每个邮箱出现的次数
    dept_email_count: dict[str, dict[str, int]] = {}
    for r in valid:
        dept = r.get("department", "未知")
        email = r.get("email", "").lower()
        if not email:
            continue
        if dept not in dept_email_count:
            dept_email_count[dept] = {}
        dept_email_count[dept][email] = dept_email_count[dept].get(email, 0) + 1

    # 批量邮箱阈值：同一部门内出现 ≥4 次或 ≥30% 教师的
    bulk_emails: dict[str, set] = {}
    dept_total: dict[str, int] = {}
    for r in valid:
        dept = r.get("department", "未知")
        dept_total[dept] = dept_total.get(dept, 0) + 1

    for dept, counts in dept_email_count.items():
        threshold = max(4, int(dept_total.get(dept, 1) * 0.3))
        bulk = {email for email, cnt in counts.items() if cnt >= threshold}
        if bulk:
            bulk_emails[dept] = bulk
            logger.info(f"    批量邮箱检测 [{dept}]: {bulk} (阈值≥{threshold}次)")

    # 第三步：清理结果
    cleaned = []
    for r in valid:
        dept = r.get("department", "未知")
        email = r.get("email", "").lower()
        # 清除内部字段
        r.pop("_all_emails", None)
        r.pop("_nju_emails", None)

        # 批量邮箱标记为空
        if email and dept in bulk_emails and email in bulk_emails[dept]:
            r["email"] = ""

        # 邮箱格式验证
        if r.get("email") and "@" not in str(r.get("email", "")):
            r["email"] = ""

        cleaned.append(r)

    return cleaned


def export_results(results: list[dict]) -> Path:
    """导出并返回文件路径。"""
    from agent.exporter import export_csv, export_xlsx

    # 后处理清理
    deduped = clean_results(results)

    # 再次去重（按姓名+院系）
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
    print("  南京大学全量教师信息爬虫 v2")
    print(f"  院系数: {len(NJU_DEPARTMENTS)}")
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
