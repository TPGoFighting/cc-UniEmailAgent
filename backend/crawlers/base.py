"""爬虫抽象基类 — 统一对外接口 + 通用共享工具"""

from __future__ import annotations

import csv
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass

from pydantic import BaseModel, Field

# 从 exporter 导入标准表头，保证列名一致
from agent.exporter import HEADERS as STANDARD_EXPORT_HEADERS

logger = logging.getLogger(__name__)

# ── 正则常量 ──

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

ANTI_SPAM_RULES = [
    (r"\[at\]", "@"), (r"\(at\)", "@"), (r"#@", "@"),
    (r"\[\s*@\s*\]", "@"), (r"\(\s*@\s*\)", "@"),
    (r"\s*at\s*", "@"), (r"\[@\]", "@"), (r"\(@\)", "@"),
]

PUBLIC_EMAIL_PREFIXES = [
    "webmaster", "admin", "office", "info", "master", "root",
    "postmaster", "bgs", "dangzheng", "yuanban", "wxyxz", "xwcb",
    "yanjiu", "office", "support", "contact", "hr", "service",
]

KNOWN_TITLES = [
    "教授/博导", "副教授/硕导", "教授级高级工程师",
    "教授", "副教授", "讲师", "助教", "助理教授",
    "研究员", "副研究员", "助理研究员",
    "高级工程师", "工程师", "助理工程师",
    "博士后", "准聘助理教授", "准聘副教授",
    "主任医师", "副主任医师", "主治医师",
    "高级实验师", "实验师", "教授级高级实验师",
    "副编审", "编审", "研究助理", "访问学者",
]

# CSV 标准字段
CSV_FIELDNAMES = ["院校名称", "教师姓名", "所在学院", "职称", "邮箱", "官网主页链接"]


# ── 数据模型 ──

class TeacherRecord(BaseModel):
    """统一的教师记录模型"""
    院校名称: str = ""
    教师姓名: str
    所在学院: str = ""
    职称: str = ""
    邮箱: str = ""
    官网主页链接: str = ""

    @property
    def has_email(self) -> bool:
        return bool(self.邮箱 and EMAIL_RE.search(self.邮箱))


# ── 抽象基类 ──

class BaseCrawler(ABC):
    """爬虫抽象基类 — 所有大学爬虫必须继承。

    子类只需实现:
        university_name: str          — 大学全称
        crawl(target_departments)     — 核心爬取逻辑
    可选覆盖:
        department_urls               — 学院→URL 映射
    """

    university_name: str = ""

    # ── 子类必须实现 ──

    @abstractmethod
    async def crawl(
        self, target_departments: list[str] | None = None
    ) -> list[TeacherRecord]:
        """核心爬取接口。

        Args:
            target_departments: 目标学院列表，为 None 时爬取全校。

        Returns:
            教师记录列表。
        """
        ...

    # ── 通用工具方法（子类可直接调用） ──

    @staticmethod
    def restore_anti_spam(text: str) -> str:
        """还原反爬虫保护的邮箱格式。"""
        for pattern, repl in ANTI_SPAM_RULES:
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def extract_email(text: str) -> str:
        """从文本中提取并返回第一个有效个人邮箱，无则返回空串。"""
        if not text:
            return ""
        cleaned = BaseCrawler.restore_anti_spam(text)
        for m in EMAIL_RE.finditer(cleaned):
            email = m.group(0)
            if not BaseCrawler.is_public_email(email):
                return email
        return ""

    @staticmethod
    def extract_all_emails(text: str) -> list[str]:
        """从文本中提取所有有效个人邮箱。"""
        if not text:
            return []
        cleaned = BaseCrawler.restore_anti_spam(text)
        return [m.group(0) for m in EMAIL_RE.finditer(cleaned)
                if not BaseCrawler.is_public_email(m.group(0))]

    @staticmethod
    def is_public_email(email: str) -> bool:
        """判断是否为学院/部门公共邮箱。"""
        if not email:
            return True
        prefix = email.split("@")[0].lower()
        return any(prefix.startswith(p) for p in PUBLIC_EMAIL_PREFIXES)

    @staticmethod
    def extract_title(text: str) -> str:
        """从文本中提取职称。"""
        if not text:
            return ""
        for title in KNOWN_TITLES:
            if title in text:
                return title
        return ""

    @staticmethod
    def validate_records(records: list[TeacherRecord]) -> list[TeacherRecord]:
        """去重 + 过滤无效记录（无姓名且无邮箱的丢弃）。"""
        seen: set[str] = set()
        valid: list[TeacherRecord] = []
        for r in records:
            if not r.教师姓名.strip() and not r.邮箱.strip():
                continue
            key = f"{r.教师姓名}|{r.所在学院}|{r.邮箱}"
            if key in seen:
                continue
            seen.add(key)
            valid.append(r)
        return valid

    @staticmethod
    def to_csv(records: list[TeacherRecord], output_dir: str | Path) -> Path:
        """将记录导出为标准 CSV 文件，返回文件路径。"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = records[0].院校名称 if records else "unknown"
        filename = f"{safe_name}_教师邮箱_{ts}.csv"
        filepath = output_dir / filename

        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()
            for r in records:
                writer.writerow({
                    "院校名称": r.院校名称,
                    "教师姓名": r.教师姓名,
                    "所在学院": r.所在学院,
                    "职称": r.职称,
                    "邮箱": r.邮箱,
                    "官网主页链接": r.官网主页链接,
                })

        logger.info(f"[BaseCrawler] CSV 导出: {filepath} ({len(records)} 条)")
        return filepath

    @classmethod
    def get_stats(cls, records: list[TeacherRecord]) -> dict:
        """返回基本统计信息。"""
        total = len(records)
        with_email = sum(1 for r in records if r.has_email)
        depts: dict[str, dict] = {}
        for r in records:
            d = r.所在学院 or "未知学院"
            if d not in depts:
                depts[d] = {"total": 0, "with_email": 0}
            depts[d]["total"] += 1
            if r.has_email:
                depts[d]["with_email"] += 1
        return {
            "total": total,
            "with_email": with_email,
            "email_rate": with_email / total if total else 0.0,
            "departments": len(depts),
            "by_department": depts,
        }
