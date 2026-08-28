"""浏览器工具 — 通过 Playwright 控制浏览器进行网页交互和抓取。

参考 PlaywrightAgent 的多级爬取策略，但以 Tool 形式暴露给 LLM 驱动。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..tool import Tool, ToolResult

logger = logging.getLogger(__name__)

# 全局 Browser 实例管理（复用浏览器，避免反复启动）
_browser_instance = None
_context_instance = None


async def _get_page():
    """获取 Playwright 页面实例（自动重连，健壮版本）。"""
    global _browser_instance, _context_instance
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError("Playwright 未安装。执行: pip install playwright && playwright install chromium")

    # 检查浏览器是否存活，异常时视为已断开
    browser_alive = False
    if _browser_instance is not None:
        try:
            browser_alive = _browser_instance.is_connected()
        except Exception:
            browser_alive = False
            logger.warning("浏览器连接检查异常，将重新创建")

    if _browser_instance is None or not browser_alive:
        # 清理旧实例
        if _browser_instance is not None:
            try:
                await _browser_instance.close()
            except Exception:
                pass
        if _context_instance is not None:
            try:
                await _context_instance.close()
            except Exception:
                pass
        
        p = await async_playwright().start()
        _browser_instance = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        _context_instance = await _browser_instance.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )

    if _context_instance:
        return await _context_instance.new_page()
    raise RuntimeError("浏览器上下文未初始化")


async def _close_page(page):
    """关闭页面。"""
    try:
        await page.close()
    except Exception:
        pass


async def cleanup_browser():
    """全局清理浏览器实例。"""
    global _browser_instance, _context_instance
    try:
        if _context_instance:
            await _context_instance.close()
    except Exception:
        pass
    try:
        if _browser_instance:
            await _browser_instance.close()
    except Exception:
        pass
    _browser_instance = None
    _context_instance = None


class BrowserNavigateTool(Tool):
    """浏览器导航 — 跳转到指定 URL，等待页面加载。"""

    name = "browser_navigate"
    description = """在浏览器中打开指定 URL，等待页面完全加载后返回页面文本内容。
适用于需要 JavaScript 渲染的单页应用、动态加载页面。
返回页面标题和可见文本内容。
"""
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "目标 URL（包含 https://）",
            },
            "wait_selector": {
                "type": "string",
                "description": "等待指定 CSS 选择器出现后再返回（可选）",
            },
            "timeout": {
                "type": "integer",
                "description": "页面加载超时（毫秒，默认 30000）",
                "default": 30000,
            },
            "extract_links": {
                "type": "boolean",
                "description": "是否提取页面中的链接（默认 false）",
                "default": False,
            },
            "max_content": {
                "type": "integer",
                "description": "页面内容最大字符数（默认 8000，最大 50000）",
                "default": 8000,
            },
        },
        "required": ["url"],
    }
    is_readonly = True

    async def call(self, input_data: dict[str, Any]) -> ToolResult:
        url = input_data["url"]
        timeout = input_data.get("timeout", 30000)
        wait_selector = input_data.get("wait_selector")
        extract_links = input_data.get("extract_links", False)
        max_content = min(input_data.get("max_content", 8000), 50000)

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        page = None
        try:
            page = await _get_page()
            await page.goto(url, wait_until="networkidle", timeout=timeout)

            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=5000)
                except Exception:
                    logger.debug(f"选择器 '{wait_selector}' 未出现，继续执行")

            title = await page.title()
            text_content = await page.evaluate("document.body?.innerText || ''")
            text_content = re.sub(r"\s+", " ", text_content).strip()

            # 截断（使用 max_content 参数）
            if len(text_content) > max_content:
                text_content = text_content[:max_content] + f"\n\n...（内容过长，已截断至 {max_content} 字符）"

            lines = [f"## 🌐 {title}", f"**URL**: {url}\n"]

            if extract_links:
                links = await page.evaluate("""() => {
                    const links = document.querySelectorAll('a[href]');
                    return Array.from(links).map(a => ({
                        text: a.innerText.trim().substring(0, 60),
                        href: a.href,
                    })).filter(l => l.href && !l.href.startsWith('javascript:'));
                }""")
                lines.append(f"**页面链接**（{len(links)} 个）:\n")
                for link in links[:30]:
                    if link["text"]:
                        lines.append(f"- [{link['text']}]({link['href']})")
                if len(links) > 30:
                    lines.append(f"- ... 及其他 {len(links) - 30} 个链接")
                lines.append("")

            lines.append(f"**页面内容**:\n{text_content[:max_content]}")

            return ToolResult(
                data="\n".join(lines),
                metadata={"title": title, "url": url, "links_count": len(lines) if extract_links else 0},
            )

        except Exception as e:
            err_msg = str(e) or type(e).__name__
            logger.warning(f"browser_navigate 失败 {url}: {err_msg}")
            return ToolResult(data=f"❌ 浏览器导航失败: {url} — {err_msg[:200]}")
        finally:
            if page:
                await _close_page(page)


class BrowserExtractTool(Tool):
    """浏览器页面分析 — 从当前页面提取结构化数据。"""

    name = "browser_extract"
    description = """从浏览器当前页面提取结构化数据，支持：
1. CSS 选择器提取（适合列表页）
2. XPath 提取
3. 邮箱正则提取
4. 完整页面分析
适用于提取教师列表、邮箱地址等结构化信息。
"""
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "目标 URL",
            },
            "extract_type": {
                "type": "string",
                "enum": ["emails", "links", "table", "text", "custom"],
                "description": "提取类型",
                "default": "emails",
            },
            "selector": {
                "type": "string",
                "description": "CSS 选择器（extract_type=custom 时使用）",
            },
            "attribute": {
                "type": "string",
                "description": "提取属性（如 href、src，默认 innerText）",
                "default": "innerText",
            },
        },
        "required": ["url"],
    }
    is_readonly = True

    async def call(self, input_data: dict[str, Any]) -> ToolResult:
        url = input_data["url"]
        extract_type = input_data.get("extract_type", "emails")
        selector = input_data.get("selector", "")
        attribute = input_data.get("attribute", "innerText")

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        page = None
        try:
            page = await _get_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)

            if extract_type == "emails":
                return await self._extract_emails(page, url)
            elif extract_type == "links":
                return await self._extract_links(page, url)
            elif extract_type == "table":
                return await self._extract_table(page, url)
            elif extract_type == "custom" and selector:
                return await self._extract_custom(page, url, selector, attribute)
            else:
                text = await page.evaluate("document.body?.innerText || ''")
                text = re.sub(r"\s+", " ", text).strip()[:5000]
                return ToolResult(data=f"📄 **{url}**\n\n{text}")

        except Exception as e:
            logger.warning(f"browser_extract 失败 {url}: {e}")
            return ToolResult(data=f"❌ 提取失败: {url} — {str(e)[:200]}")
        finally:
            if page:
                await _close_page(page)

    async def _extract_emails(self, page, url: str) -> ToolResult:
        """提取页面中的邮箱地址。"""
        html = await page.content()
        # 邮箱正则
        email_pattern = re.compile(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            re.IGNORECASE,
        )
        found = set(email_pattern.findall(html))

        # 也看可见文本
        text = await page.evaluate("document.body?.innerText || ''")
        found.update(email_pattern.findall(text))

        # 过滤公共邮箱
        admin_domains = {"admin", "info", "webmaster", "postmaster", "noreply", "support", "contact", "service"}
        emails = [e for e in sorted(found) if e.split("@")[0].lower() not in admin_domains]

        if emails:
            lines = [f"## 📧 找到 {len(emails)} 个邮箱"]
            for e in emails[:50]:
                lines.append(f"- {e}")
            if len(emails) > 50:
                lines.append(f"- ... 及其他 {len(emails) - 50} 个")
            return ToolResult(data="\n".join(lines), metadata={"emails": emails, "count": len(emails)})
        else:
            return ToolResult(data=f"在 {url} 未找到邮箱地址")

    async def _extract_links(self, page, url: str) -> ToolResult:
        """提取页面链接。"""
        links = await page.evaluate("""() => {
            const links = document.querySelectorAll('a[href]');
            return Array.from(links).map(a => ({
                text: a.innerText.trim().substring(0, 80),
                href: a.href,
            })).filter(l => l.href && !l.href.startsWith('javascript:'));
        }""")

        edu_links = [l for l in links if ".edu." in l["href"]]
        internal_links = [l for l in links if url.split("/")[2] in l["href"]]

        lines = [f"## 🔗 {url}"]
        lines.append(f"总链接数: {len(links)}")
        lines.append(f"教育网链接: {len(edu_links)}")
        lines.append(f"站内链接: {len(internal_links)}\n")

        # 按文本相关性分组
        faculty_keywords = ["教师", "师资", "教授", "导师", "队伍", "faculty", "staff", "teacher"]
        faculty_links = [
            l for l in internal_links
            if any(kw in (l["text"] + l["href"]).lower() for kw in faculty_keywords)
        ]

        if faculty_links:
            lines.append("### 🎓 师资相关链接:")
            for l in faculty_links[:15]:
                text = l["text"] or l["href"][:40]
                lines.append(f"- [{text}]({l['href']})")
            lines.append("")

        # 学院链接
        dept_keywords = ["学院", "系", "school", "department", "college", "institute"]
        dept_links = [
            l for l in internal_links
            if any(kw in (l["text"] + l["href"]).lower() for kw in dept_keywords)
        ]
        if dept_links:
            lines.append("### 🏛️ 院系链接:")
            for l in dept_links[:15]:
                text = l["text"] or l["href"][:40]
                lines.append(f"- [{text}]({l['href']})")
            lines.append("")

        # 导航链接（可能被折叠）
        nav_links = await page.evaluate("""() => {
            const nav = document.querySelector('nav, .nav, #nav, .menu, .header, #header');
            if (!nav) return [];
            const links = nav.querySelectorAll('a[href]');
            return Array.from(links).map(a => ({
                text: a.innerText.trim().substring(0, 40),
                href: a.href,
            })).filter(l => l.href && !l.href.startsWith('javascript:'));
        }""")
        if nav_links:
            lines.append("### 🧭 导航菜单:")
            for l in nav_links[:10]:
                text = l["text"] or l["href"][:30]
                lines.append(f"- [{text}]({l['href']})")

        return ToolResult(
            data="\n".join(lines),
            metadata={"total": len(links), "faculty": len(faculty_links), "dept": len(dept_links)},
        )

    async def _extract_table(self, page, url: str) -> ToolResult:
        """提取页面中的表格数据。"""
        tables = await page.evaluate("""() => {
            const tables = document.querySelectorAll('table');
            return Array.from(tables).map((table, idx) => {
                const rows = table.querySelectorAll('tr');
                const data = Array.from(rows).map(row => {
                    const cells = row.querySelectorAll('th, td');
                    return Array.from(cells).map(c => c.innerText.trim());
                });
                return { index: idx, rows: data.length, cols: data[0]?.length || 0, data: data.slice(0, 20) };
            });
        }""")

        if not tables:
            return ToolResult(data=f"在 {url} 未找到表格数据")

        lines = [f"## 📊 {url} — 找到 {len(tables)} 个表格\n"]
        for t in tables:
            lines.append(f"### 表格 {t['index'] + 1}（{t['rows']} 行 x {t['cols']} 列）")
            for row in t["data"][:10]:
                lines.append("| " + " | ".join(str(c)[:30] for c in row) + " |")

        return ToolResult(data="\n".join(lines), metadata={"table_count": len(tables)})

    async def _extract_custom(self, page, url: str, selector: str, attribute: str) -> ToolResult:
        """自定义 CSS 选择器提取。"""
        try:
            elements = await page.query_selector_all(selector)
            values = []
            for el in elements[:100]:
                if attribute == "innerText":
                    val = await el.inner_text()
                else:
                    val = await el.get_attribute(attribute) or ""
                val = val.strip()
                if val:
                    values.append(val)
            if values:
                return ToolResult(
                    data=f"## 🔍 选择器 '{selector}' 提取到 {len(values)} 个结果:\n" +
                         "\n".join(f"{i+1}. {v[:200]}" for i, v in enumerate(values[:30])),
                    metadata={"count": len(values), "selector": selector},
                )
            return ToolResult(data=f"选择器 '{selector}' 未匹配到任何元素")
        except Exception as e:
            return ToolResult(data=f"❌ 选择器提取失败: {e}")


class BrowserScreenshotTool(Tool):
    """页面截图工具 — 截取浏览器当前页面。"""

    name = "browser_screenshot"
    description = """截取指定 URL 的页面截图并保存。
适用于查看页面布局、验证爬取效果、调试反爬问题。
"""
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "目标 URL",
            },
            "output_path": {
                "type": "string",
                "description": "截图保存路径（可选，默认自动生成）",
            },
            "full_page": {
                "type": "boolean",
                "description": "是否截取整页（默认 false，只截取视口）",
                "default": False,
            },
            "width": {
                "type": "integer",
                "description": "视口宽度（默认 1280）",
                "default": 1280,
            },
            "height": {
                "type": "integer",
                "description": "视口高度（默认 800）",
                "default": 800,
            },
        },
        "required": ["url"],
    }
    is_readonly = True

    async def call(self, input_data: dict[str, Any]) -> ToolResult:
        from pathlib import Path

        url = input_data["url"]
        output_path = input_data.get("output_path", "")
        full_page = input_data.get("full_page", False)
        width = input_data.get("width", 1280)
        height = input_data.get("height", 800)

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        from agent.paths import _BASE_OUTPUT_DIR

        if not output_path:
            import uuid
            output_path = str(_BASE_OUTPUT_DIR / f"screenshot_{uuid.uuid4().hex[:8]}.png")

        page = None
        try:
            page = await _get_page()
            await page.set_viewport_size({"width": width, "height": height})
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.screenshot(path=output_path, full_page=full_page)

            return ToolResult(
                data=f"📸 截图已保存: {output_path}",
                files_created=[output_path],
            )
        except Exception as e:
            logger.warning(f"截图失败 {url}: {e}")
            return ToolResult(data=f"❌ 截图失败: {e}")
        finally:
            if page:
                await _close_page(page)
