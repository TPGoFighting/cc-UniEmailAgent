"""Hermes Orchestrator — 简报注入 + 单次委托 + 知识提取。

流程：生成历史简报（Mem0 + Skills）→ 委托 ClaudeAgent 执行 → 从日志提取经验。
"""

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from agent.claude_agent import ClaudeAgent
from agent.tracing import create_run, end_run
from agent.skill_manager import load_skills_prompt, CRAWL_KNOWLEDGE_FILE
from agent.memory import CrawlMemory, save_to_mem0
from agent.checkpoint import get_resume_briefing, clear_checkpoint

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent.parent / "skills"


class HermesOrchestrator:
    """Hermes 编排引擎：历史简报注入 → 单次委托 ClaudeAgent → 后置知识提取。"""

    def __init__(self):
        self._stopped_tasks: set[str] = set()
        self.active_procs: dict[str, asyncio.Task] = {}
        self._claude = ClaudeAgent()

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def stop_task(self, task_id: str = "") -> bool:
        self._stopped_tasks.add(task_id)
        proc = self.active_procs.get(task_id)
        if proc and not proc.done():
            proc.cancel()
            return True
        return False

    def _extract_university(self, message: str) -> str:
        """从消息中提取大学名。"""
        m = re.search(r"([一-鿿]{2,6}(?:大学|学院))", message)
        return m.group(1) if m else ""

    # ═══════════════════════════════════════════════════════════════
    # 简报生成
    # ═══════════════════════════════════════════════════════════════

    def generate_briefing(self, university: str, task_id: str = "") -> str:
        """从 通用经验 → Mem0 精确搜索 → Mem0 扩展搜索 → Skills 文件，返回结构化 Markdown 简报。

        所有子调用均内置 try/except 兜底。
        """
        parts: list[str] = []

        # 0. 通用爬取经验（所有高校共享，短小精悍）
        try:
            tips_path = Path(__file__).resolve().parent.parent / "skills" / "universal_crawling_tips.md"
            if tips_path.exists():
                tips = tips_path.read_text(encoding="utf-8").strip()
                if tips:
                    parts.append(tips)
        except Exception as e:
            logger.warning(f"[Hermes] 通用经验加载失败: {e}")

        # 1. 精确大学名搜索
        try:
            mem0_result = CrawlMemory.get_instance().search_relevant(
                f"{university} 爬取 教师邮箱 反爬 WAF URL",
                university=university,
                limit=5,
            )
            if mem0_result:
                parts.append(mem0_result)
        except Exception as e:
            logger.warning(f"[Hermes] Mem0 精确搜索失败: {e}")

        # 2. 语义扩展搜索（不限定大学名，找结构化相似的经验）
        if university:
            try:
                broad_result = CrawlMemory.get_instance().search_relevant(
                    f"{university[:2]} 大学 爬取 教师网站 结构 WAF 反爬",
                    university="",
                    limit=3,
                )
                if broad_result:
                    parts.append(f"## 🌐 同类型大学参考\n\n{broad_result}")
            except Exception as e:
                logger.warning(f"[Hermes] Mem0 扩展搜索失败: {e}")

        # 3. Skills 文件系统
        try:
            skills_prompt = load_skills_prompt(university)
            if skills_prompt:
                parts.append(skills_prompt)
        except Exception as e:
            logger.warning(f"[Hermes] Skills 查询失败: {e}")

        # 4. 断点续传检测（已有部分完成的任务，跳过已完成学院）
        if university and task_id:
            resume_info = get_resume_briefing(task_id, university)
            if resume_info:
                parts.append(resume_info)

        if not parts:
            return ""

        header = (
            f"## 🧠 {university} 历史爬取简报\n\n"
            "以下是从过往任务中自动提取的经验与避坑指南，请在执行前仔细阅读：\n\n"
        )
        return header + "\n\n---\n\n".join(parts)

    # ═══════════════════════════════════════════════════════════════
    # 知识提取
    # ═══════════════════════════════════════════════════════════════

    def extract_knowledge(self, task_id: str, task_dir: Path | str) -> dict:
        """从 agent_output.log 提取 WAF/URL/邮箱规律等经验，写入 Mem0 + skills。

        返回提取结果摘要 dict，失败时返回空结构（不影响主流程）。
        """
        result: dict = {"waf_patterns": [], "url_patterns": [], "email_domains": [], "errors": []}

        # ── 读取日志 ──
        try:
            log_path = Path(task_dir) / "agent_output.log"
            if not log_path.exists():
                result["errors"].append("agent_output.log 不存在")
                return result
            content = log_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"[Hermes] 读取 agent_output.log 失败: {e}")
            result["errors"].append(str(e)[:200])
            return result

        # ── 提取 WAF/反爬关键词 ──
        waf_keywords = [
            "403", "waf", "blocked", "captcha", "验证码", "反爬", "防火墙",
            "access denied", "too many requests", "429", "503", "cloudflare",
            "challenge", "js盾", "5秒盾", "拦截",
        ]
        for line in content.split("\n"):
            line_lower = line.lower()
            for kw in waf_keywords:
                if kw in line_lower:
                    stripped = line.strip()[:200]
                    if stripped not in result["waf_patterns"]:
                        result["waf_patterns"].append(stripped)
                    break

        # ── 提取教育域名 URL ──
        url_pattern = re.findall(r'https?://[^\s<>"\'\]\)]+', content)
        seen_urls: set[str] = set()
        for u in url_pattern:
            if ".edu." in u and u not in seen_urls:
                seen_urls.add(u)
                result["url_patterns"].append(u)
                if len(result["url_patterns"]) >= 20:
                    break

        # ── 提取邮箱域名分布 ──
        email_pattern = re.findall(
            r'[a-zA-Z0-9._%+-]+@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', content
        )
        domain_counts: dict[str, int] = {}
        for domain in email_pattern:
            # 过滤公共邮箱服务
            if domain.lower() in ("gmail.com", "qq.com", "163.com", "126.com", "outlook.com",
                                   "hotmail.com", "foxmail.com", "sina.com", "aliyun.com"):
                continue
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        result["email_domains"] = sorted(domain_counts.items(), key=lambda x: -x[1])[:10]

        # ── 提取大学名 ──
        uni_name = ""
        for line in content.split("\n")[:50]:
            m = self._extract_university(line)
            if m:
                uni_name = m
                break

        # ── 写入 Mem0 ──
        experience_text = self._build_experience_text(uni_name, result)
        if experience_text:
            try:
                ok = save_to_mem0(uni_name or "unknown", task_id, experience_text[:2000])
                if ok:
                    logger.info(f"[Hermes] 经验已写入 Mem0: {uni_name or 'unknown'}")
            except Exception as e:
                logger.warning(f"[Hermes] Mem0 写入失败: {e}")

        # ── 写入 Skills（异步写入 crawl_knowledge.md） ──
        if experience_text and uni_name:
            try:
                self._write_to_skills(task_id, uni_name, experience_text)
            except Exception as e:
                logger.warning(f"[Hermes] Skills 写入失败: {e}")

        # ── 更新通用经验文件（有新发现的 WAF/策略时追加） ──
        self._update_universal_tips(result, uni_name)

        return result

    def _update_universal_tips(self, extracted: dict, university: str) -> None:
        """爬取完成后更新通用经验文件。发现新 WAF/新策略时追加，超过阈值时压缩。"""
        tips_path = Path(__file__).resolve().parent.parent / "skills" / "universal_crawling_tips.md"
        try:
            current = tips_path.read_text(encoding="utf-8").strip() if tips_path.exists() else ""
        except Exception:
            current = ""

        # 提取新发现中值得加入通用经验的部分
        new_lines: list[str] = []
        waf_found = [p for p in extracted.get("waf_patterns", []) if any(kw in p.lower()
                      for kw in ["ztrust", "safeline", "cloudflare", "412", "js盾", "5秒盾"])]
        if waf_found:
            # 检查是否已在通用经验中
            for w in waf_found:
                kw = w.strip()[:60]
                if kw not in current:
                    new_lines.append(f"- **WAF 记录**: `{kw}`（来自 {university}）")

        # 邮箱域名规律
        domains = extracted.get("email_domains", [])
        edu_domains = [d for d, c in domains if "edu" in d]
        if edu_domains and "邮箱格式" not in current:
            new_lines.append(f"- **主邮箱域名**: `@{edu_domains[0]}`（来自 {university}）")

        if new_lines:
            prefix = "\n## 新增经验\n\n" if "新增经验" not in current else "\n"
            current += prefix + "\n".join(new_lines) + "\n"

        # 超过 300 行 → 压缩
        line_count = len(current.split("\n"))
        if line_count > 300:
            try:
                brief = []
                for line in current.split("\n"):
                    if line.startswith("#") or line.strip() == "":
                        brief.append(line)
                    elif line.strip():
                        # 去除非核心行（保留策略编号的行和关键信息）
                        if any(kw in line for kw in ["**", "1.", "2.", "3.", "4.", "5.", "6.",
                                                      "7.", "8.", "9.", "10.", "- WAF", "- **主邮箱",
                                                      "## ", "> "]):
                            brief.append(line)
                compressed = "\n".join(brief)
                # 确保不短于 30 行（保留核心内容）
                if len(compressed.split("\n")) >= 30:
                    current = compressed
                    logger.info("[Hermes] 通用经验已压缩至 %d 行", len(compressed.split("\n")))
            except Exception as e:
                logger.warning(f"[Hermes] 压缩通用经验失败: {e}")

        try:
            tips_path.parent.mkdir(parents=True, exist_ok=True)
            tips_path.write_text(current, encoding="utf-8")
        except Exception as e:
            logger.warning(f"[Hermes] 写入通用经验失败: {e}")

    def _build_experience_text(self, university: str, extracted: dict) -> str:
        """将提取的结构化数据组装成经验文本。"""
        lines: list[str] = []

        if extracted.get("waf_patterns"):
            lines.append("### WAF/反爬信号")
            for p in extracted["waf_patterns"][:5]:
                lines.append(f"- {p}")
            lines.append("")

        if extracted.get("url_patterns"):
            lines.append("### 发现的 URL 模式")
            for u in extracted["url_patterns"][:10]:
                lines.append(f"- {u}")
            lines.append("")

        if extracted.get("email_domains"):
            lines.append("### 邮箱域名分布")
            for domain, count in extracted["email_domains"]:
                lines.append(f"- `@{domain}`: {count} 个")
            lines.append("")

        return "\n".join(lines) if lines else ""

    def _write_to_skills(self, task_id: str, university: str, experience: str) -> None:
        """将提取的经验追加写入 crawl_knowledge.md（同步、非阻塞）。"""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        section = (
            f"\n\n## 🏫 {university} — {ts}（任务 {task_id[:8]}，自动提取）\n\n"
            f"{experience}\n"
        )

        try:
            if CRAWL_KNOWLEDGE_FILE.exists():
                existing = CRAWL_KNOWLEDGE_FILE.read_text(encoding="utf-8")
                updated = existing.rstrip() + section
            else:
                updated = (
                    "# 🧠 高校爬虫技能知识库\n\n"
                    "本文件由系统自动维护，记录各高校爬取过程中的实战经验和避坑指南。\n\n"
                    "---\n"
                    + section
                )

            # 原子写入
            tmp = CRAWL_KNOWLEDGE_FILE.with_suffix(".tmp")
            tmp.write_text(updated, encoding="utf-8")
            tmp.replace(CRAWL_KNOWLEDGE_FILE)
            logger.info(f"[Hermes] 经验已写入 skills: {university}")
        except Exception as e:
            logger.warning(f"[Hermes] skills 写入失败: {e}")

    # ═══════════════════════════════════════════════════════════════
    # 编排执行
    # ═══════════════════════════════════════════════════════════════

    async def execute_query(
        self,
        message: str,
        task_id: str,
        task_output_dir: str = "",
    ) -> AsyncGenerator[dict, None]:
        """简单问答：委托给 ClaudeAgent。"""
        try:
            async for log in self._claude.execute_query(message, task_id, task_output_dir):
                yield log
        except Exception as e:
            logger.error(f"[Hermes] execute_query 异常: {e}")
            yield {
                "type": "error",
                "message": f"查询异常: {str(e)[:200]}",
                "timestamp": self._timestamp(),
            }

    async def execute(
        self,
        message: str,
        task_id: str = "",
        intent_result=None,
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        """编排执行：简报注入 → 单次委托 ClaudeAgent → 后置知识提取。

        intent_result: 来自 intent_router 的分类结果（可选）。
        **kwargs: 透传给 ClaudeAgent.execute()（is_continuation / is_crawl_session 等）。
        """
        self._stopped_tasks.discard(task_id)

        uni_name = intent_result.university_name if intent_result else self._extract_university(message)
        run_id = create_run("hermes_execute", {
            "task_id": task_id,
            "university": uni_name,
            "message": message[:200],
        })

        try:
            # ── Phase 1: 生成历史简报并注入 prompt ──
            briefing = self.generate_briefing(uni_name, task_id) if uni_name else ""
            if briefing:
                yield {
                    "type": "log",
                    "message": f"📚 已加载 {uni_name} 的历史爬取经验（Mem0 + Skills 知识库）",
                    "timestamp": self._timestamp(),
                }
                enriched_message = briefing + "\n\n---\n\n" + message
            else:
                enriched_message = message

            # 附加断点续传指令（每个学院完成后写 checkpoint）
            if task_id:
                cp_instruction = (
                    f"\n\n## 📍 断点续传指令\n"
                    f"任务目录: outputs/{task_id}/\n"
                    f"每完成一个学院的爬取，请在 outputs/{task_id}/checkpoint.json 中记录进度。\n"
                    f"格式: {{ \"done_colleges\": [{{\"name\": \"学院名\", \"found\": N, \"emails\": N, \"status\": \"done\"}}], \"total_colleges\": N }}\n"
                    f"后续连接会读取 checkpoint 跳过已完成的学院，不要重复爬取。\n"
                )
                enriched_message += cp_instruction

            # ── Phase 2: 单次委托 ClaudeAgent 执行（带超时兜底） ──
            got_done = False
            try:
                async with asyncio.timeout(3600):  # 1 小时总超时
                    async for log in self._claude.execute(enriched_message, task_id, **kwargs):
                        if task_id in self._stopped_tasks:
                            yield {
                                "type": "log",
                                "message": "⏹️ 任务已被手动终止",
                                "timestamp": self._timestamp(),
                            }
                            break
                        if log.get("type") == "done":
                            got_done = True
                        if log.get("type") == "error":
                            got_done = True
                        yield log
            except asyncio.TimeoutError:
                logger.warning(f"[Hermes] task {task_id[:8]} 执行超时，自动完成")
                yield {
                    "type": "done",
                    "message": "任务执行超时，已自动完成",
                    "timestamp": self._timestamp(),
                }
                got_done = True
            except Exception as e:
                logger.error(f"[Hermes] ClaudeAgent 执行异常: {e}")
                yield {
                    "type": "error",
                    "message": f"执行异常: {str(e)[:200]}",
                    "timestamp": self._timestamp(),
                }

            # ── Phase 3: 后置知识提取（从 agent_output.log 自动提取经验） ──
            if task_id and uni_name:
                task_dir = Path(f"outputs/{task_id}")
                try:
                    extracted = self.extract_knowledge(task_id, task_dir)
                    url_count = len(extracted.get("url_patterns", []))
                    waf_count = len(extracted.get("waf_patterns", []))
                    if url_count or waf_count:
                        yield {
                            "type": "log",
                            "message": (
                                f"📝 已从日志提取 {url_count} 条 URL 模式、"
                                f"{waf_count} 条 WAF 信号，已写入 Mem0 + Skills"
                            ),
                            "timestamp": self._timestamp(),
                        }
                except Exception as e:
                    logger.warning(f"[Hermes] 知识提取失败（不影响主流程）: {e}")

            end_run(run_id, {"university": uni_name, "phases": "briefing→execute→extract"})
            # 清理 checkpoint（任务正常完成）
            if task_id:
                clear_checkpoint(task_id)
            yield {"type": "done", "message": "任务执行完毕", "timestamp": self._timestamp()}

        except Exception as e:
            logger.error(f"[Hermes] execute 顶层异常: {e}")
            end_run(run_id, error=str(e)[:200])
            yield {
                "type": "error",
                "message": f"Hermes 编排异常: {str(e)[:200]}",
                "timestamp": self._timestamp(),
            }
