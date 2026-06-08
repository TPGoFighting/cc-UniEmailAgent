"""南京大学教师邮箱爬虫 — 基于 BaseCrawler 的标准实现"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from playwright.async_api import async_playwright

from .base import BaseCrawler, TeacherRecord

logger = logging.getLogger(__name__)


class NJUCrawler(BaseCrawler):
    """南京大学教师邮箱爬虫。

    使用 Playwright 操作浏览器，进入各学院的师资列表页，
    提取教师姓名和详情页链接，再逐人访问详情页提取邮箱。
    """

    university_name = "南京大学"

    # 学院 → (学院名, 师资列表页 URL, 官网首页)
    COLLEGES: list[tuple[str, str, str]] = [
        ("文学院", "https://chin.nju.edu.cn/szdw/xrjs/index.html", "http://chin.nju.edu.cn/"),
        ("历史学院", "https://history.nju.edu.cn/28475/list.htm", "http://history.nju.edu.cn/"),
        ("哲学学院", "https://philo.nju.edu.cn/4712/list.htm", "http://philo.nju.edu.cn/"),
        ("新闻传播学院", "https://jc.nju.edu.cn/jzyg/zzjs.htm", "http://jc.nju.edu.cn/"),
        ("法学院", "https://law.nju.edu.cn/szdw/zzjs1/js.htm", "https://law.nju.edu.cn/"),
        ("商学院", "https://nubs.nju.edu.cn/8878/list.htm", "https://nubs.nju.edu.cn/"),
        ("外国语学院", "https://sfs.nju.edu.cn/szdw/index.html", "http://sfs.nju.edu.cn/"),
        ("政府管理学院", "https://public.nju.edu.cn/szdw", "http://public.nju.edu.cn/"),
        ("国际关系学院", "https://sis.nju.edu.cn/jsrk/list.htm", "https://sis.nju.edu.cn/"),
        ("信息管理学院", "https://im.nju.edu.cn/szll/zzjs.htm", "http://im.nju.edu.cn/"),
        ("社会学院", "https://sociology.nju.edu.cn/szdw/list.htm", "http://sociology.nju.edu.cn/"),
        ("数学学院", "https://math.nju.edu.cn/jzyg/index.html", "http://math.nju.edu.cn/"),
        ("物理学院", "https://physics.nju.edu.cn/szdw/qbmd/index.html", "http://physics.nju.edu.cn/"),
        ("天文与空间科学学院", "https://astronomy.nju.edu.cn/szll/index.html", "http://astronomy.nju.edu.cn/"),
        ("化学化工学院", "https://chem.nju.edu.cn/szll/list.htm", "http://chem.nju.edu.cn/"),
        ("计算机学院", "https://cs.nju.edu.cn/1651/list.htm", "http://cs.nju.edu.cn/"),
        ("软件学院", "https://software.nju.edu.cn/szll/szdw/index.html", "http://software.nju.edu.cn/"),
        ("人工智能学院", "https://ai.nju.edu.cn/people/list.htm", "http://ai.nju.edu.cn/"),
        ("电子科学与工程学院", "https://ese.nju.edu.cn/22542/list.htm", "http://ese.nju.edu.cn/"),
        ("现代工程与应用科学学院", "https://eng.nju.edu.cn/43271/list.htm", "http://eng.nju.edu.cn/"),
        ("环境学院", "http://hjxy.nju.edu.cn/szdw/index.html", "http://hjxy.nju.edu.cn/"),
        ("地球科学与工程学院", "https://es.nju.edu.cn/25235/list.htm", "http://es.nju.edu.cn/"),
        ("地理与海洋科学学院", "http://sgos.nju.edu.cn/62681/list.htm", "http://sgos.nju.edu.cn/"),
        ("大气科学学院", "http://as.nju.edu.cn/js/list.htm", "http://as.nju.edu.cn/"),
        ("生命科学学院", "https://life.nju.edu.cn/szdw/list.htm", "http://life.nju.edu.cn/"),
        ("医学院", "https://med.nju.edu.cn/10649/list.htm", "http://med.nju.edu.cn/"),
        ("工程管理学院", "https://sme.nju.edu.cn/xssz/list.htm", "http://sme.nju.edu.cn/"),
        ("匡亚明学院", "https://dii.nju.edu.cn/kyds/list.htm", "http://dii.nju.edu.cn/"),
        ("建筑与城市规划学院", "http://arch.nju.edu.cn/szdw/index.html", "http://arch.nju.edu.cn/"),
    ]

    def __init__(self, concurrency: int = 3):
        self._concurrency = concurrency  # 学院并发数

    async def crawl(
        self, target_departments: list[str] | None = None
    ) -> list[TeacherRecord]:
        """爬取南京大学教师邮箱。

        Args:
            target_departments: 目标学院名列表，为 None 时爬取全部学院。
        """
        # 过滤目标学院
        colleges = self.COLLEGES
        if target_departments:
            target_set = set(target_departments)
            colleges = [c for c in colleges if c[0] in target_set]

        logger.info(f"[NJU] 目标学院: {len(colleges)} 个，并发数: {self._concurrency}")

        all_records: list[TeacherRecord] = []
        sem = asyncio.Semaphore(self._concurrency)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                tasks = [self._crawl_college(browser, cfg, sem) for cfg in colleges]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"[NJU] 学院 {colleges[i][0]} 异常: {result}")
                    else:
                        all_records.extend(result)

            finally:
                await browser.close()

        logger.info(f"[NJU] 共爬取 {len(all_records)} 条记录")
        return self.validate_records(all_records)

    async def _crawl_college(self, browser, cfg: tuple, sem: asyncio.Semaphore) -> list[TeacherRecord]:
        """爬取单个学院。"""
        college_name, list_url, home_url = cfg
        records: list[TeacherRecord] = []

        async with sem:
            page = await browser.new_page()
            try:
                await page.goto(list_url, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

                # 提取教师条目链接
                teacher_links = await page.evaluate("""() => {
                    const links = document.querySelectorAll('a');
                    const teachers = [];
                    const nameRe = /[\\u4e00-\\u9fff]{2,4}/;
                    for (const a of links) {
                        const text = a.textContent.trim();
                        const href = a.href;
                        if (nameRe.test(text) && text.length <= 6 && href) {
                            teachers.push({ name: text, url: href });
                        }
                    }
                    return teachers;
                }""")

                # 逐人访问详情页
                for t in teacher_links[:80]:  # 每个学院最多 80 人
                    try:
                        await page.goto(t["url"], timeout=15000, wait_until="domcontentloaded")
                        await page.wait_for_timeout(500)
                        page_text = await page.content()
                        email = self.extract_email(page_text)
                        title = self.extract_title(page_text)

                        records.append(TeacherRecord(
                            院校名称=self.university_name,
                            教师姓名=t["name"],
                            所在学院=college_name,
                            职称=title,
                            邮箱=email,
                            官网主页链接=t["url"],
                        ))
                    except Exception as e:
                        logger.debug(f"[NJU] 教师详情页失败: {t['name']} — {e}")
                        continue

            except Exception as e:
                logger.error(f"[NJU] 学院页面失败: {college_name} — {e}")
            finally:
                await page.close()

        logger.info(f"[NJU] {college_name}: {len(records)} 人")
        return records
