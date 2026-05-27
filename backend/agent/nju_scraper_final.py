"""南京大学全量教师爬虫 — 最终版。

使用经过三轮验证的正确院系URL，一次完成全量抓取。
"""

import asyncio, json, re, time
from pathlib import Path
from agent.exporter import export_xlsx
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "outputs"

# ============================================================
# 经过验证的正确院系URL
# ============================================================
DEPTS = [
    # === 文科 ===
    ("文学院", "https://chin.nju.edu.cn/szdw/index.html"),
    ("历史学院", "https://history.nju.edu.cn/28475/list.htm"),
    ("哲学系", "https://philo.nju.edu.cn/szdw/list.htm"),
    ("法学院", "https://law.nju.edu.cn/szdw/zzjs1/js.htm"),
    ("商学院", "https://nubs.nju.edu.cn/8878/list.htm"),
    ("外国语学院", "https://sfs.nju.edu.cn/szdw/index.html"),
    ("政府管理学院", "https://public.nju.edu.cn/szdw/list.htm"),
    ("信息管理学院", "https://im.nju.edu.cn/szdw/list.htm"),
    ("社会学院", "https://sociology.nju.edu.cn/szdw/list.htm"),
    ("新闻传播学院", "https://jc.nju.edu.cn/jzyg/zzjs.htm"),
    ("艺术学院", "https://art.nju.edu.cn/szdw/list.htm"),
    ("马克思主义学院", "https://marxism.nju.edu.cn/szdw/list.htm"),
    ("体育部", "https://tyb.nju.edu.cn/jbgk/szdw/index.html"),
    ("海外教育学院", "https://hwxy.nju.edu.cn/szdw/list.htm"),
    ("匡亚明学院", "https://dii.nju.edu.cn/lsjs/list.htm"),
    ("教育研究院", "https://edu.nju.edu.cn/8746/list.htm"),
    ("中美文化研究中心", "https://hnc.nju.edu.cn/szll.htm"),

    # === 理科 ===
    ("数学学院", "https://math.nju.edu.cn/jzyg/apypl/index.html"),
    ("物理学院", "https://physics.nju.edu.cn/szdw/index.html"),
    ("天文与空间科学学院", "https://astronomy.nju.edu.cn/szdw/list.htm"),
    ("化学化工学院", "https://chem.nju.edu.cn/szdw/list.htm"),
    ("地理与海洋科学学院", "https://sgos.nju.edu.cn/62681/list.htm"),
    ("地球科学与工程学院", "https://es.nju.edu.cn/szdw/list.htm"),
    ("生命科学学院", "https://life.nju.edu.cn/szdw/list.htm"),
    ("大气科学学院", "https://atmos.nju.edu.cn/szdw/list.htm"),

    # === 工科 ===
    ("计算机科学与技术系", "https://cs.nju.edu.cn/1651/list.htm"),
    ("软件学院", "https://software.nju.edu.cn/szll/szdw/index.html"),
    ("人工智能学院", "https://ai.nju.edu.cn/people/list.htm"),
    ("电子科学与工程学院", "https://ese.nju.edu.cn/szdw/list.htm"),
    ("现代工程与应用科学学院", "https://eng.nju.edu.cn/szdw/list.htm"),
    ("环境学院", "https://hjxy.nju.edu.cn/szdw/index.html"),
    ("建筑与城市规划学院", "https://arch.nju.edu.cn/szdw/index.html"),
    ("工程管理学院", "https://sme.nju.edu.cn/2003/list.htm"),

    # === 医科 ===
    ("医学院", "https://med.nju.edu.cn/10649/list.htm"),

    # === 交叉/新兴 ===
    ("数字经济与管理学院", "https://sdem.nju.edu.cn/59579/list.htm"),
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
AT_RE = re.compile(r"\s*\[at\]\s*|\s*\(at\)\s*|\s*#@\s*|\s*\[@\]\s*", re.IGNORECASE)
NAV_WORDS = {
    "首页", "概况", "简介", "领导", "部门", "制度", "招聘", "通知", "公告", "新闻",
    "动态", "科研", "党建", "团建", "学生", "招生", "就业", "合作", "联系", "关于",
    "下载", "办事", "指南", "登录", "注册", "加入", "返回", "更多", "查看",
    "详情", "关闭", "确定", "取消", "中文", "EN", "MORE",
}


def extract_emails(text):
    return list(set(EMAIL_RE.findall(AT_RE.sub("@", text))))


async def scrape_dept(context, name, url):
    results = []
    page = await context.new_page()

    try:
        logger.info(f"抓取: {name}")

        # 访问师资页面
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(2)

        # 收集教师链接
        # 策略：URL 不是导航页 + 链接文本以中文名开头(2-3字) = 教师详情页
        links = await page.evaluate("""() => {
            const links = [];
            const seen = new Set();

            document.querySelectorAll('a').forEach(a => {
                const text = (a.textContent || '').trim();
                const href = (a.href || '').trim();
                if (!href || seen.has(href) || !text || text.length > 40) return;
                if (href.startsWith('javascript:') || href.startsWith('#') || href.startsWith('mailto:')) return;
                if (/\\.(jpg|png|gif|pdf|doc|xls|ppt|rar|zip)$/i.test(href)) return;

                // 黑名单：常见非人名的中文词
                const blacklist = new Set([
                    '首页','网站首','学院概','历史渊','院系领','专业设','规章制','诚聘英',
                    '师资队','在职教','现任教','退休教','荣休教','访问学','行政管','人才培',
                    '招生信','本科教','研究生','继续教','科学研','科研机','学术活','学术交',
                    '学生工','党团建','校友工','国际化','合作项','联系方','相关下','用户登',
                    '教研室','教授','副教授','博士后','讲师','中德所','经济学院','管理学院',
                    '所有教师','称号人才','各系导航','按系科','按职称','师资力量',
                ]);

                // 文本需以中文名开头（2-3字）
                const startsWithName = /^[\\u4e00-\\u9fff]{2,3}(\\s|\\d|$|[A-Z])/.test(text)
                    || /^[\\u4e00-\\u9fff]{2}[·•][\\u4e00-\\u9fff]{1,2}/.test(text);
                if (!startsWithName) return;

                // 黑名单检查
                if (blacklist.has(text.split(/\\s|\\d/)[0].trim())) return;

                // 排除导航页面URL
                if (/xygk|rcpy|zsjy|xsyd|dqjs|xsgz|hzjl|xyyfz|login|registe/i.test(href)) return;
                // 排除纯数字ID的list页面（如 /8878/list.htm 但允许 /atl/list.htm）
                if (/\\/\\d+\\/list\\.htm$/i.test(href) && !/[a-z]/i.test(href.split('/list.htm')[0].split('/').pop() || '')) return;

                seen.add(href);
                links.push({text, href});
            });
            return links;
        }""")

        logger.info(f"  {name}: {len(links)} 位教师")

        seen_urls = set()
        for link in links:
            href = link["href"]
            if href in seen_urls:
                continue
            seen_urls.add(href)

            text = link["text"]
            nm = re.match(r"^([一-鿿]{2,3})", text)
            teacher_name = nm.group(1) if nm else text

            # 快速访问详情页
            try:
                await page.goto(href, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(0.4)
                page_text = await page.evaluate("() => document.body?.innerText || ''")
                emails = extract_emails(page_text)
                email = ""
                if emails:
                    nju = [e for e in emails if "nju.edu.cn" in e]
                    email = nju[0] if nju else emails[0]

                # 姓名
                name_from_page = await page.evaluate("""() => {
                    for (const sel of ['h1','h2','h3','.name','[class*="name"]']) {
                        const el = document.querySelector(sel);
                        if (el) {
                            const t = el.textContent.trim();
                            if (/^[\\u4e00-\\u9fff]{2,4}/.test(t)) return t.split(/\\s|-|–|｜/)[0].trim();
                        }
                    }
                    return '';
                }""")
                if name_from_page:
                    teacher_name = name_from_page

                # 职称
                title = ""
                for line in page_text.split("\n"):
                    line = line.strip()
                    if len(line) > 50: continue
                    for kw in ["教授","副教授","讲师","助理教授","研究员","副研究员","院士","博导","青年学者","特聘"]:
                        if kw in line:
                            title = line
                            break
                    if title: break

                results.append({
                    "name": teacher_name,
                    "email": email,
                    "department": name,
                    "title": title,
                    "url": href,
                })
            except Exception:
                results.append({
                    "name": teacher_name,
                    "email": "",
                    "department": name,
                    "title": "",
                    "url": href,
                })

    except Exception as e:
        logger.warning(f"  {name}: 错误 - {e}")
    finally:
        await page.close()

    return results


async def main():
    from playwright.async_api import async_playwright

    OUTPUT_DIR.mkdir(exist_ok=True)
    PROGRESS_FILE = OUTPUT_DIR / "final_scrape_progress.json"

    progress = {"completed": [], "all_results": []}
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            progress = json.load(f)

    completed = set(progress["completed"])
    all_results = progress["all_results"]
    pending = [(n, u) for n, u in DEPTS if n not in completed]

    logger.info(f"总计 {len(DEPTS)} 个院系，已完成 {len(completed)}，待处理 {len(pending)}")

    if not pending:
        logger.info("全部完成!")
        if all_results:
            export_results(all_results)
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})

        try:
            for i, (name, url) in enumerate(pending):
                logger.info(f"[{i+1}/{len(pending)}] {name}")
                dept_results = await scrape_dept(context, name, url)
                all_results.extend(dept_results)
                completed.add(name)

                with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                    json.dump({"completed": list(completed), "all_results": all_results}, f, ensure_ascii=False)

                logger.info(f"  {name}: {len(dept_results)} 人 (累计 {len(all_results)})")
                await asyncio.sleep(0.5)
        finally:
            await browser.close()

    if all_results:
        export_results(all_results)
    PROGRESS_FILE.unlink(missing_ok=True)


def export_results(results: list[dict]):
    seen = set()
    deduped = []
    for r in results:
        key = (r["name"], r["email"], r["department"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    path = export_xlsx(deduped, "南京大学_教师名录_完整版")
    emails = sum(1 for r in deduped if r["email"])
    titles = sum(1 for r in deduped if r["title"])
    depts = {}
    for r in deduped:
        d = r["department"]
        depts[d] = depts.get(d, 0) + 1

    logger.info(f"===== 最终结果 =====")
    logger.info(f"总教师: {len(deduped)} | 邮箱: {emails} | 职称: {titles} | 院系: {len(depts)}")
    for d, c in sorted(depts.items(), key=lambda x: -x[1]):
        logger.info(f"  {d}: {c}")

    return path


if __name__ == "__main__":
    asyncio.run(main())
