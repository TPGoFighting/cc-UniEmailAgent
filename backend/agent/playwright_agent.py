"""Playwright Agent — 内置浏览器深层爬取引擎。

多级爬取策略：
  首页 → 师资队伍入口 → 学院列表 → 教师列表 → 教师个人详情页 → 提取邮箱

不依赖任何外部 LLM API key，自包含运行。
"""

import asyncio
import json
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator
from urllib.parse import urljoin

from constants import EMAIL_RE
from agent.proxy_manager import get_proxy_manager, BaseProxyManager

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 600
PAGE_TIMEOUT = 30000  # 单页加载超时(ms)
PROFILE_TIMEOUT = 30000  # 详情页加载超时(ms)

# 从 data/university_urls.json 加载高校 URL 映射
_DATA_DIR = Path(__file__).parent.parent / "data"
_UNIVERSITY_URLS_FILE = _DATA_DIR / "university_urls.json"
def _load_university_urls() -> dict[str, str]:
    try:
        if _UNIVERSITY_URLS_FILE.exists():
            with open(_UNIVERSITY_URLS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"加载高校 URL 映射文件失败: {e}")
    return {}
UNIVERSITY_URLS = _load_university_urls()

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

    def __init__(self, max_teachers_per_dept: int = 999999, max_depts: int = 999999):
        self._base_output_dir = Path(__file__).parent.parent / "outputs"
        self._nav_text_cache: set[str] = set()  # 缓存已识别的导航文字
        self._browser = None  # Playwright browser 实例，供 stop_task 关闭
        self._context = None  # Browser context 实例
        self._stopped = False  # 标记是否已被手动停止
        self._profile_sem = asyncio.Semaphore(2)  # 详情页并发爬取限制（降低内存占用）
        self._max_teachers_per_dept = max_teachers_per_dept  # 每学院最大教师数
        self._max_depts = max_depts  # 最大学院数
        self._proxy_manager: BaseProxyManager | None = None  # 代理管理器，execute() 中初始化

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def stop_task(self, task_id: str = "") -> bool:
        """终止正在运行的浏览器进程。"""
        self._stopped = True
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        logger.info("PlaywrightAgent: 浏览器已关闭（手动终止）")
        return True

    # —————————————————————— 代理管理 ——————————————————————

    async def _make_context(self, browser):
        """创建带代理配置的 browser context 和 page。

        根据 self._proxy_manager 的配置自动注入代理参数。
        返回 (context, page) 元组。
        """
        kwargs: dict = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
        }
        if self._proxy_manager:
            proxy_config = self._proxy_manager.get_proxy_config()
            if proxy_config:
                kwargs["proxy"] = proxy_config
                logger.info(f"使用代理: {self._proxy_manager.name}")

        context = await browser.new_context(**kwargs)
        page = await context.new_page()
        return context, page

    async def _navigate_safe(self, page, url: str, wait_until: str = "domcontentloaded", timeout: int = PAGE_TIMEOUT):
        """安全导航 — 检测到封锁时自动切换代理区域并重试。

        使用 self._browser 和 self._context 进行 context 重建。
        返回 (page, switched) 元组：
          - page: 导航后的 page（可能来自新 context）
          - switched: 是否触发了代理切换
        """
        response = await page.goto(url, wait_until=wait_until, timeout=timeout)

        if response and self._proxy_manager and self._proxy_manager.matches(response.status):
            old_name = self._proxy_manager.name
            self._proxy_manager.rotate_zone()
            logger.warning(
                f"检测到 HTTP {response.status} 封锁，切换代理: {old_name} → {self._proxy_manager.name}"
            )

            # 关闭旧 context
            try:
                await self._context.close()
            except Exception:
                pass

            # 用新代理配置重建 context
            self._context, page = await self._make_context(self._browser)

            # 重试导航
            await page.goto(url, wait_until=wait_until, timeout=timeout)
            return page, True

        return page, False

    def _extract_university(self, message: str) -> tuple[str, str | None]:
        """从用户消息中提取大学名称和对应 URL。

        策略：
        1. 优先从用户原始请求部分提取（跳过系统注入的上下文）
        2. 精确匹配已知映射表
        3. 正则提取大学名称 + URL 模式推断
        4. 仍无法匹配时返回名称但 URL 为 None，由搜索引擎回退处理
        """
        # 优先从用户原始请求中提取（跳过### 具体任务需求之前注入的全局技能上下文）
        user_part = message
        if "### 具体任务需求" in message:
            user_part = message.split("### 具体任务需求")[-1]

        # 策略1：精确匹配（按名称长度降序，避免"南京大学"子串误匹配"南京邮电大学"）
        for name, url in sorted(UNIVERSITY_URLS.items(), key=lambda x: -len(x[0])):
            if name in user_part:
                return name, url

        # 策略2：正则提取「XX大学」「XX学院」并尝试 URL 推断
        uni_match = re.search(r"([一-鿿]{2,4}(?:大学|学院|师范大学|科技大学|理工大学))", user_part)
        if uni_match:
            name = uni_match.group(1)
            inferred_url = self._infer_university_url(name)
            return name, inferred_url

        # 回退：从完整消息中尝试（兼容无上下文的直接调用）
        for name, url in sorted(UNIVERSITY_URLS.items(), key=lambda x: -len(x[0])):
            if name in message:
                return name, url
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

    async def _extract_emails_multi(self, page, body_text: str) -> list[str]:
        """多策略邮箱提取：body文本 + meta标签 + data属性。"""
        pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        all_emails = set(re.findall(pattern, self._parse_at_sign(body_text)))

        # 策略2: meta 标签
        try:
            meta_emails = await page.evaluate("""() => {
                const results = new Set();
                const p = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/g;
                document.querySelectorAll('meta[name="description"], meta[name="keywords"]').forEach(m => {
                    const c = m.content || '';
                    for (const match of c.matchAll(p)) results.add(match[0]);
                });
                return Array.from(results);
            }""")
            for e in meta_emails:
                all_emails.add(e)
        except Exception:
            pass

        # 策略3: data-* 属性
        try:
            data_emails = await page.evaluate("""() => {
                const results = new Set();
                const p = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/g;
                document.querySelectorAll('[data-email], [data-mail], [data-contact]').forEach(el => {
                    const val = el.dataset.email || el.dataset.mail || el.dataset.contact || '';
                    for (const match of val.matchAll(p)) results.add(match[0]);
                });
                return Array.from(results);
            }""")
            for e in data_emails:
                all_emails.add(e)
        except Exception:
            pass

        # 策略4: iframe 内容穿透
        try:
            for frame in page.frames:
                if frame == page.main_frame:
                    continue  # 跳过主框架（已提取）
                try:
                    frame_text = await frame.evaluate("() => document.body.innerText")
                    frame_text = self._parse_at_sign(frame_text)
                    frame_emails = set(re.findall(pattern, frame_text))
                    for e in frame_emails:
                        all_emails.add(e)
                except Exception:
                    pass  # 跨域 iframe 无法访问，静默跳过
        except Exception:
            pass

        return list(all_emails)

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
        return bool(EMAIL_RE.match(email))

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

    # —————————————————————— URL 详情页检测 ——————————————————————

    def is_teacher_detail_url(self, url: str) -> bool:
        """判断 URL 是否为教师详情页（而非导航/列表页）。"""
        url_lower = url.lower()

        # 导航页特征 → 直接排除
        nav_patterns = [
            r'/list\.(htm|html|shtml)$',
            r'/index\.(htm|html|shtml)$',
            r'/main\.htm$',
            r'^javascript:',
            r'^#',
            r'^mailto:',
        ]
        for pat in nav_patterns:
            if re.search(pat, url_lower):
                return False

        # 详情页特征 → 认定是详情页
        detail_patterns = [
            r'/page\.(htm|html|shtml)',          # 通用详情页
            r'/\d+/\d+/c\d+',                      # NJU 特有格式 /2025/0321/c12345/
            r'/\d{5,}/',                            # 子路径含多位数字 ID
            r'/[a-z_-]+info',                         # xxx_info 结尾
            r'/[a-z_-]+detail',                       # xxx_detail 路径
            r'/\d+\.(htm|html|shtml)$',             # /12345.htm 纯数字页
            r'[?&]id=\d+',                          # ?id=12345 参数
        ]
        for pat in detail_patterns:
            if re.search(pat, url_lower):
                return True

        return False  # 默认保守

    # —————————————————————— 导航检测 ——————————————————————

    def _is_nav_element(self, element: dict) -> bool:
        """基于 DOM 位置和 CSS 属性检测元素是否为导航链接而非教师条目。

        参数 element 至少包含:
          - tag: 元素标签名（a/li/div 等）
          - text: 元素文本内容
          - href: 链接 URL
          - parent_tags: 父级标签列表，如 ['nav', 'div', 'body']
          - font_size: CSS font-size 值（px），可省略
        """
        href = (element.get("href") or "").lower()
        parent_tags = element.get("parent_tags", [])
        font_size = element.get("font_size")

        # 1. 检查是否在 nav/aside/footer/header 内部
        nav_containers = {"nav", "aside", "footer", "header", "menubar", "navigation"}
        if any(t.lower() in nav_containers for t in parent_tags):
            return True

        # 2. 检查 href 是否指向导航页而非详情页
        nav_href_patterns = [
            "/about", "/intro", "/general", "/overview",
            "/news", "/notice", "/announcement",
            "/contact", "/links", "/map", "/index",
            "javascript:", "#",
        ]
        for pat in nav_href_patterns:
            if pat in href:
                return True

        # 3. 检查 font-size（导航栏字体通常 < 14px）
        if font_size is not None:
            try:
                fs = float(font_size)
                if fs < 14:
                    return True
            except (ValueError, TypeError):
                pass

        return False

    def _is_teacher_name(self, text: str, element: dict | None = None) -> bool:
        """检测文本是否为合理的教师姓名。"""
        text = text.strip()
        # 硬排除：导航/非教师关键词
        hard_exclude = ["信箱", "联系", "招聘", "校友", "捐赠", "图书馆", "copyright",
                        "首页", "返回", "更多", "详情", "查看", "下载"]
        for kw in hard_exclude:
            if kw in text:
                return False
        # 中文姓名：2-4个汉字
        if re.match(r"^[一-鿿]{2,4}$", text):
            if element:
                return not self._is_nav_element(element)
            return True
        # 含·的少数民族姓名：2-6个汉字加间隔号
        if re.match(r"^[一-鿿·]{2,6}$", text) and "·" in text:
            if element:
                return not self._is_nav_element(element)
            return True
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
            self._proxy_manager = get_proxy_manager()
            browser = await p.chromium.launch(headless=True)
            self._browser = browser
            context, page = await self._make_context(browser)
            self._context = context

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
                page, switched = await self._navigate_safe(page, uni_url)
                if switched:
                    yield {
                        "type": "log",
                        "message": f"检测到封锁，已切换代理区域 → {self._proxy_manager.name}",
                        "timestamp": self._timestamp(),
                    }
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
                    page, switched = await self._navigate_safe(page, faculty_url)
                    if switched:
                        yield {
                            "type": "log",
                            "message": f"检测到封锁，已切换代理区域 → {self._proxy_manager.name}",
                            "timestamp": self._timestamp(),
                        }
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
                    all_teachers, page = await self._scrape_teacher_list(page, "全部", uni_url, uni_name)
                else:
                    # ——— 第4层：遍历学院教师列表 + 详情页 ———
                    all_teachers = []
                    dept_count = 0

                    for dept_name, dept_url in dept_links:
                        if self._stopped:
                            yield {"type": "log", "message": "任务已被手动终止", "timestamp": self._timestamp()}
                            break
                        dept_count += 1
                        yield {
                            "type": "log",
                            "message": f"📌 第4层 [{dept_count}/{len(dept_links)}]：进入 {dept_name} → {dept_url}",
                            "timestamp": self._timestamp(),
                        }

                        try:
                            page, switched = await self._navigate_safe(page, dept_url)
                            if switched:
                                yield {
                                    "type": "log",
                                    "message": f"检测到封锁，已切换代理区域 → {self._proxy_manager.name}",
                                    "timestamp": self._timestamp(),
                                }
                            await asyncio.sleep(2)

                            # 在当前学院页面上找到教师列表入口
                            teacher_list_url = await self._find_teacher_list_link(page, dept_url)
                            if teacher_list_url and teacher_list_url != dept_url:
                                page, switched = await self._navigate_safe(page, teacher_list_url)
                                if switched:
                                    yield {
                                        "type": "log",
                                        "message": f"检测到封锁，已切换代理区域 → {self._proxy_manager.name}",
                                        "timestamp": self._timestamp(),
                                    }
                                await asyncio.sleep(2)

                            teachers, page = await self._scrape_teacher_list(page, dept_name, uni_url, uni_name)
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
                try:
                    if self._context:
                        await self._context.close()
                except Exception:
                    pass
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

    async def _find_pagination(self, page, base_url: str) -> list[str]:
        """检测页面分页链接，返回第2页开始的 URL 列表（已排序去重）。

        覆盖常见分页模式：
        - ?page=2 / &page=2
        - list_2.htm / list-2.html
        - /page/2/
        - ?p=2 / &p=2
        - ?offset=20
        """
        pagination_urls = await page.evaluate("""() => {
            const results = [];
            const seen = new Set();
            const pagePatterns = [
                /[?&]page=(\\d+)/i,
                /[_\\-](\\d+)\\.(htm|html|shtml|aspx|php|jsp)/i,
                /\\/page\\/(\\d+)/i,
                /[?&]p=(\\d+)/i,
                /[?&]offset=(\\d+)/i,
            ];
            document.querySelectorAll('a').forEach(a => {
                const href = a.href || '';
                if (!href || href.startsWith('javascript:') || href === '#') return;
                for (const pattern of pagePatterns) {
                    const m = href.match(pattern);
                    if (m) {
                        const num = parseInt(m[1], 10);
                        if (num >= 2 && !seen.has(href)) {
                            seen.add(href);
                            results.push({url: href, page: num});
                            break;
                        }
                    }
                }
            });
            // 按页码升序排列
            results.sort((a, b) => a.page - b.page);
            return results.map(r => r.url);
        }""")
        return pagination_urls

    # —————————————————————— 教师列表爬取 ——————————————————————

    async def _extract_teacher_entries_from_page(self, page) -> list[dict]:
        """从当前页面 JS 提取教师条目（支持分页场景复用）。"""
        return await page.evaluate("""() => {
            const entries = [];
            const seen = new Set();

            // 导航关键词（href/text 过滤）
            const hrefExclude = /webplus|login|mailto:|javascript:/i;
            const textExclude = /信箱|联系|招聘|校友|捐赠|图书馆|copyright|首页|返回|更多|详情|查看|下载|新闻|通知|公告|概况|学院|大学|系部|机构/;

            function isNavLink(a) {
                const href = (a.href || '').toLowerCase();
                const text = (a.textContent || '').trim();
                if (!href || hrefExclude.test(href)) return true;
                if (textExclude.test(text)) return true;
                // 列表页/导航页 URL 模式
                if (/\\/list\\.(htm|html|shtml)$|\\/index\\.(htm|html)$|\\/main\\.htm$/.test(href)) return true;
                return false;
            }

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
                        if (!href || seen.has(href) || isNavLink(a)) return;
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
                        if (!href || seen.has(href) || isNavLink(a)) return;
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
                    if (!href || seen.has(href) || isNavLink(a)) return;
                    if (/^[\\u4e00-\\u9fff]{2,4}$/.test(text)) {
                        seen.add(href);
                        entries.push({name: text, url: href, title: ''});
                    }
                });
            }

            return entries;  // 不限制，完整爬取
        }""")

    async def _scrape_teacher_list(
        self, page, dept_name: str, base_url: str, uni_name: str
    ):
        """在教师列表页中提取教师条目，支持分页，并逐个访问详情页提取邮箱。

        返回 (teachers: list[dict], page) 元组 — page 可能在代理切换后更新。
        """
        # 第1步：提取首页教师条目
        all_entries = await self._extract_teacher_entries_from_page(page)

        # 第2步：分页处理 — 检测并爬取后续分页（自动代理切换）
        pagination_urls = await self._find_pagination(page, base_url)
        if pagination_urls:
            logger.info(f"{dept_name}: 检测到 {len(pagination_urls)} 个分页")
            for page_url in pagination_urls:
                if self._stopped:
                    break
                try:
                    page, switched = await self._navigate_safe(page, page_url)
                    if switched:
                        logger.info(f"分页导航触发代理切换 → {self._proxy_manager.name}")
                    await asyncio.sleep(2)
                    page_entries = await self._extract_teacher_entries_from_page(page)
                    all_entries.extend(page_entries)
                    logger.info(f"  分页 {page_url}: 提取到 {len(page_entries)} 条")
                except Exception as e:
                    logger.debug(f"分页加载失败 {page_url}: {e}")
                    continue

        # 第3步：去重（按 URL 去重，保留首次出现的条目）
        seen_urls: set[str] = set()
        unique_entries = []
        for e in all_entries:
            url = e["url"]
            if url not in seen_urls:
                seen_urls.add(url)
                unique_entries.append(e)
        all_entries = unique_entries

        # 第4步：URL 白名单过滤 — 去掉明显不是详情页的条目
        filtered_entries = [
            e for e in all_entries
            if self.is_teacher_detail_url(e["url"])
        ]
        if filtered_entries:
            all_entries = filtered_entries

        # 第5步：并行访问教师详情页提取邮箱
        if self._stopped:
            return [], page
        ctx = page.context
        tasks = [self._crawl_single_profile(ctx, entry, dept_name) for entry in all_entries]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        results = [r for r in results_list if r and isinstance(r, dict)]

        # 后过滤：排除非教师职称条目
        results = self._filter_teacher_results(results)

        return results, page

    async def _crawl_single_profile(self, ctx, entry: dict, dept_name: str) -> dict | None:
        """并行爬取单个教师详情页。"""
        async with self._profile_sem:
            if self._stopped:
                return None
            name = entry["name"]
            profile_url = entry["url"]
            list_title = entry.get("title", "")
            profile_page = await ctx.new_page()
            try:
                if self._stopped:
                    return None
                response = await profile_page.goto(profile_url, wait_until="load", timeout=PROFILE_TIMEOUT)
                # 检测封锁（并行任务中不切换代理，仅跳过）
                if response and self._proxy_manager and self._proxy_manager.matches(response.status):
                    logger.debug(f"详情页封锁 HTTP {response.status}: {name} {profile_url}")
                    return None
                if self._stopped:
                    return None
                await asyncio.sleep(1)
                # 滚动到底部触发懒加载
                try:
                    if self._stopped:
                        return None
                    await profile_page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    if self._stopped:
                        return None
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
                profile_text = await profile_page.evaluate("() => document.body.innerText")
                profile_text = self._parse_at_sign(profile_text)
                emails = await self._extract_emails_multi(profile_page, profile_text)  # 多策略提取
                valid_emails = [
                    e for e in emails
                    if self._is_valid_email(e) and not self._is_admin_email(e)
                ]
                if valid_emails:
                    title = self._extract_title_from_profile(profile_text) or list_title
                    return {
                        "name": name,
                        "email": valid_emails[0],
                        "department": dept_name,
                        "title": title,
                        "url": profile_url,
                    }
            except Exception as e:
                logger.debug(f"详情页加载失败 {name}: {e}")
            finally:
                await profile_page.close()
        return None

    def _filter_teacher_results(self, results: list[dict]) -> list[dict]:
        """对爬取结果做后过滤，排除非教师职称条目。"""
        non_teacher_titles = ["书记", "主任", "院长信箱", "教务", "行政", "党政",
                             "辅导员", "秘书", "财务", "人事", "团委"]
        filtered = []
        for r in results:
            name = r.get("name", "")
            title = r.get("title", "")
            # 二次校验姓名合理性
            if not self._is_teacher_name(name):
                continue
            # 排除非教师职称
            skip = False
            for nt in non_teacher_titles:
                if nt in title:
                    skip = True
                    break
            if skip:
                continue
            filtered.append(r)
        return filtered

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
