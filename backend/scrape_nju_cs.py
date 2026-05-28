"""南京大学计算机科学与技术系教师邮箱爬取脚本"""
import asyncio
import csv
import re
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs" / "d2f5c072-1462-43e2-9dcc-8d8b88c473e6"
DEPT_NAME = "计算机科学与技术系"
BASE_URL = "https://cs.nju.edu.cn"

SEED_URLS = [
    f"{BASE_URL}/szdw/jsxx.htm",
    f"{BASE_URL}/szdw.htm",
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
AT_RE = re.compile(r"\s*\[at\]\s*|\s*\(at\)\s*|\s*#@\s*|\s*\[@\]\s*", re.IGNORECASE)

# 忽略的公共邮箱
PUBLIC_PREFIXES = [
    "webmaster", "admin", "info@", "office@", "cs@cs.nju",
    "szdw@", "jsxx@", "nju_cs@", "cs_nju@",
]

# 百家姓（top 200+）用于验证中文姓名
_SURNAMES = set("""
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
曾毋沙乜养鞠须丰巢关蒯相查後荆红游竺权逮盍益桓公
仉督晋楚闫法汝鄢涂钦归谯帅况
""".replace("\n", ""))

# 不是人名的常见词（含4字及以下的管理/类别词汇）
NON_PERSON_WORDS = {
    "教授", "副教授", "讲师", "助教", "研究员", "副研究员",
    "博导", "硕导", "院士", "博士后", "工程师", "高级工程师",
    "师资队伍", "师资", "教师", "教师名录", "学院概览", "学院概况",
    "学院简介", "机构设置", "现任领导", "历任领导", "党政领导",
    "系主任", "副系主任", "教研室", "实验室", "研究所",
    "党委", "党支部", "团支部", "行政", "管理", "学工",
    "人才培养", "科学研究", "社会服务", "国际合作", "招生就业",
    "本科教学", "研究生教学", "研究生教育", "工程硕士",
    "学术动态", "新闻动态", "通知公告", "院内公告",
    "科研工作", "科研获奖", "合作交流", "最新动态", "最新论著",
    "支部建设", "学习教育", "规章制度", "资料汇编", "热点链接",
    "诚聘英才", "就业信息", "会议讲座", "计算机基础",
    "奖学金", "研究生公告", "本科生公告", "获奖公告",
    "研究领域", "研究团队", "研究方向", "学生工作",
    "离退休", "离退休人员", "返聘", "荣休", "兼职",
    "访问学者", "特聘", "讲座", "客座",
    "专业技术", "行政人员", "行政管理", "专业技术人员",
    "准长聘", "跨学科博", "跨学科",
    "国家级项", "省部级项", "企业委托", "国际合作",
    "教学计划", "教学资源", "课程计划",
    "硕士研究生", "博士研究生", "在职专业", "研究生课程",
    "深入学习", "学习贯彻", "树立和践", "学习宣传",
    "网站首页", "返回首页", "设为首页", "加入收藏",
    "联系我们", "友情链接", "版权信息", "网站地图",
    "中文", "English", "旧版", "新版",
    "下载中心", "办事指南", "登录", "注册",
}

NOT_NAME_ENDS = set("报组室部处委会局办系院所馆站网栏目页版")


def _has_valid_surname(name: str) -> bool:
    """检查名字是否以合法姓氏开头"""
    if not name:
        return False
    # 2字名的第一个字必须是姓氏
    if name[0] not in _SURNAMES:
        return False
    return True


def is_public_email(email: str) -> bool:
    email_lower = email.lower()
    for prefix in PUBLIC_PREFIXES:
        if prefix in email_lower:
            return True
    return False


def extract_chinese_name(text: str) -> str:
    """从文本中提取中文姓名（2-3字，以合法姓氏开头）"""
    if not text:
        return ""
    text = text.strip()
    # 先检查是否是非人名词汇
    if text in NON_PERSON_WORDS:
        return ""
    # 取前2-3个中文字符
    m = re.search(r"^([一-鿿]{2,3})", text)
    if not m:
        return ""
    name = m.group(1)
    if name in NON_PERSON_WORDS:
        return ""
    if name[-1] in NOT_NAME_ENDS:
        return ""
    # 必须包含合法姓氏
    if not _has_valid_surname(name):
        return ""
    return name


def is_teacher_link(text: str) -> bool:
    """检查链接文本是否像教师姓名"""
    text = text.strip()
    if not text or len(text) > 50:
        return False
    if text in NON_PERSON_WORDS:
        return False
    name = extract_chinese_name(text)
    if not name:
        return False
    return True


def extract_title_from_text(text: str) -> str:
    """从页面文本中提取职称"""
    titles = []
    title_keywords = [
        "教授", "副教授", "讲师", "助理教授", "研究员", "副研究员",
        "博导", "硕导", "院士", "博士后", "高级工程师", "工程师",
        "实验师", "特聘教授", "讲座教授", "访问教授", "兼职教授",
        "长江学者", "杰青", "优青", "青年学者", "千人计划",
    ]
    # 只搜索前 2000 字符来提取职称信息
    search_text = text[:2000]
    for kw in title_keywords:
        if kw in search_text and kw not in titles:
            titles.append(kw)
    return "、".join(titles[:5])


async def collect_links(page) -> list[dict]:
    """收集页面上所有可能的教师链接"""
    links = await page.evaluate("""() => {
        const links = [];
        const seen = new Set();
        document.querySelectorAll('a[href]').forEach(a => {
            const text = (a.textContent || '').trim();
            const href = a.href;
            if (!text || !href) return;
            if (href.startsWith('javascript:') || href === '#') return;
            if (href.startsWith('mailto:') || href.startsWith('tel:')) return;
            if (/\\.(jpg|png|gif|pdf|doc|xls|ppt|rar|zip|mp4|avi)$/i.test(href)) return;
            const key = href;
            if (seen.has(key)) return;
            seen.add(key);
            links.push({text: text.substring(0, 80), href: href});
        });
        return links;
    }""")
    return links


async def scrape_detail(page, url: str) -> dict:
    """访问教师详情页，提取姓名、邮箱、职称"""
    result = {"name": "", "email": "", "title": "", "url": url}
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(0.3)
        page_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        if not page_text:
            return result

        # 提取邮箱
        clean_text = AT_RE.sub("@", page_text)
        emails = EMAIL_RE.findall(clean_text)
        valid_emails = [e for e in emails if not is_public_email(e)]

        if valid_emails:
            # 优先 nju.edu.cn 邮箱
            nju_emails = [e for e in valid_emails if "nju.edu.cn" in e]
            result["email"] = nju_emails[0] if nju_emails else valid_emails[0]

        # 从页面提取姓名
        name = await page.evaluate("""() => {
            const selectors = [
                'h1', 'h2', 'h3', '.name', '[class*="name"]', '[class*="title"]',
                '[class*="teacher"]', '[class*="profile"]',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const t = el.textContent.trim();
                    const m = t.match(/[\\u4e00-\\u9fff]{2,4}/);
                    if (m && t.length <= 50) {
                        const parts = t.split(/[\\s\\-–—|｜：:\\/]+/);
                        for (const p of parts) {
                            const n = p.trim();
                            if (/^[\\u4e00-\\u9fff]{2,3}$/.test(n)) return n;
                        }
                    }
                }
            }
            // 从页面标题提取
            const title = document.title || '';
            const parts = title.split(/[-–—|｜_\\s]+/);
            for (const p of parts) {
                const n = p.trim();
                if (/^[\\u4e00-\\u9fff]{2,3}$/.test(n)) return n;
            }
            return '';
        }""")
        if name:
            result["name"] = name.strip()

        # 从 URL 提取姓名（作为备选）
        if not result["name"]:
            url_path = urlparse(url).path
            path_parts = url_path.strip("/").split("/")
            for part in path_parts:
                name_from_url = extract_chinese_name(part)
                if name_from_url:
                    result["name"] = name_from_url
                    break

        # 提取职称
        result["title"] = extract_title_from_text(page_text)

    except Exception as e:
        pass

    return result


async def scrape_list_page(page, url: str) -> list[dict]:
    """抓取列表页，返回教师链接"""
    logger.info(f"  访问列表页: {url}")
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except Exception:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            logger.warning(f"  无法访问 {url}: {e}")
            return []

    await asyncio.sleep(1)

    # 滚动触发懒加载
    for _ in range(5):
        await page.evaluate("() => window.scrollBy(0, 600)")
        await asyncio.sleep(0.4)

    raw_links = await collect_links(page)
    logger.info(f"  原始链接数: {len(raw_links)}")

    # 筛选同域名的教师名字链接
    base_domain = urlparse(url).netloc
    teacher_links = []
    for link in raw_links:
        if base_domain not in link["href"]:
            continue
        if is_teacher_link(link["text"]):
            teacher_links.append(link)

    logger.info(f"  筛选后教师链接: {len(teacher_links)}")
    return teacher_links


async def main():
    logger.info(f"🎓 开始爬取 {DEPT_NAME} 教师邮箱")
    logger.info(f"   输出目录: {OUTPUT_DIR}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        # 第一阶段：收集所有教师链接
        all_teacher_links = {}
        for seed_url in SEED_URLS:
            links = await scrape_list_page(page, seed_url)
            for l in links:
                href = l["href"]
                if href not in all_teacher_links:
                    all_teacher_links[href] = l

        logger.info(f"\n📋 共找到 {len(all_teacher_links)} 位教师链接")

        if len(all_teacher_links) == 0:
            # 尝试访问网站首页找教师入口
            logger.info("  列表页无结果，尝试从首页寻找入口...")
            try:
                await page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)
                for _ in range(5):
                    await page.evaluate("() => window.scrollBy(0, 600)")
                    await asyncio.sleep(0.4)
                raw = await collect_links(page)
                logger.info(f"  首页链接: {len(raw)}")
                for link in raw:
                    text = link["text"]
                    href = link["href"]
                    if any(kw in text for kw in ["师资", "教师", "人员", "教授"]) and "cs.nju.edu.cn" in href:
                        logger.info(f"  发现师资入口: {text} → {href}")
                        sub_links = await scrape_list_page(page, href)
                        for l in sub_links:
                            if l["href"] not in all_teacher_links:
                                all_teacher_links[l["href"]] = l
            except Exception as e:
                logger.error(f"  首页探索失败: {e}")

        logger.info(f"  最终教师链接数: {len(all_teacher_links)}")

        # 第二阶段：逐个访问详情页
        results = []
        teacher_list = list(all_teacher_links.values())
        total = len(teacher_list)

        for i, link in enumerate(teacher_list):
            text = link["text"]
            href = link["href"]
            default_name = extract_chinese_name(text) or text

            detail = await scrape_detail(page, href)
            if not detail["name"]:
                detail["name"] = default_name
            detail["department"] = DEPT_NAME

            has_email = "✅" if detail["email"] else "❌"
            logger.info(f"  [{i+1}/{total}] {has_email} {detail['name']} → {detail.get('email', '无邮箱')}")

            results.append(detail)

            # 每 30 个休息一下
            if (i + 1) % 30 == 0:
                await asyncio.sleep(2)

        await context.close()
        await browser.close()

    # 第三阶段：去重和统计
    seen = set()
    deduped = []
    for r in results:
        key = (r["name"], r["email"], r["url"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    has_email = sum(1 for r in deduped if r["email"])
    logger.info(f"\n📊 统计: 总 {len(deduped)} 人, 有邮箱 {has_email} 人")

    # 第四阶段：导出 CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"南京大学_计算机科学与技术系_教师邮箱_{timestamp}.csv"
    csv_path = OUTPUT_DIR / filename

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["姓名", "邮箱", "学院", "职称", "主页链接"])
        writer.writeheader()
        for r in deduped:
            writer.writerow({
                "姓名": r["name"],
                "邮箱": r.get("email", ""),
                "学院": r["department"],
                "职称": r.get("title", ""),
                "主页链接": r["url"],
            })

    logger.info(f"\n💾 CSV 已保存: {csv_path}")
    logger.info(f"   文件: [FILES]")
    logger.info(f"   {filename} | 南京大学计算机科学与技术系教师邮箱")
    logger.info(f"   [/FILES]")

    return csv_path


if __name__ == "__main__":
    asyncio.run(main())
