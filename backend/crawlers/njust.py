"""南京理工大学教师邮箱爬虫 — 基于 BaseCrawler 的标准实现"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import aiohttp

from .base import BaseCrawler, TeacherRecord

logger = logging.getLogger(__name__)


class NJUSTCrawler(BaseCrawler):
    """南京理工大学教师邮箱爬虫。

    基于预抓取的教师列表 JSON，使用 aiohttp 并发访问每位教师的
    个人主页，从中提取邮箱地址。
    """

    university_name = "南京理工大学"

    # 教师 JSON 数据的最小字段要求
    _REQUIRED_JSON_FIELDS = ("title", "department", "cnUrl")

    def __init__(self, concurrency: int = 20, request_timeout: int = 15):
        self._concurrency = concurrency
        self._request_timeout = request_timeout

    async def crawl(
        self, target_departments: list[str] | None = None
    ) -> list[TeacherRecord]:
        """爬取南京理工大学教师邮箱。

        教师数据来源：项目根目录下的 njust_all_teachers.json。

        Args:
            target_departments: 目标学院名列表，为 None 时爬取全部。
        """
        # 加载教师列表
        teachers = self._load_teachers()
        if not teachers:
            logger.error("[NJUST] 未找到教师数据 JSON")
            return []

        # 按学院过滤
        if target_departments:
            target_set = set(target_departments)
            teachers = [t for t in teachers if t.get("department", "") in target_set]

        logger.info(f"[NJUST] 目标教师: {len(teachers)} 人，并发: {self._concurrency}")

        # 并发抓取
        sem = asyncio.Semaphore(self._concurrency)
        connector = aiohttp.TCPConnector(limit=self._concurrency + 10)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }

        async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
            tasks = [self._fetch_teacher(session, t, sem) for t in teachers]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        records: list[TeacherRecord] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.debug(f"[NJUST] {teachers[i].get('title', '?')} 异常: {result}")
            elif result is not None:
                records.append(result)

        logger.info(f"[NJUST] 共获取 {len(records)} 条记录")
        return self.validate_records(records)

    async def _fetch_teacher(
        self, session: aiohttp.ClientSession, teacher: dict, sem: asyncio.Semaphore
    ) -> TeacherRecord | None:
        """访问单个教师主页，提取邮箱。"""
        url = teacher.get("cnUrl", "")
        if not url:
            return TeacherRecord(
                院校名称=self.university_name,
                教师姓名=teacher.get("title", ""),
                所在学院=teacher.get("department", ""),
                职称=teacher.get("career", ""),
            )

        async with sem:
            try:
                timeout = aiohttp.ClientTimeout(total=self._request_timeout)
                async with session.get(url, timeout=timeout) as resp:
                    if resp.status != 200:
                        return TeacherRecord(
                            院校名称=self.university_name,
                            教师姓名=teacher.get("title", ""),
                            所在学院=teacher.get("department", ""),
                            职称=teacher.get("career", ""),
                            官网主页链接=url,
                        )
                    text = await resp.text()
            except Exception:
                return TeacherRecord(
                    院校名称=self.university_name,
                    教师姓名=teacher.get("title", ""),
                    所在学院=teacher.get("department", ""),
                    职称=teacher.get("career", ""),
                    官网主页链接=url,
                )

        email = self.extract_email(text) or "无邮箱"
        return TeacherRecord(
            院校名称=self.university_name,
            教师姓名=teacher.get("title", ""),
            所在学院=teacher.get("department", ""),
            职称=teacher.get("career", ""),
            邮箱=email,
            官网主页链接=url,
        )

    def _load_teachers(self) -> list[dict]:
        """加载教师列表 JSON。"""
        # 从项目根目录查找
        json_paths = [
            Path(__file__).parent.parent / "njust_all_teachers.json",
            Path("njust_all_teachers.json"),
        ]
        for jp in json_paths:
            if jp.exists():
                try:
                    data = json.loads(jp.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        return data
                except (json.JSONDecodeError, OSError) as e:
                    logger.error(f"[NJUST] JSON 解析失败: {e}")
        return []
