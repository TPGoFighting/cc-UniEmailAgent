"""
南邮学院发现脚本 — 从主站获取各学院真实URL和教师列表入口
"""
import asyncio
import re
import json
import logging
from pathlib import Path

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "f8d29d14-aa64-4781-8efa-ee32cd310ec5"


async def discover_from_main_site(context) -> list[dict]:
    """从南邮主站 www.njupt.edu.cn 发现教学单位链接"""
    page = await context.new_page()
    colleges = []

    try:
        # 访问主站
        await page.goto("https://www.njupt.edu.cn", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # 找"组织机构"或"教学单位"入口
        all_links = await page.evaluate("""() => {
            const links = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const text = (a.textContent || '').trim();
                const href = a.href;
                if (!text || !href || href.startsWith('javascript:') || href === '#') return;
                links.push({text: text.substring(0, 100), url: href});
            });
            return links;
        }""")

        logger.info(f"  主站共 {len(all_links)} 个链接")

        # 找组织/学院相关入口
        org_links = [l for l in all_links if any(
            kw in l["text"] for kw in ["组织机构", "教学单位", "学院设置", "院系", "教学机构",
                                        "学院", "研究机构", "二级学院"]
        )]
        for ol in org_links:
            logger.info(f"  组织机构入口: {ol['text'][:40]} → {ol['url'][:80]}")

        # 如果找到了教学单位页面，访问它
        teaching_unit_url = None
        for ol in org_links:
            if any(kw in ol["text"] for kw in ["教学单位", "学院设置", "院系", "教学机构", "二级学院"]):
                teaching_unit_url = ol["url"]
                break

        if not teaching_unit_url:
            teaching_unit_url = "https://www.njupt.edu.cn/xxgk/jxjj.htm"

        if teaching_unit_url:
            logger.info(f"\n  访问教学单位页面: {teaching_unit_url}")
            await page.goto(teaching_unit_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)

            unit_links = await page.evaluate("""() => {
                const links = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    const text = (a.textContent || '').trim();
                    const href = a.href;
                    if (!text || !href || href.startsWith('javascript:') || href === '#') return;
                    if (href === 'https://www.njupt.edu.cn') return;
                    links.push({text: text.substring(0, 100), url: href});
                });
                return links;
            }""")

            # 提取学院链接（含有"学院""部""中心"的链接）
            for link in unit_links:
                text = link["text"]
                url = link["url"]
                if re.search(r"(学院|学部|中心|研究院|体育部)", text) and len(text) < 30:
                    colleges.append({"name": text.strip(), "url": url})
                    logger.info(f"  🏫 {text.strip()} → {url}")

        # 如果教学机构页面没找到，尝试从主页直接找
        if not colleges:
            logger.info("  从主站链接直接搜索学院...")
            for link in all_links:
                text = link["text"].strip()
                url = link["url"]
                if re.search(r"(学院|学部)", text) and len(text) < 30:
                    if "njupt.edu.cn" in url and url != "https://www.njupt.edu.cn":
                        colleges.append({"name": text, "url": url})

        # 去重
        seen = set()
        unique = []
        for c in colleges:
            if c["url"] not in seen:
                seen.add(c["url"])
                unique.append(c)

        logger.info(f"\n📊 发现 {len(unique)} 个教学单位")
        return unique

    except Exception as e:
        logger.error(f"  主站探索失败: {e}")
        return []
    finally:
        await page.close()


async def find_teacher_list(context, college: dict) -> list[str]:
    """访问学院网站，找到教师列表页URL"""
    page = await context.new_page()
    teacher_urls = []

    try:
        await page.goto(college["url"], wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2)

        links = await page.evaluate("""() => {
            const links = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const text = (a.textContent || '').trim();
                const href = a.href;
                if (!text || !href || href.startsWith('javascript:') || href === '#') return;
                links.push({text: text.substring(0, 100), url: href});
            });
            return links;
        }""")

        for link in links:
            if any(kw in link["text"] for kw in ["师资", "教师名录", "教师队伍", "导师", "教师列表"]):
                if len(link["text"]) < 15:
                    teacher_urls.append(link["url"])

        logger.info(f"  {college['name']}: 找到 {len(teacher_urls)} 个师资入口")
        return teacher_urls

    except Exception as e:
        logger.warning(f"  {college['name']} 访问失败: {str(e)[:60]}")
        return []
    finally:
        await page.close()


async def main():
    logger.info("=" * 60)
    logger.info("🔍 南邮教学单位发现")
    logger.info("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=ua)

        # 步骤1: 发现学院
        colleges = await discover_from_main_site(ctx)
        await ctx.close()

        if not colleges:
            logger.info("未从主站发现学院，使用预设列表")
            colleges = [
                {"name": "通信与信息工程学院", "url": "https://ctie.njupt.edu.cn"},
                {"name": "计算机学院/软件学院/网络空间安全学院", "url": "https://cs.njupt.edu.cn"},
                {"name": "自动化学院/人工智能学院", "url": "https://coa.njupt.edu.cn"},
                {"name": "材料科学与工程学院", "url": "https://iam.njupt.edu.cn"},
                {"name": "物联网学院", "url": "https://iot.njupt.edu.cn"},
                {"name": "理学院", "url": "https://cos.njupt.edu.cn"},
                {"name": "管理学院", "url": "https://sm.njupt.edu.cn"},
                {"name": "经济学院", "url": "https://se.njupt.edu.cn"},
                {"name": "外国语学院", "url": "https://sfs.njupt.edu.cn"},
                {"name": "传媒与艺术学院", "url": "https://cma.njupt.edu.cn"},
                {"name": "马克思主义学院", "url": "https://marx.njupt.edu.cn"},
                {"name": "社会与人口学院", "url": "https://ssp.njupt.edu.cn"},
                {"name": "教育科学与技术学院", "url": "https://est.njupt.edu.cn"},
                {"name": "地理与生物信息学院", "url": "https://cgb.njupt.edu.cn"},
                {"name": "现代邮政学院", "url": "https://mpc.njupt.edu.cn"},
                {"name": "贝尔英才学院", "url": "https://bel.njupt.edu.cn"},
                {"name": "海外教育学院", "url": "https://oice.njupt.edu.cn"},
                {"name": "继续教育学院", "url": "https://jjy.njupt.edu.cn"},
                {"name": "体育部", "url": "https://tyb.njupt.edu.cn"},
            ]

        logger.info(f"\n📋 共 {len(colleges)} 个教学单位")

        # 步骤2: 对每个学院，找教师列表页
        logger.info(f"\n📌 查找各学院教师列表页...")
        all_college_data = []

        for college in colleges:
            try:
                ctx2 = await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=ua)
                teacher_urls = await find_teacher_list(ctx2, college)
                await ctx2.close()

                all_college_data.append({
                    "name": college["name"],
                    "url": college["url"],
                    "teacher_pages": teacher_urls,
                })
            except Exception as e:
                logger.warning(f"  {college['name']} 失败: {e}")

        await browser.close()

    # 保存发现结果
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result_file = OUTPUT_DIR / "college_discovery.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(all_college_data, f, ensure_ascii=False, indent=2)

    # 报告
    logger.info(f"\n{'='*60}")
    logger.info("📊 发现汇总")
    for cd in all_college_data:
        if cd["teacher_pages"]:
            logger.info(f"  ✅ {cd['name']}: {cd['teacher_pages']}")
        else:
            logger.info(f"  ⚠️ {cd['name']}: 未找到师资入口")
    logger.info(f"\n💾 结果已保存到 {result_file}")


if __name__ == "__main__":
    asyncio.run(main())
