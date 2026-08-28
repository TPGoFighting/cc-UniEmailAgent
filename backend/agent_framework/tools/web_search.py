"""网络搜索工具 — 通过外部搜索引擎检索信息。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..tool import Tool, ToolResult

logger = logging.getLogger(__name__)


class WebSearchTool(Tool):
    """网络搜索工具 — 搜索网页获取最新信息。"""

    name = "web_search"
    description = """搜索互联网，获取最新的网页信息。
适用于查找高校官网、学院页面链接、教师名录等公开信息。
返回搜索结果的标题、摘要和 URL 列表。
"""
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词（如 '南京大学计算机学院 师资队伍'）",
            },
            "max_results": {
                "type": "integer",
                "description": "返回结果数量（默认 5，最大 10）",
                "default": 5,
            },
        },
        "required": ["query"],
    }
    is_readonly = True

    def __init__(self):
        super().__init__()
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    async def call(self, input_data: dict[str, Any]) -> ToolResult:
        query = input_data["query"]
        max_results = min(input_data.get("max_results", 5), 10)

        # 首选：DuckDuckGo（直接可用，无需 API Key）
        results = await self._search_duckduckgo(query, max_results)

        if not results:
            # 回退：多个 SearXNG 实例
            results = await self._search_searxng(query, max_results)

        if not results:
            return ToolResult(data=f"搜索 '{query}' 未找到结果")

        lines = [f"搜索结果: {query}\n"]
        for i, r in enumerate(results[:max_results], 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   URL: {r['url']}")
            if r.get("snippet"):
                lines.append(f"   {r['snippet']}")
            lines.append("")

        return ToolResult(data="\n".join(lines), metadata={"result_count": len(results)})

    async def _search_duckduckgo(self, query: str, limit: int) -> list[dict]:
        """通过 DuckDuckGo HTML 搜索（无需 API Key，直接解析结果页）。"""
        import re

        try:
            url = "https://html.duckduckgo.com/html/"
            data = {"q": query}
            headers = {"User-Agent": self._ua, "Accept": "text/html,application/xhtml+xml"}
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.post(url, data=data, headers=headers)
                if resp.status_code != 200:
                    logger.debug(f"DuckDuckGo 返回 {resp.status_code}")
                    return []

                html = resp.text
                results = []
                seen = set()

                # 解析 DuckDuckGo 结果链接
                # 新版 DDG 使用 <a class="result__a" ...> 或普通 <a> 标签
                for m in re.finditer(
                    r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>',
                    html,
                ):
                    url = m.group(1)
                    title = re.sub(r"<[^>]+>", "", m.group(2)).strip()

                    # 过滤：跳过空标题、图标、分页等
                    if not title or len(title) < 3:
                        continue
                    if title in (" ", "", "→", "«", "»"):
                        continue

                    # 去重
                    if url in seen:
                        continue
                    seen.add(url)

                    results.append({"title": title, "url": url, "snippet": ""})
                    if len(results) >= limit * 2:  # 多取一些后排序
                        break

                # 优先放 .edu.cn 链接（高校搜索场景）
                edu_results = [r for r in results if ".edu." in r["url"]]
                other_results = [r for r in results if ".edu." not in r["url"]]
                return (edu_results + other_results)[:limit]

        except Exception as e:
            logger.debug(f"DuckDuckGo 搜索失败: {e}")
            return []

    async def _search_searxng(self, query: str, limit: int) -> list[dict]:
        """回退：尝试多个 SearXNG 实例。"""
        instances = [
            "https://searx.be/search",
            "https://search.sapti.me/search",
            "https://searx.baczek.me/search",
        ]

        for base_url in instances:
            try:
                params = {
                    "q": query,
                    "format": "json",
                    "language": "zh-CN",
                    "categories": "general",
                    "pageno": 1,
                }
                headers = {"User-Agent": self._ua}
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(base_url, params=params, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        results = []
                        for r in data.get("results", []):
                            title = r.get("title", "")
                            url = r.get("url", "")
                            if title and url:
                                results.append({
                                    "title": title,
                                    "url": url,
                                    "snippet": r.get("content", ""),
                                })
                        if results:
                            return results[:limit]
            except Exception as e:
                logger.debug(f"SearXNG {base_url} 失败: {e}")
                continue

        return []
