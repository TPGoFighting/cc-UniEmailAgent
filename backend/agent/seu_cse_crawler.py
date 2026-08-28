"""Deterministic crawler for Southeast University CSE teacher profiles."""

from __future__ import annotations

import asyncio
import html
import re
from collections.abc import Awaitable, Callable
from urllib.parse import urljoin, urlparse

import httpx

UNIVERSITY = "东南大学"
DEPARTMENT = "计算机科学与工程学院"

LIST_URLS = [
    "https://cse.seu.edu.cn/49354/list.htm",
    "https://cse.seu.edu.cn/dsxx/list.htm",
    "https://cse.seu.edu.cn/49355/list.htm",
    "https://cse.seu.edu.cn/49356/list.htm",
    "https://cse.seu.edu.cn/54820/list.htm",
    "https://cse.seu.edu.cn/49357/list.htm",
    "https://cse.seu.edu.cn/49358/list.htm",
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ANCHOR_RE = re.compile(
    r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
TITLE_OR_ANCHOR_RE = re.compile(
    r"<h2\b[^>]*>(.*?)</h2>|<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
PUBLIC_EMAIL_PREFIXES = (
    "admin",
    "webmaster",
    "office",
    "info",
    "master",
    "root",
    "postmaster",
    "support",
    "service",
    "contact",
)


def is_seu_cse_request(message: str, university_name: str = "") -> bool:
    text = f"{message or ''} {university_name or ''}"
    has_university = "东南大学" in text or "seu" in text.lower()
    has_department = any(token in text for token in ("计算机", "计科", "CSE", "cse"))
    has_teacher_intent = any(token in text for token in ("教师", "老师", "师资", "邮箱", "爬取", "抓取", "信息"))
    return has_university and has_department and has_teacher_intent


async def crawl_seu_cse_teachers(
    progress: Callable[[str], Awaitable[None]] | None = None,
) -> list[dict]:
    async def emit(message: str) -> None:
        if progress:
            await progress(message)

    await emit("正在访问东南大学计算机科学与工程学院师资入口...")
    timeout = httpx.Timeout(25.0, connect=10.0)
    headers = {"User-Agent": "Mozilla/5.0 UniEmailAgent/1.0"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        list_pages = await _fetch_list_pages(client)
        title_map = _build_title_map(list_pages.get("https://cse.seu.edu.cn/49355/list.htm", ""))
        links = _extract_teacher_links(list_pages)
        await emit(f"已发现 {len(links)} 个教师主页，开始提取邮箱...")

        semaphore = asyncio.Semaphore(12)
        done = 0

        async def fetch_one(name: str, url: str) -> dict:
            nonlocal done
            async with semaphore:
                record = await _fetch_teacher_detail(client, name, url, title_map.get(name, ""))
                done += 1
                if done % 25 == 0 or done == len(links):
                    await emit(f"已处理 {done}/{len(links)} 个教师主页")
                return record

        records = await asyncio.gather(*[fetch_one(name, url) for name, url in links])

    merged: dict[str, dict] = {}
    for record in records:
        name = record.get("name", "")
        if not name:
            continue
        old = merged.get(name)
        if old is None or (not old.get("email") and record.get("email")):
            merged[name] = record

    result = list(merged.values())
    result.sort(key=lambda row: (0 if row.get("email") else 1, row.get("name", "")))
    await emit(f"抓取完成：{len(result)} 位教师，其中 {sum(1 for r in result if r.get('email'))} 位提取到邮箱。")
    return result


async def _fetch_list_pages(client: httpx.AsyncClient) -> dict[str, str]:
    async def fetch(url: str) -> tuple[str, str]:
        return url, await _fetch_text(client, url)

    pairs = await asyncio.gather(*[fetch(url) for url in LIST_URLS])
    return dict(pairs)


async def _fetch_text(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(url)
    response.raise_for_status()
    content = response.content
    for encoding in ("utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _extract_teacher_links(list_pages: dict[str, str]) -> list[tuple[str, str]]:
    seen_names: set[str] = set()
    links: list[tuple[str, str]] = []
    for page_url, body in list_pages.items():
        for match in ANCHOR_RE.finditer(body):
            href = html.unescape(match.group(1).strip())
            label = _clean_html_text(match.group(2))
            full_url = urljoin(page_url, href)
            if not _is_chinese_name(label) or not _is_teacher_url(full_url):
                continue
            if label in seen_names:
                continue
            seen_names.add(label)
            links.append((label, full_url))
    return links


def _build_title_map(rank_page_html: str) -> dict[str, str]:
    title_map: dict[str, str] = {}
    current_title = ""
    base_url = "https://cse.seu.edu.cn/49355/list.htm"
    for match in TITLE_OR_ANCHOR_RE.finditer(rank_page_html):
        heading_html, href, label_html = match.groups()
        if heading_html is not None:
            current_title = _normalize_rank_title(_clean_html_text(heading_html))
            continue
        if not current_title or not href:
            continue
        label = _clean_html_text(label_html or "")
        full_url = urljoin(base_url, html.unescape(href.strip()))
        if _is_chinese_name(label) and _is_teacher_url(full_url):
            title_map.setdefault(label, current_title)
    return title_map


async def _fetch_teacher_detail(
    client: httpx.AsyncClient,
    name: str,
    url: str,
    title_hint: str,
) -> dict:
    record = {
        "name": name,
        "email": "",
        "department": DEPARTMENT,
        "title": title_hint,
        "url": url,
    }
    try:
        body = await _fetch_text(client, url)
    except Exception:
        return record

    text = _clean_html_text(body)
    emails = _extract_emails(f"{body}\n{text}")
    seu_email = next((email for email in emails if email.endswith("@seu.edu.cn")), "")
    record["email"] = seu_email or (emails[0] if emails else "")
    if not record["title"]:
        record["title"] = _extract_title_from_text(text)
    return record


def _extract_emails(raw: str) -> list[str]:
    restored = html.unescape(raw or "")
    restored = re.sub(r"(?<=\w)\s*(?:\[at\]|\(at\)|\[@\]|\(@\)|#@)\s*(?=[A-Za-z0-9.-]+\.)", "@", restored, flags=re.I)
    restored = re.sub(r"(?<=\w)\s+(?:AT|at)\s+(?=[A-Za-z0-9.-]+\.[A-Za-z]{2,})", "@", restored)
    restored = re.sub(r"(?<=\w)\s*(?:\[dot\]|\(dot\))\s*(?=\w)", ".", restored, flags=re.I)

    emails: list[str] = []
    for email in EMAIL_RE.findall(restored):
        cleaned = email.strip(".,;:)]}>").lower()
        prefix = cleaned.split("@", 1)[0]
        if any(prefix == public or prefix.startswith(public) for public in PUBLIC_EMAIL_PREFIXES):
            continue
        if cleaned not in emails:
            emails.append(cleaned)
    return emails


def _is_teacher_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    if parsed.netloc == "cs.seu.edu.cn":
        return bool(re.fullmatch(r"/[^/]+/main\.htm", path))
    if parsed.netloc == "cse.seu.edu.cn":
        return path.endswith("/page.htm") or bool(re.search(r"/c\d+a\d+/page\.htm$", path))
    if parsed.netloc == "8.149.133.61":
        return True
    return False


def _is_chinese_name(value: str) -> bool:
    return bool(re.fullmatch(r"[\u4e00-\u9fff]{2,6}", value or ""))


def _clean_html_text(value: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", value or "", flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", "", text).strip()


def _normalize_rank_title(value: str) -> str:
    if "正高" in value:
        return "教授/研究员"
    if "副高" in value:
        return "副教授/副研究员"
    if "中级" in value:
        return "讲师/工程师"
    return value


def _extract_title_from_text(text: str) -> str:
    for title in ("教授", "副教授", "讲师", "研究员", "副研究员", "高级工程师", "工程师", "实验师", "博士后"):
        if title in text:
            return title
    return ""
