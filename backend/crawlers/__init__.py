"""高校爬虫脚本库 — 各大学专项爬取脚本。

标准接口:
    from crawlers.base import BaseCrawler, TeacherRecord
    from crawlers.nju import NJUCrawler
    from crawlers.njust import NJUSTCrawler

使用示例:
    crawler = NJUCrawler(concurrency=3)
    records = await crawler.crawl(target_departments=["计算机学院"])
    path = BaseCrawler.to_csv(records, "outputs/task_001/")
    stats = BaseCrawler.get_stats(records)
"""

from .base import BaseCrawler, TeacherRecord
from .nju import NJUCrawler
from .njust import NJUSTCrawler

# 已收录的大学爬虫（旧版脚本保留在 crawlers/ 目录中，逐步迁移）：
# - nju_*.py          → nju.py (已标准化)
# - crawl_njust_*.py  → njust.py (已标准化)
# - crawl_nuaa_*.py   南京航空航天大学（待迁移）
# - crawl_seu_*.py    东南大学（待迁移）

__all__ = [
    "BaseCrawler",
    "TeacherRecord",
    "NJUCrawler",
    "NJUSTCrawler",
]
