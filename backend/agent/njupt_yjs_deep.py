"""
从 yjs.njupt.edu.cn 导师系统深度爬取所有学院教师邮箱
dfsc.htm 页面展示了所有学院教师姓名，但没有链接
需要探索 dsJbxxId 和其他可能的入口

策略：
1. 尝试各种可能的导师列表/搜索页面URL
2. 从 dsfc.htm 提取教师姓名，然后尝试在 yjs 站点内搜索
3. 尝试查找 dsgl 目录下的其他页面
"""
import asyncio
import csv
import re
import sys
import logging
from datetime import datetime
from pathlib import Path
from collections import Counter

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("pip install playwright")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

TASK_ID = "f8d29d14-aa64-4781-8efa-ee32cd310ec5"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / TASK_ID
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

TITLE_KW = [
    "教授", "副教授", "助理教授", "讲师", "研究员", "副研究员",
    "助理研究员", "工程师", "高级工程师", "院士", "博导", "硕导",
    "长江学者", "杰青", "优青", "博士后", "实验师", "高级实验师",
    "青年专聘教授", "校聘副教授", "预聘副教授", "特聘教授",
    "客座教授", "名誉教授", "国家级教学名师",
]

PUBLIC_LOCAL = {"webmaster", "admin", "info", "office", "master", "president",
                "xb", "xxgk", "jwc", "yjsc", "rsc", "gjc", "tw", "xsc"}


def is_public_email(email: str) -> bool:
    if not email:
        return True
    local = email.lower().split("@")[0]
    return any(kw in local for kw in PUBLIC_LOCAL)


def parse_at_sign(text: str) -> str:
    text = re.sub(r"\s*\[at\]\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(at\)\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*#@\s*", "@", text)
    text = re.sub(r"\s*\[@\]\s*", "@", text)
    return text


def extract_titles(text: str) -> str:
    return "、".join([kw for kw in TITLE_KW if kw in text][:5])


def is_chinese_name(text: str) -> bool:
    text = text.strip()
    if not re.fullmatch(r"[一-鿿]{2,4}", text):
        return False
    if text[-1] in "报组室部处委会局办系院所馆站网栏目页版":
        return False
    return True


async def explore_yjs_site(context) -> list[str]:
    """探索 yjs.njupt.edu.cn 站点，找到所有可访问的导师相关页面"""
    page = await context.new_page()
    discovered_urls = set()

    # 尝试各种可能的路径
    paths_to_try = [
        "/dsgl/",
        "/dsgl/nocontrol/",
        "/dsgl/nocontrol/college/dsfc.htm",
        "/dsgl/nocontrol/college/dsfcxq.htm",
        "/dsgl/nocontrol/college/index.htm",
        "/dsgl/nocontrol/college/main.htm",
        "/dsgl/nocontrol/college/search.htm",
        "/dsgl/nocontrol/college/list.htm",
        "/dsgl/nocontrol/index.htm",
        "/dsgl/nocontrol/dsfc.htm",
        "/dsgl/dsfc.htm",
        "/dsgl/dsfc.htm?dslb=1",  # 导师列表
        "/dsgl/dsfc.htm?dslb=2",
        "/dsgl/dsfc.htm?dslb=3",
        "/dsgl/nocontrol/college/dsfc.htm?dslb=1",
        "/",
        "/index.htm",
    ]

    for p in paths_to_try:
        url = f"https://yjs.njupt.edu.cn{p}"
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=10000)
            status = resp.status if resp else "N/A"
            if status == 200 or status == 304:
                discovered_urls.add(url)
                # 获取页面内容提示
                body = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 200) : ''")
                logger.info(f"  ✅ {url} → {body[:80]}")

                # 收集此页面上的链接
                links = await page.evaluate("""() => {
                    const ls = [];
                    document.querySelectorAll('a[href]').forEach(a => {
                        const h = a.href;
                        if (h && !h.startsWith('javascript:') && !h.includes('mailto:')) {
                            ls.push(h);
                        }
                    });
                    return ls;
                }""")
                for l in links:
                    if "yjs.njupt.edu.cn" in l:
                        discovered_urls.add(l)
        except Exception:
            pass

    await page.close()
    return list(discovered_urls)


async def parse_dsfc_html(context) -> dict[str, list[str]]:
    """解析 dsfc.htm 页面，提取各学院教师姓名

    返回: {学院名: [教师姓名列表]}
    """
    page = await context.new_page()
    college_teachers = {}

    try:
        await page.goto("https://yjs.njupt.edu.cn/dsgl/nocontrol/college/dsfc.htm",
                         wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2)

        # 获取页面HTML（不只是文本）
        html = await page.evaluate("() => document.body ? document.body.innerHTML : ''")
        text = await page.evaluate("() => document.body ? document.body.innerText : ''")

        # 解析文本：按学科代码分组，然后学院-教师列表
        # 格式: "0701 数学 - 理学院 陈艳萍 纪海峰 ..."
        lines = text.split("\n")
        current_college = ""
        current_subject = ""

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 跳过页面头
            if any(h in line for h in ["南京邮电大学研究生导师简介", "导师属性", "学术型博导",
                                         "专业型博导", "学术型硕导", "专业型硕导", "兼职导师"]):
                continue

            # 检测学科代码行（如 "0701 数学"）
            subject_match = re.match(r"^(\d{4})\s+(\S+)", line)
            if subject_match:
                current_subject = subject_match.group(2)
                continue

            # 解析 "学科 - 学院 姓名1 姓名2 ..." 模式
            # 比如 "0701 数学	-	理学院	陈艳萍	纪海峰	..."
            parts = re.split(r"\s+", line)
            if not parts:
                continue

            # 尝试找到学院名
            college_idx = -1
            for i, p in enumerate(parts):
                if re.search(r"(学院|学部|体育部|中心)", p):
                    college_idx = i
                    current_college = p
                    break

            # 提取学院后面的姓名列表
            if college_idx >= 0 and college_idx + 1 < len(parts):
                names = []
                for i in range(college_idx + 1, len(parts)):
                    name = parts[i].rstrip("*")  # 去掉兼职标记
                    if is_chinese_name(name):
                        names.append(name)
                if current_college not in college_teachers:
                    college_teachers[current_college] = []
                college_teachers[current_college].extend(names)

        logger.info(f"  📊 从 dsfc.htm 解析到 {sum(len(v) for v in college_teachers.values())} 个教师, {len(college_teachers)} 个学院")
        for c, names in sorted(college_teachers.items()):
            logger.info(f"    {c}: {len(names)} 人")

    except Exception as e:
        logger.warning(f"  解析 dsfc.htm 失败: {e}")
    finally:
        await page.close()

    return college_teachers


async def try_search_teacher(context, name: str, college: str) -> dict | None:
    """通过搜索或url推断尝试访问教师详情页"""
    page = await context.new_page()
    result = None

    try:
        # 尝试在 yjs 站点搜索这个教师
        # 方法1: 尝试常见URL模式
        # yjs.njupt.edu.cn 是否有搜索功能？

        # 先尝试访问 yjs 首页
        await page.goto("https://yjs.njupt.edu.cn/", wait_until="domcontentloaded", timeout=10000)
        await asyncio.sleep(1)

        # 尝试找搜索框
        search_inputs = await page.evaluate("""() => {
            const inputs = [];
            document.querySelectorAll('input[type="text"], input[type="search"], input[name], input[placeholder]').forEach(el => {
                inputs.push({id: el.id, name: el.name, placeholder: el.placeholder});
            });
            return inputs;
        }""")
        logger.info(f"  yjs首页搜索框: {search_inputs}")

        if search_inputs:
            # 尝试搜索教师姓名
            for si in search_inputs[:1]:
                selector = f"#{si['id']}" if si['id'] else f"input[name='{si['name']}']" if si['name'] else "input[type='text']"
                try:
                    await page.fill(selector, name)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(2)

                    # 检查搜索结果
                    body = await page.evaluate("() => document.body ? document.body.innerText.substring(0, 500) : ''")
                    if name in body:
                        logger.info(f"  搜索 {name} 成功: {body[:100]}")
                except Exception:
                    pass
    except Exception:
        pass
    finally:
        await page.close()

    return result


async def main():
    logger.info("=" * 60)
    logger.info("🔍 yjs.njupt.edu.cn 深度探索")
    logger.info("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=ua)

        # 步骤1: 探索 yjs 站点
        logger.info("\n📌 步骤1: 探索 yjs 站点可用页面")
        urls = await explore_yjs_site(ctx)

        # 步骤2: 解析 dsfc.htm 获取教师名单
        logger.info("\n📌 步骤2: 解析 dsfc.htm 获取全校教师名单")
        college_teachers = await parse_dsfc_html(ctx)

        # 步骤3: 尝试从已知的详情页模式获取更多信息
        # 已知模式：https://cs.njupt.edu.cn/18762/list.htm → 各教师详情页
        logger.info("\n📌 步骤3: 尝试在 cs.njupt.edu.cn 找其他学院入口")

        # 尝试探索 cs.njupt.edu.cn 上是否有其他学院的入口
        cs_page = await ctx.new_page()
        cs_links = []
        try:
            await cs_page.goto("https://cs.njupt.edu.cn", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)

            cs_links = await cs_page.evaluate("""() => {
                const ls = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    ls.push({t: a.textContent.trim().substring(0, 60), h: a.href});
                });
                return ls;
            }""")

            # 找指向其他学院的链接
            for l in cs_links:
                if any(kw in l["t"] for kw in ["学院", "通信", "自动化", "材料", "物联网", "理学",
                                                  "地理", "现代邮政", "传媒", "管理", "经济",
                                                  "马克思", "社会", "外国语", "教育科学",
                                                  "贝尔", "海外", "继续", "体育"]):
                    logger.info(f"  跨学院链接: {l['t']} → {l['h'][:100]}")
        except Exception:
            pass
        finally:
            await cs_page.close()

        await ctx.close()
        await browser.close()

    # 报告
    logger.info(f"\n{'='*60}")
    logger.info("📊 发现汇总")
    logger.info(f"  yjs 站点可访问页面: {len(urls)}")
    logger.info(f"  从 dsfc.htm 发现学院: {len(college_teachers)}")
    total = sum(len(v) for v in college_teachers.values())
    logger.info(f"  从 dsfc.htm 发现教师: {total}")


if __name__ == "__main__":
    asyncio.run(main())
