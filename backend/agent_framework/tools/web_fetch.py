"""网页抓取工具 — 获取 URL 内容并转为 Markdown。支持重试和反爬绕过。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..tool import Tool, ToolResult

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]


class WebFetchTool(Tool):
    """获取网页内容并转为 Markdown 文本。"""

    name = "web_fetch"
    description = """获取指定 URL 的网页内容并转换为可读的 Markdown 格式。
适用于查看网页信息，如高校官网、学院介绍页等。
对于需要 JavaScript 渲染的复杂页面，请使用 browser_navigate。
"""
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "需要获取的完整 URL（包含 https://）",
            },
            "max_length": {
                "type": "integer",
                "description": "返回内容的最大字符数（默认 10000）",
                "default": 10000,
            },
        },
        "required": ["url"],
    }
    is_readonly = True

    async def call(self, input_data: dict[str, Any]) -> ToolResult:
        url = input_data["url"]
        max_length = input_data.get("max_length", 10000)

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # 重试策略：换 User-Agent
        last_error = ""
        for attempt in range(3):
            ua = _USER_AGENTS[attempt % len(_USER_AGENTS)]
            try:
                async with httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=30,
                    headers={
                        "User-Agent": ua,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                        "Accept-Encoding": "gzip, deflate",
                        "Cache-Control": "no-cache",
                        "Pragma": "no-cache",
                        "Referer": (url[:url.index("/", 8)] if url.startswith("http") and "/" in url[8:] else url),
                    },
                ) as client:
                    resp = await client.get(url)

                    # 4xx 错误不重试（除了 429 和 503）
                    if resp.status_code in (403, 404, 410):
                        return ToolResult(data=f"❌ 页面无法访问（HTTP {resp.status_code}），建议换用 browser_navigate: {url}")
                    if resp.status_code == 412:
                        if attempt < 2:
                            last_error = f"412 Precondition Failed（第 {attempt+1} 次重试）"
                            continue
                        return ToolResult(data=f"❌ 412 Precondition Failed — 服务器反爬校验拦截，请使用 browser_navigate: {url}")

                    resp.raise_for_status()
                    html = resp.text

                # 检测 Cloudflare 等反爬页面
                if "just a moment" in html[:500].lower() or "cf-browser-verification" in html[:1000]:
                    return ToolResult(
                        data=f"🛡️ Cloudflare 防护页面，无法直接抓取。请使用 browser_navigate: {url}"
                    )

                text = self._html_to_text(html)

                if not text.strip():
                    text = f"[页面 {url} 可能依赖 JavaScript 渲染，内容为空。建议使用 browser_navigate 工具]"

                if len(text) > max_length:
                    text = text[:max_length] + f"\n\n...（内容过长，已截断至 {max_length} 字符）"

                return ToolResult(
                    data=f"## 📄 {url}\n\n{text.strip()[:max_length]}",
                    metadata={"url": url, "length": len(text), "truncated": len(text) > max_length},
                )

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in (429, 503) and attempt < 2:
                    last_error = f"HTTP {status}（第 {attempt+1} 次重试）"
                    continue
                return ToolResult(data=f"❌ HTTP 错误 {status}: {url}")
            except httpx.TimeoutException:
                last_error = f"超时（第 {attempt+1} 次重试）"
                if attempt < 2:
                    continue
                return ToolResult(data=f"⏱️ 请求超时: {url}")
            except Exception as e:
                logger.warning(f"web_fetch 失败 {url}: {e}")
                last_error = str(e)[:100]
                if attempt < 2:
                    continue

        return ToolResult(data=f"❌ 获取失败: {url} — {last_error}")

    def _html_to_text(self, html: str) -> str:
        """简单 HTML → 纯文本转换。"""
        import re

        # 移除 script/style
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)

        # 替换块级标签为换行
        text = re.sub(r"</?(?:div|p|tr|li|br|h[1-6]|table|ul|ol|section|article|nav|header|footer)[^>]*>",
                      "\n", text, flags=re.IGNORECASE)

        # 替换其他标签
        text = re.sub(r"<[^>]+>", "", text)

        # 解码 HTML 实体
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&nbsp;", " ").replace("&quot;", '"')

        # 合并多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)

        return text.strip()
