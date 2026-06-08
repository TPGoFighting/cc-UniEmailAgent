"""Hermes Agent — 通过 hermes CLI 子进程执行任务，含简报注入 + 知识提取。

HermesAgent: 直接调用 hermes CLI（子进程引擎）
HermesOrchestrator: 简报注入 → 委托 HermesAgent 执行 → 后置知识提取
"""

import asyncio
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from agent.tracing import create_run, end_run
from agent.skill_manager import load_skills_prompt, CRAWL_KNOWLEDGE_FILE
from agent.memory import CrawlMemory, save_to_mem0
from agent.checkpoint import get_resume_briefing, clear_checkpoint

logger = logging.getLogger(__name__)

MAX_STEPS = 10000
TIMEOUT_SECONDS = 600
DEFAULT_MODEL = "deepseek/deepseek-v4-flash"

SKILLS_DIR = Path(__file__).parent.parent / "skills"


class HermesAgent:
    """直接调用 hermes CLI 执行任务（替代 Claude Code CLI）。"""

    def __init__(self):
        self._last_stderr = ""
        self._stopped_tasks: set[str] = set()
        self.active_procs: dict[str, subprocess.Popen] = {}
        self._check_hermes()
        self.model = os.environ.get("HERMES_MODEL", DEFAULT_MODEL)

    def _check_hermes(self) -> bool:
        path = shutil.which("hermes")
        if not path:
            logger.warning("hermes CLI 未找到，将使用回退模式")
            return False
        logger.info(f"hermes CLI 已就绪: {path}")
        return True

    def stop_task(self, task_id: str) -> bool:
        """终止正在运行的 hermes 子进程。"""
        self._stopped_tasks.add(task_id)
        proc = self.active_procs.pop(task_id, None)
        if proc:
            try:
                proc.kill()
                logger.info(f"成功终止 Task {task_id} 的 hermes 子进程")
                return True
            except Exception as e:
                logger.error(f"终止 Task {task_id} 子进程失败: {e}")
        return False

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    async def execute(
        self,
        message: str,
        task_id: str = "",
        is_continuation: bool = False,
        is_crawl_session: bool = True,
        current_user_message: str | None = None,
        intent_result=None,
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        """执行任务：优先走 Hermes CLI，回退到 DeepSeek API 直调。"""
        self._stopped_tasks.discard(task_id)

        if not is_crawl_session:
            eval_msg = current_user_message or message
            has_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
            if has_key:
                try:
                    async for log in self._respond_via_api(eval_msg):
                        yield log
                    return
                except Exception:
                    logger.warning("DeepSeek API 失败，回退 Hermes CLI")

        async for log in self._run_hermes(message, task_id):
            yield log

    async def execute_query(
        self, message: str, task_id: str, task_output_dir: str = ""
    ) -> AsyncGenerator[dict, None]:
        """简单问答：DeepSeek API 流式回答。"""
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if api_key:
            async for log in self._respond_via_api(message):
                yield log
        else:
            yield {"type": "text", "message": "当前未配置 API Key，无法执行查询。", "timestamp": self._timestamp()}
            yield {"type": "done", "message": "无 API Key", "timestamp": self._timestamp()}

    # ═══════════════════════════════════════════════════════════════
    # DeepSeek API 直调
    # ═══════════════════════════════════════════════════════════════

    async def _respond_via_api(self, message: str) -> AsyncGenerator[dict, None]:
        """通过 DeepSeek API 流式回复（非爬取任务）。"""
        from openai import AsyncOpenAI

        key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
        client = AsyncOpenAI(api_key=key, base_url="https://api.deepseek.com/v1")
        try:
            stream = await client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": message}],
                stream=True,
            )
            full = ""
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    full += delta.content
                    yield {"type": "text", "message": full, "timestamp": self._timestamp()}
            yield {"type": "done", "message": "回答完毕", "timestamp": self._timestamp()}
        except Exception as e:
            logger.error(f"DeepSeek API 调用失败: {e}")
            raise

    # ═══════════════════════════════════════════════════════════════
    # Hermes CLI 子进程执行
    # ═══════════════════════════════════════════════════════════════

    async def _run_hermes(
        self, message: str, task_id: str = ""
    ) -> AsyncGenerator[dict, None]:
        """通过 PTY 流式运行 hermes chat --cli，逐行实时推日志。"""
        if not shutil.which("hermes"):
            raise RuntimeError("hermes CLI 未安装")

        # 转义方括号防止 Hermes 的 rich markup 崩溃
        safe_msg = message.replace("[", r"\[").replace("]", r"\]")
        shell_cmd = f"hermes chat -q {shlex.quote(safe_msg)} --yolo -m {shlex.quote(self.model)} --cli"
        env = os.environ.copy()
        task_start = time.time()

        process = await asyncio.create_subprocess_exec(
            "stdbuf", "-o0", "script", "-qfc", shell_cmd, "/dev/null",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self.active_procs[task_id] = process

        reply_text = ""
        try:
            async for raw_line in process.stdout:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                # 清理 ANSI 转义
                cleaned = re.sub(r'\x1b\[[0-9;]*[mK]', '', line)
                stripped = cleaned.strip()
                # 跳过 Query: 开头的 prompt 内容（不是 Agent 日志）
                if not stripped or stripped.startswith("Query:"):
                    continue
                yield {"type": "log", "message": stripped, "timestamp": self._timestamp()}
                reply_text += stripped + "\n"

            await asyncio.wait_for(process.wait(), timeout=10)
        except asyncio.TimeoutError:
            yield {"type": "error", "message": f"任务超时 ({TIMEOUT_SECONDS}s)", "timestamp": self._timestamp()}
            return
        except Exception as e:
            yield {"type": "error", "message": f"执行异常: {str(e)[:200]}", "timestamp": self._timestamp()}
            return
        finally:
            self.active_procs.pop(task_id, None)

        if process.returncode and process.returncode != 0:
            yield {"type": "error", "message": f"Hermes 退出码 {process.returncode}", "timestamp": self._timestamp()}
            return

        # 提取 ⚕ Hermes 块内的回复文本
        final_reply = ""
        in_block = False
        for l in reply_text.split("\n"):
            s = l.strip()
            if "⚕" in s and ("Hermes" in s or "──" in s):
                in_block = True
                continue
            if in_block:
                if s.startswith("──") or s.startswith("─") or "Resume" in s:
                    break
                if s and not s.startswith("⚠"):
                    final_reply += s + "\n"

        final_reply = final_reply.strip()
        if not final_reply and reply_text.strip():
            # 兜底：过滤掉分隔符和标题行
            lines = [l for l in reply_text.strip().split("\n")
                     if l.strip() and not l.strip().startswith("─")
                     and "Resume" not in l and "Session" not in l and "Duration" not in l]
            final_reply = "\n".join(lines[-3:])

        if final_reply:
            yield {"type": "text", "message": final_reply, "timestamp": self._timestamp()}
        yield {"type": "done", "message": "Agent 任务执行完毕", "timestamp": self._timestamp()}

    # ═══════════════════════════════════════════════════════════════
    # Windows 兼容（线程 + subprocess.Popen）
    # ═══════════════════════════════════════════════════════════════

    def _start_subprocess_thread(
        self, cmd: list[str], env: dict, queue: asyncio.Queue, task_id: str, prompt: str = ""
    ) -> None:
        """Windows 兼容：线程 + subprocess.Popen + asyncio.Queue 桥接。"""
        stop_event = threading.Event()

        def _run():
            try:
                si = None
                if sys.platform == "win32":
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = subprocess.SW_HIDE

                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    startupinfo=si,
                )
                self.active_procs[task_id] = proc

                for line in proc.stdout:
                    if stop_event.is_set():
                        break
                    decoded = line.decode("utf-8", errors="replace").strip()
                    if decoded:
                        try:
                            queue.put_nowait(decoded)
                        except asyncio.QueueFull:
                            pass

                proc.wait()
            except Exception as e:
                logger.error(f"子进程线程异常: {e}")
            finally:
                self.active_procs.pop(task_id, None)
                stop_event.set()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()


class HermesOrchestrator(HermesAgent):
    """简报注入 → 委托 HermesAgent 执行 → 后置知识提取。"""

    def __init__(self):
        super().__init__()

    async def execute(
        self,
        message: str,
        task_id: str = "",
        is_continuation: bool = False,
        is_crawl_session: bool = True,
        current_user_message: str | None = None,
        intent_result=None,
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        """简报注入 → 执行 → 知识提取。"""
        self._stopped_tasks.discard(task_id)
        run_id = None
        try:
            uni_name = self._extract_university(message) or "unknown"
            run_id = create_run(f"crawl:{uni_name}", {"task_id": task_id, "message": message[:200]})

            # 简报注入
            briefing = build_briefing(task_id, message, uni_name)
            if briefing:
                message = briefing + "\n\n" + message

            # 执行
            async for log in HermesAgent.execute(
                self, message, task_id, is_continuation, is_crawl_session, current_user_message, intent_result, **kwargs
            ):
                yield log
                if log.get("type") == "done":
                    # 后置知识提取
                    _task_dir = Path("outputs") / task_id
                    if _task_dir.exists():
                        try:
                            extracted = self.extract_knowledge(task_id, _task_dir)
                            url_cnt = len(extracted.get("url_patterns", []))
                            waf_cnt = len(extracted.get("waf_patterns", []))
                            if url_cnt or waf_cnt:
                                yield {"type": "log", "message": f"📝 已提取 {url_cnt} URL 模式、{waf_cnt} WAF 信号",
                                       "timestamp": self._timestamp()}
                        except Exception as e:
                            logger.warning(f"[Hermes] 知识提取失败: {e}")
                    if run_id:
                        end_run(run_id, {"university": uni_name, "phases": "briefing→execute→extract"})
                    clear_checkpoint(task_id)

        except Exception as e:
            logger.error(f"[HermesOrchestrator] 顶层异常: {e}")
            if run_id:
                end_run(run_id, error=str(e)[:200])
            yield {"type": "error", "message": f"Hermes 编排异常: {str(e)[:200]}", "timestamp": self._timestamp()}

    def _extract_university(self, message: str) -> str:
        m = re.search(r"([一-鿿]{2,6}(?:大学|学院))", message)
        return m.group(1) if m else ""

    def extract_knowledge(self, task_id: str, task_dir: Path | str) -> dict:
        """从 agent_output.log 提取爬取经验。"""
        result: dict = {"waf_patterns": [], "url_patterns": [], "email_domains": [], "errors": []}
        try:
            log_path = Path(task_dir) / "agent_output.log"
            if not log_path.exists():
                result["errors"].append("agent_output.log 不存在")
                return result
            content = log_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            result["errors"].append(str(e)[:200])
            return result

        waf_keywords = ["403", "waf", "blocked", "captcha", "验证码", "反爬",
                        "access denied", "429", "503", "cloudflare", "拦截"]
        for line in content.split("\n"):
            low = line.lower()
            for kw in waf_keywords:
                if kw in low:
                    s = line.strip()[:200]
                    if s not in result["waf_patterns"]:
                        result["waf_patterns"].append(s)
                    break

        urls = re.findall(r'https?://[^\s<>"\'\]\)]+', content)
        seen: set[str] = set()
        for u in urls:
            if ".edu." in u and u not in seen:
                seen.add(u)
                result["url_patterns"].append(u)
                if len(result["url_patterns"]) >= 20:
                    break
        return result


def build_briefing(task_id: str, message: str, university: str = "") -> str:
    """构建简报（Mem0 + Skills 历史经验注入）。"""
    parts: list[str] = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    uni_parts = ["📋 爬取范围约束",
                 f"用户指定以下范围：{message[:100]}...",
                 "严格爬取上述范围，不要混入其他学院数据。"]
    parts.append("\n".join(uni_parts))

    # Mem0 历史经验
    try:
        from agent.memory import CrawlMemory
        mem = CrawlMemory()
        if university:
            memories = mem.query(f"爬取 {university} 经验", limit=5)
            if memories:
                mem_lines = ["📚 历史经验 (Mem0)"]
                for m in memories:
                    mem_lines.append(f"- {str(m)[:300]}")
                parts.append("\n".join(mem_lines))
    except Exception as e:
        logger.warning(f"Mem0 查询失败: {e}")

    # Skills 文件
    try:
        skills_prompt = load_skills_prompt(university)
        if skills_prompt:
            parts.append(skills_prompt)
    except Exception as e:
        logger.warning(f"Skills 查询失败: {e}")

    # 任务信息
    info = [
        f"\n## 🔄 任务信息",
        f"- **任务 ID**: {task_id}",
        f"- **创建时间**: {ts}",
        f"- **专属目录**: outputs/{task_id}/",
    ]
    parts.append("\n".join(info))

    return "\n\n".join(parts)
