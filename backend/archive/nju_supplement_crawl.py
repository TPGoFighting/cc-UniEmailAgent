"""南京大学综合补充爬取 — 针对邮箱率低和人数明显不足的学院。

分批并行爬取，覆盖 25 个学院。每个学院使用已知最佳 URL，未知时从首页探测。
"""

import asyncio, re, logging, json, csv, os, sys
from pathlib import Path
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"
PROGRESS_FILE = OUTPUT_DIR / "nju_supplement_progress.json"

# ========== 学院配置 ==========
# Group A: 邮箱率极低但人数多
# Group B: 人数明显不足（＜预期值一半）
TARGET_DEPTS = [
    # === Group A: 高人数 + 低邮箱率 ===
    {"name": "政府管理学院", "urls": ["http://public.nju.edu.cn/szdw", "http://public.nju.edu.cn/szdw/list.htm"]},
    {"name": "大学外语部", "urls": ["http://dafls.nju.edu.cn", "http://dafls.nju.edu.cn/szdw/list.htm"]},
    {"name": "文学院", "urls": ["http://chin.nju.edu.cn", "http://chin.nju.edu.cn/szdw/index.html"]},
    {"name": "外国语学院", "urls": ["http://sfs.nju.edu.cn", "http://sfs.nju.edu.cn/szdw/list.htm"]},
    {"name": "计算机学院", "urls": ["http://cs.nju.edu.cn/1651/list.htm", "http://cs.nju.edu.cn/2639/list.htm"]},
    {"name": "人工智能学院", "urls": ["http://ai.nju.edu.cn", "http://ai.nju.edu.cn/szdw/list.htm"]},

    # === Group B: 人数明显不足 ===
    {"name": "环境学院", "urls": ["http://hjxy.nju.edu.cn/szdw/index.html"]},
    {"name": "信息管理学院", "urls": ["http://im.nju.edu.cn/szdw/list.htm"]},
    {"name": "法学院", "urls": ["https://law.nju.edu.cn/szdw/zzjs1/js.htm"]},
    {"name": "化学化工学院", "urls": ["http://chem.nju.edu.cn", "http://chem.nju.edu.cn/szdw/list.htm"]},
    {"name": "历史学院", "urls": ["http://history.nju.edu.cn", "http://history.nju.edu.cn/szdw/list.htm"]},
    {"name": "匡亚明学院", "urls": ["http://dii.nju.edu.cn", "http://dii.nju.edu.cn/szll/szdw/list.htm", "http://dii.nju.edu.cn/lsjs/list.htm"]},
    {"name": "现代工程与应用科学学院", "urls": ["http://eng.nju.edu.cn", "http://eng.nju.edu.cn/szdw/list.htm"]},
    {"name": "电子科学与工程学院", "urls": ["http://ese.nju.edu.cn", "http://ese.nju.edu.cn/szdw/list.htm"]},
    {"name": "体育部", "urls": ["http://tyb.nju.edu.cn/jbgk/szdw/index.html", "http://sports.nju.edu.cn/szdw/list.htm"]},
    {"name": "地球科学与工程学院", "urls": ["http://es.nju.edu.cn", "http://es.nju.edu.cn/szdw/list.htm"]},
    {"name": "生物医学工程学院", "urls": ["http://bme.nju.edu.cn", "http://bme.nju.edu.cn/szdw/list.htm"]},
    {"name": "马克思主义学院", "urls": ["http://marxism.nju.edu.cn/szdw/js.htm", "http://marxism.nju.edu.cn/szdw/list.htm"]},
    {"name": "工程管理学院", "urls": ["http://sme.nju.edu.cn/2003/list.htm"]},
    {"name": "社会学院", "urls": ["http://sociology.nju.edu.cn/szdw/list.htm"]},
    {"name": "南京赫尔辛基大气与地球系统科学学院", "urls": ["http://nh.nju.edu.cn", "http://nh.nju.edu.cn/szdw/list.htm"]},
    {"name": "智能科学与技术学院", "urls": ["https://is.nju.edu.cn/57159/list.htm", "https://is.nju.edu.cn/main.htm"]},
    {"name": "数字经济与管理学院", "urls": ["https://sdem.nju.edu.cn/59579/list.htm", "https://sdem.nju.edu.cn/main.htm"]},
    {"name": "国际关系学院", "urls": ["https://sis.nju.edu.cn", "https://sis.nju.edu.cn/szdw/list.htm"]},
    {"name": "机器人与自动化学院", "urls": ["https://ra.nju.edu.cn", "https://ra.nju.edu.cn/szdw/list.htm"]},
]

# 导航黑名单
NAV_BLACKLIST = {
    "首页", "网站", "概况", "简介", "领导", "部门", "制度", "招聘", "通知", "公告",
    "新闻", "动态", "科研", "党建", "团建", "学生", "招生", "就业", "合作", "联系",
    "关于", "下载", "办事", "指南", "登录", "注册", "加入", "返回", "更多", "查看",
    "详情", "关闭", "确定", "取消", "中文", "英文",
    "博士后", "教研室", "实验室", "研究所", "中心",
    "科学研究", "学术", "交流", "国际", "版权所有", "友情链接",
    "人才培养", "科学研究", "社会服务", "文化传承", "国际合作",
    "校友", "基金会", "图书馆", "学报", "出版社", "医院", "附属",
    "书记信箱", "院长信箱", "联系我们", "师资队伍", "教师名录",
    "教授", "副教授", "讲师", "博士", "硕士", "本科", "教育",
    "校内", "链接", "网站地图", "管理", "教师", "师资",
}

# 合法职称关键词
TITLE_KW = ["教授", "副教授", "助理教授", "讲师", "研究员", "副研究员",
            "助理研究员", "工程师", "高级工程师", "院士", "博导", "硕导",
            "长江学者", "杰青", "优青", "院长", "副院长", "系主任",
            "副主任", "所长", "副所长", "博士后", "高级实验师", "实验师",
            "青年学者", "特聘", "助理教授"]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
AT_RE = re.compile(r"\s*\[at\]\s*|\s*\(at\)\s*|\s*#@\s*|\s*\[@\]\s*", re.IGNORECASE)

PUBLIC_EMAIL_PREFIXES = {
    "webmaster", "admin", "office", "info", "master", "root", "postmaster",
    "wxyxz", "xwcb", "bgs", "dangzheng", "yuanban", "dangban", "renshi",
    "jiaowu", "xuegong", "tuanwei", "yanjiusheng", "gysj", "gyyz", "glxb",
}

def extract_emails(text):
    cleaned = AT_RE.sub("@", text)
    all_emails = EMAIL_RE.findall(cleaned)
    return [e.lower() for e in all_emails if not e.split("@")[0].lower() in PUBLIC_EMAIL_PREFIXES]

def looks_like_teacher_name(text):
    text = text.strip()
    if not text: return False
    m = re.match(r"^([一-鿿]{2,4})", text)
    if not m: return False
    name = m.group(1)
    if name in NAV_BLACKLIST: return False
    if text in NAV_BLACKLIST: return False
    return True

async def collect_all_links(page):
    return await page.evaluate("""() => {
        const links = []; const seen = new Set();
        document.querySelectorAll('a').forEach(a => {
            const text = (a.textContent || '').trim();
            const href = (a.href || '').trim();
            if (!href || seen.has(href) || !text) return;
            seen.add(href);
            links.push({text, href});
        });
        return links;
    }""")

async def find_faculty_url(page, base_url: str, max_depth=2) -> str | None:
    """归递地在首页和子页面中寻找师资链接。"""
    FACULTY_KW = ["师资队伍", "师资力量", "教师名录", "教师队伍", "教职员工",
                   "专任教师", "现任教师", "在职教师", "faculty", "teacher", "people", "staff"]

    visited = set()
    to_visit = [base_url]

    for _ in range(max_depth):
        next_batch = []
        for url in to_visit:
            if url in visited: continue
            visited.add(url)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(1)

                # 在当前页面搜索师资链接
                links = await page.evaluate(f"""() => {{
                    const kws = {json.dumps(FACULTY_KW)};
                    const results = [];
                    document.querySelectorAll('a').forEach(a => {{
                        const text = (a.textContent || '').trim();
                        const href = (a.href || '').trim();
                        if (!href || !text) return;
                        const lower = text.toLowerCase();
                        for (const kw of kws) {{
                            if (lower.includes(kw) || href.toLowerCase().includes(kw)) {{
                                results.push({{text: text.slice(0,30), href, score: kws.indexOf(kw)}});
                                break;
                            }}
                        }}
                    }});
                    results.sort((a,b) => a.score - b.score);
                    return results.map(r => r.href);
                }}""")
                if links:
                    return links[0]

                # 收集下一批页面（首页的子链接）
                if _ == 0:  # 只在第一层收集子页面
                    all_l = await collect_all_links(page)
                    for l in all_l:
                        if l["href"].startswith(base_url.rstrip("/") + "/") or "/szdw/" in l["href"] or "/szll/" in l["href"]:
                            next_batch.append(l["href"])
            except:
                pass
        to_visit = next_batch[:10]

    return None

async def scrape_detail(page, url: str, dept_name: str, default_name: str) -> dict:
    result = {"name": default_name, "email": "", "department": dept_name, "title": "", "url": url}
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(0.5)
        page_text = await page.evaluate("() => document.body?.innerText || ''")
        if not page_text:
            return result

        # 邮箱提取
        emails = extract_emails(page_text)
        if emails:
            nju = [e for e in emails if "nju.edu.cn" in e]
            result["email"] = nju[0] if nju else emails[0]

        # 姓名提取
        name_from = await page.evaluate("""() => {
            for (const sel of ['h1','h2','h3','.name','.title','[class*="name"]','[class*="title"]']) {
                const el = document.querySelector(sel);
                if (el) {
                    const t = el.textContent.trim();
                    const m = t.match(/[\\u4e00-\\u9fff]{2,4}/);
                    if (m && t.length <= 40) return t.split(/\\s|-|–|—|\\||｜|：|:/)[0].trim();
                }
            }
            const parts = (document.title || '').split(/[-–—|｜_\\s]+/);
            for (const p of parts) {
                if (/^[\\u4e00-\\u9fff]{2,3}$/.test(p.trim())) return p.trim();
            }
            return '';
        }""")
        if name_from:
            result["name"] = name_from.strip()

        # 职称提取
        for line in page_text.split("\n"):
            line = line.strip()
            if len(line) > 80: continue
            for kw in TITLE_KW:
                if kw in line:
                    result["title"] = line
                    break
            if result["title"]: break

    except: pass
    return result

async def filter_teacher_links(page, raw_links, dept_name):
    """过滤教师链接，进入详情页提取邮箱。"""
    results = []
    seen_urls = set()
    seen_names = set()

    filtered = []
    for link in raw_links:
        href = link.get("href", "").strip()
        text = link.get("text", "").strip()
        if not href or not text: continue
        if href in seen_urls: continue
        if any(href.startswith(p) for p in ("javascript:", "#", "mailto:", "tel:")): continue
        if re.search(r"\.(jpg|png|gif|pdf|doc|xls|ppt|rar|zip|mp4|avi)$", href, re.I): continue
        if not looks_like_teacher_name(text): continue
        if len(text) > 50: continue
        seen_urls.add(href)
        filtered.append(link)

    # 逐个访问详情页
    for i, link in enumerate(filtered):
        href = link["href"]
        text = link["text"].strip()
        nm = re.match(r"^([一-鿿]{2,4})", text)
        teacher_name = nm.group(1) if nm else text

        if teacher_name in seen_names and len(filtered) > 10:
            continue  # 只在大列表中跳过重名

        detail = await scrape_detail(page, href, dept_name, teacher_name)
        if detail["name"]:
            if detail["name"] not in seen_names:
                seen_names.add(detail["name"])
                results.append(detail)
        else:
            seen_names.add(teacher_name)
            results.append(detail)

        if (i+1) % 20 == 0:
            logger.info(f"  [{dept_name}] 进度: {i+1}/{len(filtered)}")

    return results

async def scrape_dept(context, config):
    """爬取单个学院。改进版：始终尝试所有URL，不会因首页有5个"名字"就停止。"""
    name = config["name"]
    urls = config["urls"]
    results = []

    page = await context.new_page()

    try:
        logger.info(f"抓取: {name}")

        working_url = None
        all_links = []
        visited_urls = set()
        szdw_found = False  # 是否找到了师资专属页面

        for url in urls:
            if url in visited_urls: continue
            visited_urls.add(url)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)
                logger.info(f"  → 可访问: {url}")

                raw = await collect_all_links(page)
                logger.info(f"  → {url}: {len(raw)} 个链接")

                # 检查当前页面是否本身就是师资页面（URL含szdw/szll/jzyg等关键词）
                is_faculty_page = any(kw in url.lower() for kw in ["szdw", "szll", "jzyg", "jsxx", "faculty", "teacher", "staff"])

                for l in raw:
                    if l["href"] not in {x["href"] for x in all_links}:
                        all_links.append(l)

                if is_faculty_page:
                    szdw_found = True
                    working_url = url
                elif not szdw_found:
                    # 在首页找师资页面链接并跟随
                    faculty_links = [
                        l for l in raw
                        if any(kw in l.get("text","").lower() or kw in l.get("href","").lower()
                               for kw in ["师资", "教师", "faculty", "szdw", "szll", "jzyg", "staff", "teacher"])
                        and l["href"] not in visited_urls
                    ]
                    for fl in faculty_links[:3]:
                        fl_href = fl["href"]
                        if fl_href in visited_urls: continue
                        visited_urls.add(fl_href)
                        try:
                            await page.goto(fl_href, wait_until="domcontentloaded", timeout=20000)
                            await asyncio.sleep(2)
                            sub_raw = await collect_all_links(page)
                            logger.info(f"  → 师资子页 {fl['text'][:20]}: {len(sub_raw)} 链接")
                            for l in sub_raw:
                                if l["href"] not in {x["href"] for x in all_links}:
                                    all_links.append(l)
                            szdw_found = True
                            working_url = fl_href
                        except Exception as e:
                            logger.warning(f"  → 师资子页不可访问: {str(e)[:50]}")

            except Exception as e:
                logger.warning(f"  ✗ {url}: 不可用 ({str(e)[:50]})")

        if not working_url:
            logger.warning(f"  ✗ {name}: 所有URL均不可用，尝试从首页探测")
            tried = set()
            for guess_url in [f"https://{d}.nju.edu.cn" for d in _guess_subdomain(name)]:
                if guess_url in tried: continue
                tried.add(guess_url)
                try:
                    await page.goto(guess_url, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(1.5)
                    title = await page.evaluate("() => document.title")
                    if title and len(title) > 0:
                        logger.info(f"  → 探测成功: {guess_url} (title={title[:40]})")
                        faculty_url = await find_faculty_url(page, guess_url)
                        if faculty_url:
                            logger.info(f"  → 师资页面: {faculty_url}")
                            await page.goto(faculty_url, wait_until="domcontentloaded", timeout=20000)
                            await asyncio.sleep(1.5)
                            raw = await collect_all_links(page)
                            for l in raw:
                                if l["href"] not in {x["href"] for x in all_links}:
                                    all_links.append(l)
                            break
                except: pass

            if not all_links:
                logger.warning(f"  ✗ {name}: 无法找到师资页面，跳过")
                return results

        # 过滤教师链接并访问详情页
        results = await filter_teacher_links(page, all_links, name)

        n_teachers = len(results)
        n_emails = sum(1 for r in results if r["email"])
        if n_teachers:
            logger.info(f"  ✅ {name}: {n_teachers} 人, {n_emails} 邮箱 ({n_emails/n_teachers*100:.1f}%)")
        else:
            logger.info(f"  ⚠️ {name}: 0 人")

    except Exception as e:
        logger.error(f"  ❌ {name}: 出错 {e}")
    finally:
        await page.close()

    return results

def _guess_subdomain(name):
    """猜测学院可能的子域名。"""
    mapping = {
        "大学外语部": ["dafls"],
        "外国语学院": ["sfs", "wgy"],
        "人工智能学院": ["ai"],
        "环境学院": ["hjxy", "environment"],
        "化学化工学院": ["chem"],
        "历史学院": ["history"],
        "现代工程与应用科学学院": ["eng"],
        "电子科学与工程学院": ["ese"],
        "体育部": ["sports", "tyb"],
        "地球科学与工程学院": ["es"],
        "生物医学工程学院": ["bme"],
        "社会学院": ["sociology"],
        "国际关系学院": ["sis"],
        "机器人与自动化学院": ["ra"],
        "南京赫尔辛基大气与地球系统科学学院": ["nh"],
    }
    return mapping.get(name, [])

async def main():
    import uuid
    from playwright.async_api import async_playwright

    task_id = f"nju_supplement_{uuid.uuid4().hex[:8]}"
    task_dir = OUTPUT_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    # 加载进度
    all_results = []
    completed = set()
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                prog = json.load(f)
            completed = set(prog.get("completed", []))
            all_results = prog.get("all_results", [])
            logger.info(f"📌 加载进度: 已完成 {len(completed)}/{len(TARGET_DEPTS)} 学院")
        except: pass

    pending = [d for d in TARGET_DEPTS if d["name"] not in completed]
    logger.info(f"📌 共 {len(TARGET_DEPTS)} 个学院, 待处理 {len(pending)} 个")

    if not pending:
        logger.info("全部完成!")
        return _finalize(all_results, task_dir)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # 分批处理（每批 3 个）
        batch_size = 3
        for batch_start in range(0, len(pending), batch_size):
            batch = pending[batch_start:batch_start + batch_size]
            logger.info(f"\n{'='*50}\n批次 {batch_start//batch_size + 1}/{(len(pending)-1)//batch_size + 1}")

            contexts = []
            tasks = []
            for dept in batch:
                ctx = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
                )
                contexts.append(ctx)
                tasks.append(scrape_dept(ctx, dept))

            batch_results = await asyncio.gather(*tasks)

            for dept, dept_results in zip(batch, batch_results):
                all_results.extend(dept_results)
                completed.add(dept["name"])

            # 关闭所有 context
            for ctx in contexts:
                try: await ctx.close()
                except: pass

            # 保存进度
            with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                json.dump({"completed": list(completed), "all_results": all_results}, f, ensure_ascii=False, indent=2)

            logger.info(f"累计: {len(all_results)} 条记录, 完成 {len(completed)}/{len(TARGET_DEPTS)} 学院")
            await asyncio.sleep(2)

        await browser.close()

    # 最终保存
    logger.info(f"\n{'='*50}")
    logger.info(f"✅ 全部完成!")
    _finalize(all_results, task_dir)

    PROGRESS_FILE.unlink(missing_ok=True)


def _finalize(all_results, task_dir):
    """去重并保存结果。"""
    if not all_results:
        logger.info("无新数据")
        return

    # 去重
    seen = set()
    deduped = []
    for r in all_results:
        key = (r["name"], r["email"], r["department"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    # 统计
    dept_stats = defaultdict(lambda: {"total": 0, "email": 0})
    for r in deduped:
        d = r["department"]
        dept_stats[d]["total"] += 1
        if r["email"]: dept_stats[d]["email"] += 1

    logger.info(f"\n📊 补充爬取结果统计:")
    logger.info(f"总记录: {len(deduped)}, 有邮箱: {sum(1 for r in deduped if r['email'])}")
    logger.info(f"{'学院':<30} {'人数':>6} {'邮箱':>6} {'邮箱率':>8}")
    logger.info("-"*50)
    for d, s in sorted(dept_stats.items(), key=lambda x: -x[1]["total"]):
        rate = s["email"]/s["total"]*100 if s["total"]>0 else 0
        logger.info(f"{d:<30} {s['total']:>6} {s['email']:>6} {rate:>7.1f}%")

    # 保存 CSV
    csv_path = task_dir / "南京大学_补充爬取_V1.0.0.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["序号", "姓名", "邮箱", "学院", "职称", "主页链接"])
        for i, r in enumerate(deduped, 1):
            writer.writerow([i, r["name"], r["email"], r["department"], r["title"], r["url"]])

    logger.info(f"💾 CSV 已保存: {csv_path}")

    # 保存 XLSX
    try:
        sys.path.insert(0, str(BASE_DIR))
        from agent.exporter import export_xlsx
        xlsx_path = export_xlsx(deduped, f"南京大学_补充爬取_V1.0.0")
        # 复制到 task_dir
        import shutil
        shutil.copy(xlsx_path, task_dir / xlsx_path.name)
        logger.info(f"💾 XLSX 已保存: {task_dir / xlsx_path.name}")
    except Exception as e:
        logger.warning(f"XLSX 导出失败: {e}")

    return csv_path


if __name__ == "__main__":
    asyncio.run(main())
