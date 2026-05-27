"""Playwright Agent — 内置浏览器深层爬取引擎。

多级爬取策略：
  首页 → 师资队伍入口 → 学院列表 → 教师列表 → 教师个人详情页 → 提取邮箱

不依赖任何外部 LLM API key，自包含运行。
"""

import asyncio
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 600
PAGE_TIMEOUT = 30000  # 单页加载超时(ms)
PROFILE_TIMEOUT = 15000  # 详情页加载超时(ms)
MAX_TEACHERS_PER_DEPT = 30  # 每个学院最多处理的教师数
MAX_DEPTS = 15  # 最多处理的学院数

# 高校 URL 映射
UNIVERSITY_URLS: dict[str, str] = {
    "南京大学": "https://www.nju.edu.cn",
    "南京邮电大学": "https://www.njupt.edu.cn",
    "北京大学": "https://www.pku.edu.cn",
    "清华大学": "https://www.tsinghua.edu.cn",
    "复旦大学": "https://www.fudan.edu.cn",
    "浙江大学": "https://www.zju.edu.cn",
    "上海交通大学": "https://www.sjtu.edu.cn",
    "中国科学技术大学": "https://www.ustc.edu.cn",
    "武汉大学": "https://www.whu.edu.cn",
    "华中科技大学": "https://www.hust.edu.cn",
    "中山大学": "https://www.sysu.edu.cn",
    "西安交通大学": "https://www.xjtu.edu.cn",
    "哈尔滨工业大学": "https://www.hit.edu.cn",
    "同济大学": "https://www.tongji.edu.cn",
    "东南大学": "https://www.seu.edu.cn",
    "北京航空航天大学": "https://www.buaa.edu.cn",
    "北京理工大学": "https://www.bit.edu.cn",
    "中国农业大学": "https://www.cau.edu.cn",
    "北京师范大学": "https://www.bnu.edu.cn",
    "南开大学": "https://www.nankai.edu.cn",
    "天津大学": "https://www.tju.edu.cn",
    "大连理工大学": "https://www.dlut.edu.cn",
    "吉林大学": "https://www.jlu.edu.cn",
    "厦门大学": "https://www.xmu.edu.cn",
    "山东大学": "https://www.sdu.edu.cn",
    "中国海洋大学": "https://www.ouc.edu.cn",
    "湖南大学": "https://www.hnu.edu.cn",
    "中南大学": "https://www.csu.edu.cn",
    "华南理工大学": "https://www.scut.edu.cn",
    "四川大学": "https://www.scu.edu.cn",
    "重庆大学": "https://www.cqu.edu.cn",
    "电子科技大学": "https://www.uestc.edu.cn",
    "西安电子科技大学": "https://www.xidian.edu.cn",
    "西北工业大学": "https://www.nwpu.edu.cn",
    "兰州大学": "https://www.lzu.edu.cn",
    "国防科技大学": "https://www.nudt.edu.cn",
    "北京邮电大学": "https://www.bupt.edu.cn",
}

# 导航链接关键词 — 匹配到说明是导航而非教师条目
NAV_KEYWORDS = [
    "概况", "简介", "新闻", "通知", "公告", "招生", "培养", "就业",
    "学位", "学科", "科研", "学术", "党建", "工会", "校友", "捐赠",
    "图书馆", "校园", "地图", "网站", "登录", "邮箱", "联系我们",
    "欢迎", "首页", "返回", "更多", "详情", "查看", "下载",
    "introduction", "about", "news", "contact", "home",
    "copyright", "版权所有",
]

# 学院级公共邮箱特征 — 匹配到说明不是个人邮箱
ADMIN_EMAIL_PATTERNS = [
    r"^webmaster@", r"^admin@", r"^office@", r"^info@",
    r"^master@", r"^root@", r"^postmaster@",
]


class PlaywrightAgent:
    """基于 Playwright 的多级深层爬取 Agent。

    爬取层次：
    1. 大学首页 → 找到「师资队伍」入口
    2. 师资队伍页 → 找到各学院链接
    3. 学院教师列表页 → 找到每位教师的个人详情页链接
    4. 教师详情页 → 提取姓名、邮箱、职称

    task_id 用于任务隔离：输出文件写入 outputs/{task_id}/ 子目录。
    """

    def __init__(self):
        self._base_output_dir = Path(__file__).parent.parent / "outputs"
        self._nav_text_cache: set[str] = set()  # 缓存已识别的导航文字

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _extract_university(self, message: str) -> tuple[str, str | None]:
        """从用户消息中提取大学名称和对应 URL。

        策略：
        1. 精确匹配已知映射表
        2. 正则提取大学名称 + URL 模式推断
        3. 仍无法匹配时返回名称但 URL 为 None，由搜索引擎回退处理
        """
        # 策略1：精确匹配（按名称长度降序，避免"南京大学"子串误匹配"南京邮电大学"）
        for name, url in sorted(UNIVERSITY_URLS.items(), key=lambda x: -len(x[0])):
            if name in message:
                return name, url

        # 策略2：正则提取「XX大学」「XX学院」并尝试 URL 推断
        uni_match = re.search(r"([一-鿿]{2,4}(?:大学|学院|师范大学|科技大学|理工大学))", message)
        if uni_match:
            name = uni_match.group(1)
            inferred_url = self._infer_university_url(name)
            return name, inferred_url

        return None, None

    # —————————————————————— 邮箱提取 ——————————————————————

    def _extract_emails(self, text: str) -> list[str]:
        """从文本中提取邮箱地址。"""
        pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        emails = list(set(re.findall(pattern, text)))
        return emails

    def _parse_at_sign(self, text: str) -> str:
        """恢复反爬邮箱（如 xxx[at]xxx.com → xxx@xxx.com）。"""
        text = re.sub(r"\s*\[at\]\s*", "@", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*\(at\)\s*", "@", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*#@\s*", "@", text)
        text = re.sub(r"\s*\[@\]\s*", "@", text)
        text = re.sub(r"\s*\(@\)\s*", "@", text)
        return text

    def _is_valid_email(self, email: str) -> bool:
        """校验邮箱格式。"""
        return bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email))

    def _is_admin_email(self, email: str) -> bool:
        """检测是否为学院公共邮箱。"""
        email_lower = email.lower()
        for pattern in ADMIN_EMAIL_PATTERNS:
            if re.match(pattern, email_lower):
                return True
        # 常见行政邮箱前缀
        admin_prefixes = ["wxyxz", "xwcb", "bgs", "dangzheng", "office", "yuanban"]
        for prefix in admin_prefixes:
            if email_lower.startswith(prefix + "@"):
                return True
        return False

    # —————————————————————— 导航检测 ——————————————————————

    def _is_nav_text(self, text: str) -> bool:
        """检测文本是否为导航链接而非教师姓名。"""
        text = text.strip()
        if len(text) < 2 or len(text) > 10:
            return True
        # 纯英文且很短
        if re.match(r"^[A-Za-z\s]{1,15}$", text):
            return True
        # 含导航关键词
        for kw in NAV_KEYWORDS:
            if kw in text:
                return True
        # 以标点结尾（如"师资队"是被截断的"师资队伍"）
        # 全中文2-4字且是常见姓名格式 → 不拦截
        # 这里主要拦截常见导航文字
        nav_fragments = ["师资", "教师", "教授", "行政", "管理", "教职", "荣休", "访问",
                         "博士", "硕士", "本科", "研究", "学术", "系科", "教研", "诚聘"]
        for nf in nav_fragments:
            if text == nf or text.startswith(nf) and len(text) <= 3:
                return True
        return False

    def _is_teacher_name(self, text: str) -> bool:
        """检测文本是否为合理的教师姓名。"""
        text = text.strip()
        # 中文姓名：2-4个汉字
        if re.match(r"^[一-鿿]{2,4}$", text):
            return not self._is_nav_text(text)
        return False

    # —————————————————————— 核心爬取逻辑 ——————————————————————

    async def execute(self, message: str, task_id: str = "") -> AsyncGenerator[dict, None]:
        """执行浏览器抓取任务。task_id 用于任务隔离。"""
        from playwright.async_api import async_playwright

        uni_name, uni_url = self._extract_university(message)

        yield {
            "type": "log",
            "message": "🚀 启动多级深层爬取引擎...",
            "timestamp": self._timestamp(),
        }

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            )
            page = await context.new_page()

            try:
                if not uni_name or not uni_url:
                    yield {
                        "type": "log",
                        "message": f"⚠️ 未能识别「{uni_name or '未知大学'}」的官网 URL，尝试搜索引擎查找...",
                        "timestamp": self._timestamp(),
                    }
                    if uni_name:
                        search_url = f"https://www.google.com/search?q={uni_name}+官方网站"
                        yield {
                            "type": "log",
                            "message": f"请在浏览器中搜索: {search_url}",
                            "timestamp": self._timestamp(),
                        }
                    yield {"type": "done", "message": "任务结束：请手动指定大学官网 URL 后重试", "timestamp": self._timestamp()}
                    return

                # ——— 第1层：大学首页 ———
                yield {
                    "type": "log",
                    "message": f"📌 第1层：打开 {uni_name} 官网 {uni_url}",
                    "timestamp": self._timestamp(),
                }
                await page.goto(uni_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                await asyncio.sleep(2)

                # ——— 第2层：找师资队伍入口 ———
                faculty_url = await self._find_faculty_entry(page, uni_url)
                if not faculty_url:
                    yield {
                        "type": "log",
                        "message": "⚠️ 未找到师资队伍入口，尝试从首页直接提取...",
                        "timestamp": self._timestamp(),
                    }
                else:
                    yield {
                        "type": "log",
                        "message": f"📌 第2层：进入师资队伍页面 {faculty_url}",
                        "timestamp": self._timestamp(),
                    }
                    await page.goto(faculty_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                    await asyncio.sleep(2)

                # ——— 第3层：找各学院/系所链接 ———
                dept_links = await self._find_department_links(page, uni_url)
                yield {
                    "type": "log",
                    "message": f"📌 第3层：发现 {len(dept_links)} 个学院/系所链接",
                    "timestamp": self._timestamp(),
                }

                if not dept_links:
                    # 如果找不到学院链接，尝试直接在当前页面找教师列表
                    yield {
                        "type": "log",
                        "message": "未找到学院链接，尝试直接查找教师列表...",
                        "timestamp": self._timestamp(),
                    }
                    all_teachers = await self._scrape_teacher_list(page, "全部", uni_url, uni_name)
                else:
                    # ——— 第4层：遍历学院教师列表 + 详情页 ———
                    all_teachers = []
                    dept_count = 0

                    for dept_name, dept_url in dept_links[:MAX_DEPTS]:
                        dept_count += 1
                        yield {
                            "type": "log",
                            "message": f"📌 第4层 [{dept_count}/{min(len(dept_links), MAX_DEPTS)}]：进入 {dept_name} → {dept_url}",
                            "timestamp": self._timestamp(),
                        }

                        try:
                            await page.goto(dept_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                            await asyncio.sleep(2)

                            # 在当前学院页面上找到教师列表入口
                            teacher_list_url = await self._find_teacher_list_link(page, dept_url)
                            if teacher_list_url and teacher_list_url != dept_url:
                                await page.goto(teacher_list_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                                await asyncio.sleep(2)

                            teachers = await self._scrape_teacher_list(page, dept_name, uni_url, uni_name)
                            all_teachers.extend(teachers)

                            yield {
                                "type": "log",
                                "message": f"  ✅ {dept_name}：提取到 {len(teachers)} 位教师邮箱",
                                "timestamp": self._timestamp(),
                            }
                        except Exception as e:
                            yield {
                                "type": "log",
                                "message": f"  ❌ {dept_name} 处理失败: {str(e)[:100]}",
                                "timestamp": self._timestamp(),
                            }

                    # 去重（按邮箱）
                    seen = set()
                    unique = []
                    for t in all_teachers:
                        if t["email"] and t["email"] not in seen:
                            seen.add(t["email"])
                            unique.append(t)
                    all_teachers = unique

                # ——— 导出 ———
                yield {
                    "type": "log",
                    "message": f"🎉 爬取完成！共 {len(all_teachers)} 位教师（去重后）",
                    "timestamp": self._timestamp(),
                }

                if all_teachers:
                    # 显示摘要
                    summary = ", ".join(
                        f"{t['name']}<{t['email']}>" for t in all_teachers[:10]
                    )
                    yield {
                        "type": "log",
                        "message": f"前10条: {summary}",
                        "timestamp": self._timestamp(),
                    }

                    files = self._export_files(all_teachers, uni_name, task_id)
                    if files.get("csv"):
                        yield {
                            "type": "download",
                            "message": "CSV 文件已生成",
                            "filename": files["csv"],
                            "url": f"/api/download/{task_id}/{files['csv']}" if task_id else f"/api/download/{files['csv']}",
                            "timestamp": self._timestamp(),
                        }
                    if files.get("xlsx"):
                        yield {
                            "type": "download",
                            "message": "XLSX 文件已生成",
                            "filename": files["xlsx"],
                            "url": f"/api/download/{task_id}/{files['xlsx']}" if task_id else f"/api/download/{files['xlsx']}",
                            "timestamp": self._timestamp(),
                        }
                else:
                    yield {
                        "type": "log",
                        "message": "⚠️ 未能提取到任何教师邮箱",
                        "timestamp": self._timestamp(),
                    }

            except Exception as e:
                logger.error(f"浏览器操作异常: {e}")
                yield {
                    "type": "error",
                    "message": f"浏览器操作异常: {str(e)[:200]}",
                    "timestamp": self._timestamp(),
                }
            finally:
                await context.close()
                await browser.close()

        yield {
            "type": "log",
            "message": "浏览器已关闭",
            "timestamp": self._timestamp(),
        }
        yield {
            "type": "done",
            "message": "任务执行完毕",
            "timestamp": self._timestamp(),
        }

    # —————————————————————— 页面元素查找 ——————————————————————

    async def _find_faculty_entry(self, page, base_url: str) -> str | None:
        """在首页中查找师资队伍入口链接。"""
        links = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                const href = (a.href || '').toLowerCase();
                if (text.includes('师资') || text.includes('教师') ||
                    text.includes('faculty') || text.includes('staff') ||
                    href.includes('szdw') || href.includes('jsxx') ||
                    href.includes('faculty') || href.includes('teacher') ||
                    href.includes('jzyg') || href.includes('szll')) {
                    results.push({text: text, href: a.href});
                }
            });
            return results;
        }""")

        if links:
            return links[0]["href"]
        return None

    async def _find_department_links(self, page, base_url: str) -> list[tuple[str, str]]:
        """在师资队伍页面中查找各学院链接。"""
        links = await page.evaluate("""() => {
            const results = [];
            const seen = new Set();

            // 策略1：查找包含"学院"/"系"的链接
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                const href = a.href;
                if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;
                if (seen.has(href)) return;

                if ((text.includes('学院') || text.includes('系') || text.includes('研究院') ||
                     text.includes('中心')) &&
                    text.length >= 4 && text.length <= 20 &&
                    !text.includes('通知') && !text.includes('新闻') && !text.includes('概况')) {
                    seen.add(href);
                    results.push({text: text, href: href});
                }
            });

            // 策略2：如果在主内容区找到表格，提取表格中的学院链接
            if (results.length === 0) {
                const tables = document.querySelectorAll('table');
                tables.forEach(table => {
                    table.querySelectorAll('a').forEach(a => {
                        const text = a.textContent.trim();
                        const href = a.href;
                        if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;
                        if (seen.has(href)) return;
                        if (text.length >= 4 && text.length <= 20) {
                            seen.add(href);
                            results.push({text: text, href: href});
                        }
                    });
                });
            }

            return results;
        }""")

        return [(l["text"], l["href"]) for l in links]

    async def _find_teacher_list_link(self, page, base_url: str) -> str | None:
        """在学院页面中查找教师列表入口。"""
        links = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                const href = (a.href || '').toLowerCase();
                if (text.includes('教师') || text.includes('师资') ||
                    text.includes('教授') || text.includes('讲师') ||
                    text.includes('faculty') || text.includes('staff') ||
                    href.includes('teacher') || href.includes('faculty') ||
                    href.includes('js') || href.includes('sz')) {
                    results.push({text: text, href: a.href});
                }
            });
            return results;
        }""")

        if links:
            return links[0]["href"]
        return None

    # —————————————————————— 教师列表爬取 ——————————————————————

    async def _scrape_teacher_list(
        self, page, dept_name: str, base_url: str, uni_name: str
    ) -> list[dict]:
        """在教师列表页中提取教师条目，并逐个访问详情页提取邮箱。"""
        # 先获取教师条目（姓名 + 详情页链接）
        teacher_entries = await page.evaluate("""() => {
            const entries = [];
            const seen = new Set();

            // 策略1：在表格中查找
            const tables = document.querySelectorAll('table');
            tables.forEach(table => {
                const rows = table.querySelectorAll('tr');
                rows.forEach(row => {
                    const links = row.querySelectorAll('a');
                    const cells = row.querySelectorAll('td, th');
                    links.forEach(a => {
                        const text = a.textContent.trim();
                        const href = a.href;
                        if (!href || seen.has(href)) return;
                        // 中文姓名：2-4个汉字
                        if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text)) {
                            seen.add(href);
                            entries.push({
                                name: text,
                                url: href,
                                // 尝试从同行单元格获取职称
                                title: cells.length > 1 ? cells[1].textContent.trim() : ''
                            });
                        }
                    });
                });
            });

            // 策略2：在列表中查找（ul/div 结构）
            if (entries.length === 0) {
                const containers = document.querySelectorAll('ul, div.list, div.teacher-list, div.faculty-list');
                containers.forEach(container => {
                    const items = container.querySelectorAll('li, div.item, div.card, div.entry');
                    items.forEach(item => {
                        const a = item.querySelector('a');
                        if (!a) return;
                        const text = a.textContent.trim();
                        const href = a.href;
                        if (!href || seen.has(href)) return;
                        if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text)) {
                            seen.add(href);
                            entries.push({
                                name: text,
                                url: href,
                                title: ''
                            });
                        }
                    });
                });
            }

            // 策略3：查找所有可能是教师姓名的链接
            if (entries.length === 0) {
                document.querySelectorAll('a').forEach(a => {
                    const text = a.textContent.trim();
                    const href = a.href;
                    if (!href || seen.has(href)) return;
                    if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text) &&
                        !text.includes('学院') && !text.includes('大学') &&
                        !text.includes('概况') && !text.includes('新闻') &&
                        !text.includes('通知') && !text.includes('公告')) {
                        seen.add(href);
                        entries.push({name: text, url: href, title: ''});
                    }
                });
            }

            return entries.slice(0, 50);  // 每个学院最多50人
        }""")

        # 逐个访问教师详情页提取邮箱
        results = []
        for i, entry in enumerate(teacher_entries[:MAX_TEACHERS_PER_DEPT]):
            name = entry["name"]
            profile_url = entry["url"]
            list_title = entry.get("title", "")

            try:
                # 另开一个 page 加载详情页
                ctx = page.context
                profile_page = await ctx.new_page()
                try:
                    await profile_page.goto(profile_url, wait_until="domcontentloaded", timeout=PROFILE_TIMEOUT)
                    await asyncio.sleep(1)

                    # 获取详情页文本
                    profile_text = await profile_page.evaluate("() => document.body.innerText")
                    profile_text = self._parse_at_sign(profile_text)

                    # 提取邮箱
                    emails = self._extract_emails(profile_text)
                    valid_emails = [
                        e for e in emails
                        if self._is_valid_email(e) and not self._is_admin_email(e)
                    ]

                    if valid_emails:
                        # 尝试从详情页获取更准确的职称
                        title = self._extract_title_from_profile(profile_text) or list_title

                        results.append({
                            "name": name,
                            "email": valid_emails[0],  # 取第一个个人邮箱
                            "department": dept_name,
                            "title": title,
                            "url": profile_url,
                        })
                finally:
                    await profile_page.close()
            except Exception as e:
                logger.debug(f"详情页加载失败 {name}: {e}")

        return results

    def _extract_title_from_profile(self, text: str) -> str:
        """从教师详情页文本中提取职称。"""
        title_keywords = ["教授", "副教授", "助理教授", "讲师", "研究员", "副研究员",
                          "助理研究员", "工程师", "高级工程师", "院士", "博导", "硕导",
                          "长江学者", "杰青", "优青", "千人计划"]
        for title in title_keywords:
            if title in text:
                return title
        return ""

    # —————————————————————— 文件导出 ——————————————————————

    def _export_files(self, records: list[dict], uni_name: str | None, task_id: str = "") -> dict:
        from agent.exporter import export_all
        from agent.cleaner import clean_records

        cleaned = clean_records(records)
        logger.info(f"导出前清洗: {len(records)} → {len(cleaned)} 条")

        data = []
        for r in cleaned:
            data.append({
                "name": r.get("name", ""),
                "email": r.get("email", ""),
                "department": r.get("department", ""),
                "title": r.get("title", ""),
                "url": r.get("url", ""),
            })
        return export_all(data, uni_name or "unknown", task_id)

    def _infer_university_url(self, name: str) -> str | None:
        """根据大学名称推断官网 URL。

        常见模式：
        - www.{拼音缩写}.edu.cn  （如 pku.edu.cn, nju.edu.cn）
        - www.{全拼}.edu.cn      （如 tsinghua.edu.cn）
        """
        import re as _re

        # 提取拼音首字母缩写进行二次推断
        # 常见大学名→缩写映射
        common_abbr: dict[str, str] = {
            "深圳大学": "szu",
            "郑州大学": "zzu",
            "南昌大学": "ncu",
            "福州大学": "fzu",
            "云南大学": "ynu",
            "广西大学": "gxu",
            "贵州大学": "gzu",
            "山西大学": "sxu",
            "河南大学": "henu",
            "河北大学": "hbu",
            "安徽大学": "ahu",
            "江苏大学": "ujs",
            "浙江工业大学": "zjut",
            "南京工业大学": "njtech",
            "广东工业大学": "gdut",
            "上海大学": "shu",
            "北京工业大学": "bjut",
            "杭州电子科技大学": "hdu",
            "重庆邮电大学": "cqupt",
            "南京理工大学": "njust",
            "南京航空航天大学": "nuaa",
        }

        # 去除「省/自治区」等前缀
        clean = _re.sub(r"^(江苏|浙江|广东|山东|河南|河北|湖南|湖北|福建|安徽|江西|四川)", "", name)
        abbr = common_abbr.get(name) or common_abbr.get(clean)

        if abbr:
            return f"https://www.{abbr}.edu.cn"

        # 生成常见变体尝试
        # 提取首字母（取前2-4个字的拼音首字母）
        short = clean.replace("大学", "").replace("学院", "")
        if 2 <= len(short) <= 4:
            # 无法可靠推断时返回 None，让搜索引擎回退处理
            pass

        return None
