"""Hermes Agent — 通过 hermes CLI 子进程执行任务，含简报注入 + 知识提取。

HermesAgent: 直接调用 hermes CLI（类似 ClaudeAgent 调 claude CLI）
HermesOrchestrator: 简报注入 → 委托 HermesAgent 执行 → 后置知识提取
"""

import asyncio
import json
import logging
import os
import re
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
HERMES_STARTUP_TIMEOUT = 30
DEFAULT_MODEL = "deepseek/deepseek-v4-pro"

SKILLS_DIR = Path(__file__).parent.parent / "skills"


class HermesAgent:
    """直接调用 hermes CLI 执行任务（类似 ClaudeAgent 调 claude CLI）。

    子进程调用: hermes chat -q "prompt" --yolo -m deepseek/deepseek-v4-pro --json
    输出解析: JSON 行 → log/text/error/download/done 消息流
    """

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
        """执行任务：直接调用 hermes CLI。

        对于非爬取会话，优先用 DeepSeek API 秒回；否则拉起 hermes CLI 子进程。
        """
        self._stopped_tasks.discard(task_id)

        if not is_crawl_session:
            eval_msg = current_user_message or message
            has_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
            if has_key:
                async for log in self._respond_via_api(eval_msg):
                    yield log
                return

        async for log in self._run_hermes(message, task_id, is_continuation):
            yield log

    async def execute_query(
        self,
        message: str,
        task_id: str,
        task_output_dir: str = "",
    ) -> AsyncGenerator[dict, None]:
        """简单问答：直接用 DeepSeek API 流式回答，不启动 hermes CLI。"""
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if api_key:
            async for log in self._respond_via_api(message):
                yield log
        else:
            yield {
                "type": "text",
                "message": "当前未配置 API Key，无法执行查询。",
                "timestamp": self._timestamp(),
            }
            yield {"type": "done", "message": "无 API Key", "timestamp": self._timestamp()}

    # ═══════════════════════════════════════════════════════════════
    # 子进程管理
    # ═══════════════════════════════════════════════════════════════

    async def _run_hermes(
        self, message: str, task_id: str = "", is_continuation: bool = False
    ) -> AsyncGenerator[dict, None]:
        """通过子进程运行 hermes chat --json，流式解析输出。"""
        if not shutil.which("hermes"):
            raise RuntimeError("hermes CLI 未安装")

        prompt = message
        cmd = [
            "hermes", "chat",
            "-q", prompt,
            "--yolo",
            "-m", self.model,
            "--cli",
        ]

        env = os.environ.copy()
        task_start = time.time()

        if sys.platform == "win32":
            queue: asyncio.Queue = asyncio.Queue()
            self._start_subprocess_thread(cmd, env, queue, task_id, prompt)
            async for log in self._process_output(queue, task_id, task_start, message):
                yield log
        else:
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
                self.active_procs[task_id] = process
                try:
                    process.stdin.write(prompt.encode("utf-8"))
                    await process.stdin.drain()
                    process.stdin.close()
                except Exception as e:
                    logger.warning(f"stdin 写入异常: {e}")
            except NotImplementedError:
                queue = asyncio.Queue()
                self._start_subprocess_thread(cmd, env, queue, task_id, prompt)
                async for log in self._process_output(queue, task_id, task_start, message):
                    yield log
                return

            async for log in self._process_output(process, task_id, task_start, message):
                yield log

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

                if prompt:
                    try:
                        proc.stdin.write(prompt.encode("utf-8"))
                        proc.stdin.flush()
                        proc.stdin.close()
                    except (BrokenPipeError, OSError) as e:
                        logger.warning(f"stdin 写入失败: {e}")

                def _read_stderr():
                    try:
                        while not stop_event.is_set():
                            chunk = proc.stderr.read(65536)
                            if not chunk:
                                break
                            self._last_stderr = chunk.decode("utf-8", errors="replace")[-500:]
                    except Exception:
                        pass

                stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
                stderr_thread.start()

                for line in proc.stdout:
                    if stop_event.is_set():
                        break
                    decoded = line.decode("utf-8", errors="replace").strip()
                    if decoded:
                        try:
                            queue.put_nowait({"_type": "line", "data": decoded})
                        except asyncio.QueueFull:
                            pass

                proc.wait()
                stderr_thread.join(timeout=2)

                if proc.returncode != 0:
                    err = getattr(self, "_last_stderr", "")
                    logger.warning(f"hermes 进程退出码 {proc.returncode}: {err[-300:]}")
                    try:
                        queue.put_nowait({
                            "_type": "error",
                            "message": f"Hermes CLI 异常退出（退出码 {proc.returncode}）：{err[-300:]}" if err else f"Hermes CLI 异常退出（退出码 {proc.returncode}）",
                        })
                    except asyncio.QueueFull:
                        pass
            except Exception as e:
                logger.error(f"子进程线程异常: {e}")
            finally:
                self.active_procs.pop(task_id, None)
                stop_event.set()
                try:
                    queue.put_nowait({"_type": "done"})
                except asyncio.QueueFull:
                    pass

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    # ═══════════════════════════════════════════════════════════════
    # 输出流处理
    # ═══════════════════════════════════════════════════════════════

    async def _process_output(
        self,
        source,
        task_id: str,
        task_start: float,
        message: str,
    ) -> AsyncGenerator[dict, None]:
        """处理 hermes CLI 输出：JSON 行解析 + 纯文本兜底。"""
        is_threaded = isinstance(source, asyncio.Queue)

        if not is_threaded:
            try:
                source.stdout._limit = 10 * 1024 * 1024  # 10MB
            except AttributeError:
                pass
            stderr_task = asyncio.create_task(self._drain_stderr(source.stderr))

        step_count = 0
        has_output = False
        tracked_files: list[Path] = []
        collected_text: list[str] = []

        try:
            if is_threaded:
                while True:
                    try:
                        msg = await asyncio.wait_for(source.get(), timeout=TIMEOUT_SECONDS)
                    except asyncio.TimeoutError:
                        yield {
                            "type": "error",
                            "message": f"任务超时 ({TIMEOUT_SECONDS}s)，已终止",
                            "timestamp": self._timestamp(),
                        }
                        return

                    if msg["_type"] == "line":
                        step_count += 1
                        if step_count > MAX_STEPS:
                            yield {
                                "type": "log",
                                "message": f"达到最大步数限制 ({MAX_STEPS})，任务已终止",
                                "timestamp": self._timestamp(),
                            }
                            break

                        parsed = self._parse_output_line(msg["data"])
                        if parsed:
                            has_output = True
                            async for log in self._yield_parsed(parsed, collected_text, tracked_files):
                                yield log

                    elif msg["_type"] == "error":
                        yield {
                            "type": "error",
                            "message": msg.get("message", "Hermes CLI 进程异常退出"),
                            "timestamp": self._timestamp(),
                        }
                    elif msg["_type"] == "done":
                        break
            else:
                async for raw_line in source.stdout:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    step_count += 1
                    if step_count > MAX_STEPS:
                        source.kill()
                        yield {
                            "type": "log",
                            "message": f"达到最大步数限制 ({MAX_STEPS})，任务已终止",
                            "timestamp": self._timestamp(),
                        }
                        break

                    parsed = self._parse_output_line(line)
                    if parsed:
                        has_output = True
                        async for log in self._yield_parsed(parsed, collected_text, tracked_files):
                            yield log

                await asyncio.wait_for(source.wait(), timeout=10)

        except asyncio.TimeoutError:
            if not is_threaded:
                source.kill()
            yield {
                "type": "error",
                "message": f"任务超时 ({TIMEOUT_SECONDS}s)，已终止",
                "timestamp": self._timestamp(),
            }
            return
        finally:
            self.active_procs.pop(task_id, None)
            if not is_threaded:
                stderr_task.cancel()
                try:
                    await stderr_task
                except (asyncio.CancelledError, Exception):
                    pass

        # ── 推送下载文件 ──
        async for log in self._push_files(collected_text, tracked_files, task_id, task_start, message):
            yield log

        if not has_output:
            err_text = getattr(self, "_last_stderr", "无 stderr 输出")
            raise RuntimeError(f"Hermes CLI 无输出: {err_text}")

        yield {
            "type": "done",
            "message": "Agent 任务执行完毕",
            "timestamp": self._timestamp(),
        }

    async def _yield_parsed(
        self, parsed: dict, collected_text: list[str], tracked_files: list[Path]
    ) -> AsyncGenerator[dict, None]:
        """将解析后的单行 JSON 转为 yield 消息。"""
        msg_type = parsed.get("_msg_type", "")

        if msg_type == "assistant":
            text = parsed.get("_text", "")
            if text:
                collected_text.append(text)
                yield {"type": "log", "message": text, "timestamp": self._timestamp()}
            for tc in parsed.get("_tool_chunks", []):
                yield {"type": "log", "message": tc, "timestamp": self._timestamp()}
            for tu in parsed.get("_tool_uses", []):
                if tu.get("name") == "Write":
                    fp = tu.get("input", {}).get("file_path", "")
                    if fp:
                        tracked_files.append(Path(fp))

        elif msg_type == "result":
            text = parsed.get("_text", "")
            is_error = parsed.get("is_error", False)
            if is_error:
                yield {
                    "type": "error",
                    "message": text or "Hermes CLI 执行出错",
                    "timestamp": self._timestamp(),
                }
            elif text:
                yield {"type": "text", "message": text, "timestamp": self._timestamp()}

        elif msg_type == "text":
            text = parsed.get("_text", "")
            if text:
                collected_text.append(text)
                yield {"type": "text", "message": text, "timestamp": self._timestamp()}

    def _parse_output_line(self, line: str) -> dict | None:
        """解析 hermes --json 输出行。

        支持格式：
        1. {"type": "assistant", "message": {"content": [...]}}  — 类 Claude Code stream-json
        2. {"type": "result", "result": "..."}
        3. {"role": "assistant", "content": "..."}  — OpenAI 兼容格式
        4. 纯文本（非 JSON）→ 当作 assistant text
        """
        # 尝试 JSON 解析
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            # 纯文本行
            text = line.strip()
            if text:
                return {"_msg_type": "text", "_text": text}
            return None

        # ── OpenAI 兼容格式（hermes 使用 LiteLLM，可能返回 OpenAI 格式） ──
        if "choices" in data:
            choices = data.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    return {"_msg_type": "text", "_text": content}
            return None

        # ── 类 Claude Code stream-json 格式 ──
        msg_type = data.get("type", "")

        if msg_type == "assistant":
            message = data.get("message", {})
            content_list = message.get("content", [])
            chunks = []
            tool_chunks = []
            tool_uses = []
            for item in content_list:
                if item.get("type") == "text":
                    text = item.get("text", "").strip()
                    if text:
                        chunks.append(text)
                elif item.get("type") == "tool_use":
                    tool_name = item.get("name", "unknown")
                    tool_input = item.get("input", {})
                    tool_uses.append({"name": tool_name, "input": tool_input})
                    tool_chunks.append(f"🔧 调用工具: {tool_name}")
                    input_str = json.dumps(tool_input, ensure_ascii=False)
                    if len(input_str) < 200:
                        tool_chunks.append(f"   参数: {input_str}")
            return {
                "_msg_type": "assistant",
                "_text": "\n".join(chunks),
                "_chunks": chunks,
                "_tool_chunks": tool_chunks,
                "_tool_uses": tool_uses,
            }

        if msg_type == "result":
            subtype = data.get("subtype", "")
            is_error = subtype != "success"
            result_text = data.get("result", "")
            if isinstance(result_text, str):
                result_text = result_text[:1000]
            return {
                "_msg_type": "result",
                "_text": result_text,
                "_subtype": subtype,
                "is_error": is_error,
                "duration_ms": data.get("duration_ms", 0),
                "cost_usd": data.get("total_cost_usd", 0),
            }

        # ── 类 OpenAI chat completion chunk（streaming delta） ──
        if "object" in data and "chat.completion.chunk" in str(data.get("object", "")):
            choices = data.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    return {"_msg_type": "text", "_text": content}
            return None

        # ── 包含 role + content 的对象（非流式单条消息） ──
        role = data.get("role", "")
        content = data.get("content", "")
        if role and content:
            if isinstance(content, str):
                if role == "assistant":
                    return {"_msg_type": "text", "_text": content}
                elif role == "tool":
                    return {"_msg_type": "log", "_text": f"📋 工具结果: {content[:500]}"}
            elif isinstance(content, list):
                texts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        texts.append(item.get("text", ""))
                if texts:
                    return {"_msg_type": "text", "_text": "\n".join(texts)}

        # ── 通用兜底：尝试提取任何 text/content/message 字段 ──
        for key in ("text", "content", "message", "output"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return {"_msg_type": "text", "_text": val}

        return None

    # ═══════════════════════════════════════════════════════════════
    # 文件下载
    # ═══════════════════════════════════════════════════════════════

    async def _push_files(
        self,
        collected_text: list[str],
        tracked_files: list[Path],
        task_id: str,
        task_start: float,
        message: str,
    ) -> AsyncGenerator[dict, None]:
        """推送生成的文件下载链接。"""
        from agent.exporter import _BASE_OUTPUT_DIR

        all_text = "\n".join(collected_text)
        declared = self._parse_file_declarations(all_text)

        pushed: set[str] = set()

        if declared:
            for filename, label in declared:
                if filename in pushed:
                    continue
                safe_name = filename.replace("\\", "/").split("/")[-1]
                if not safe_name or safe_name == ".":
                    continue
                candidate = _BASE_OUTPUT_DIR / task_id / safe_name if task_id else _BASE_OUTPUT_DIR / safe_name
                if not candidate.exists():
                    logger.warning(f"Agent 声明了文件但不存在: {safe_name}")
                    continue
                pushed.add(safe_name)
                yield {
                    "type": "download",
                    "message": label,
                    "filename": safe_name,
                    "url": f"/api/download/{task_id}/{safe_name}" if task_id else f"/api/download/{safe_name}",
                    "timestamp": self._timestamp(),
                }

        if not pushed:
            logger.info("Agent 未使用 [FILES] 声明，回退到 Write 工具追踪")
            for fp in tracked_files:
                if fp.suffix.lower() != ".csv":
                    continue
                try:
                    base = _BASE_OUTPUT_DIR.resolve()
                    resolved = fp.resolve()
                    if not str(resolved).startswith(str(base) + os.sep) and resolved != base:
                        continue
                    if not resolved.exists():
                        continue
                    filename = resolved.name
                    if filename in pushed:
                        continue
                    pushed.add(filename)
                    yield {
                        "type": "download",
                        "message": f"CSV 表格（Agent 已生成）",
                        "filename": filename,
                        "url": f"/api/download/{task_id}/{filename}" if task_id else f"/api/download/{filename}",
                        "timestamp": self._timestamp(),
                    }
                except Exception as e:
                    logger.warning(f"文件推送失败 {fp}: {e}")

        if not pushed:
            logger.info("Write 追踪无文件，回退到时间戳扫描")
            for dl in self._detect_downloads(task_id, message, task_start):
                yield dl

    def _parse_file_declarations(self, text: str) -> list[tuple[str, str]]:
        """从 Agent 输出文本中解析 [FILES]...[/FILES] 文件声明块。"""
        results: list[tuple[str, str]] = []
        pattern = r"\[FILES\]\s+(.*?)\[/FILES\]"
        for match in re.finditer(pattern, text, re.DOTALL | re.IGNORECASE):
            for line in match.group(1).strip().split("\n"):
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("//"):
                    continue
                parts = line.split("|", 1)
                filename = parts[0].strip().strip("`").strip('"').strip("'")
                label = parts[1].strip() if len(parts) > 1 else filename
                if filename:
                    results.append((filename, label))
        return results

    def _detect_downloads(
        self, task_id: str = "", message: str = "", after_timestamp: float = 0
    ) -> list[dict]:
        """检测任务执行期间新生成的 CSV 文件。"""
        from agent.exporter import _BASE_OUTPUT_DIR
        import csv as _csv

        results: list[dict] = []
        candidates: list[Path] = []

        if task_id:
            safe_tid = task_id.replace("/", "_").replace("\\", "_")
            task_dir = _BASE_OUTPUT_DIR / safe_tid
            if task_dir.exists():
                for f in task_dir.rglob("*.csv"):
                    try:
                        if f.stat().st_mtime < after_timestamp - 10 or f.stat().st_size < 200:
                            continue
                        candidates.append(f)
                    except OSError:
                        continue

        for f in _BASE_OUTPUT_DIR.glob("*.csv"):
            try:
                if f.stat().st_mtime < after_timestamp - 10 or f.stat().st_size < 200:
                    continue
                candidates.append(f)
            except OSError:
                continue

        if not candidates:
            return results

        pushed_names: set[str] = set()
        for csv_path in candidates:
            csv_name = csv_path.name
            if csv_name in pushed_names:
                continue
            pushed_names.add(csv_name)

            rel = csv_path.relative_to(_BASE_OUTPUT_DIR)
            csv_url = (
                f"/api/download/{csv_name}" if len(rel.parts) == 1
                else f"/api/download/{rel.parts[0]}/{csv_name}"
            )
            results.append({
                "type": "download",
                "message": f"CSV: {csv_name}",
                "filename": csv_name,
                "url": csv_url,
                "timestamp": self._timestamp(),
            })

        return results

    # ═══════════════════════════════════════════════════════════════
    # API 直调（非爬取类问答，跳过 CLI 进程）
    # ═══════════════════════════════════════════════════════════════

    async def _respond_via_api(self, message: str) -> AsyncGenerator[dict, None]:
        """DeepSeek API 直调，流式响应（非爬取任务秒回通道）。"""
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            yield {
                "type": "text",
                "message": "未配置 API Key，无法响应。",
                "timestamp": self._timestamp(),
            }
            yield {"type": "done", "message": "无 API Key", "timestamp": self._timestamp()}
            return

        try:
            from openai import AsyncOpenAI

            if os.environ.get("DEEPSEEK_API_KEY"):
                base_url = "https://api.deepseek.com/v1"
                model = "deepseek-chat"
            else:
                base_url = os.environ.get("OPENAI_BASE_URL") or None
                model = os.environ.get("OPENAI_API_MODEL") or "gpt-4o-mini"

            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            stream = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你是 UniEmail Agent，高校教师邮箱爬取助手。用中文简洁回答。"},
                    {"role": "user", "content": message},
                ],
                max_tokens=2048,
                temperature=0.3,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield {"type": "text", "message": delta.content, "timestamp": self._timestamp()}
            yield {"type": "done", "message": "API 响应完毕", "timestamp": self._timestamp()}
        except Exception as e:
            logger.error(f"API 直调失败: {e}")
            yield {"type": "error", "message": f"API 调用失败: {str(e)[:200]}", "timestamp": self._timestamp()}

    async def _drain_stderr(self, stream: asyncio.StreamReader) -> None:
        """持续消费 stderr，防止管道缓冲区满导致子进程死锁。"""
        try:
            while True:
                chunk = await stream.read(65536)
                if not chunk:
                    break
                self._last_stderr = chunk.decode("utf-8", errors="replace")[-500:]
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════
# HermesOrchestrator — 简报注入 + 委托 HermesAgent + 知识提取
# ═══════════════════════════════════════════════════════════════════

class HermesOrchestrator:
    """Hermes 编排引擎：历史简报注入 → 单次委托 HermesAgent → 后置知识提取。"""

    def __init__(self):
        self._stopped_tasks: set[str] = set()
        self.active_procs: dict[str, asyncio.Task] = {}
        self._agent = HermesAgent()

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def stop_task(self, task_id: str = "") -> bool:
        self._stopped_tasks.add(task_id)
        self._agent.stop_task(task_id)
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
        """从 通用经验 → Mem0 精确搜索 → Mem0 扩展搜索 → Skills 文件，返回结构化 Markdown 简报。"""
        parts: list[str] = []

        # 0. 通用爬取经验
        try:
            tips_path = Path(__file__).resolve().parent.parent / "skills" / "universal_crawling_tips.md"
            if tips_path.exists():
                tips = tips_path.read_text(encoding="utf-8").strip()
                if tips:
                    parts.append(tips)
        except Exception as e:
            logger.warning(f"[Hermes] 通用经验加载失败: {e}")

        # 1. Mem0 精确搜索
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

        # 2. Mem0 语义扩展搜索
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

        # 4. 断点续传检测
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
        """从 agent_output.log 提取 WAF/URL/邮箱规律等经验，写入 Mem0 + skills。"""
        result: dict = {"waf_patterns": [], "url_patterns": [], "email_domains": [], "errors": []}

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

        # 提取 WAF/反爬关键词
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

        # 提取教育域名 URL
        url_pattern = re.findall(r'https?://[^\s<>"\'\]\)]+', content)
        seen_urls: set[str] = set()
        for u in url_pattern:
            if ".edu." in u and u not in seen_urls:
                seen_urls.add(u)
                result["url_patterns"].append(u)
                if len(result["url_patterns"]) >= 20:
                    break

        # 提取邮箱域名分布
        email_pattern = re.findall(
            r'[a-zA-Z0-9._%+-]+@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', content
        )
        domain_counts: dict[str, int] = {}
        for domain in email_pattern:
            if domain.lower() in ("gmail.com", "qq.com", "163.com", "126.com", "outlook.com",
                                   "hotmail.com", "foxmail.com", "sina.com", "aliyun.com"):
                continue
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        result["email_domains"] = sorted(domain_counts.items(), key=lambda x: -x[1])[:10]

        # 提取大学名
        uni_name = ""
        for line in content.split("\n")[:50]:
            m = self._extract_university(line)
            if m:
                uni_name = m
                break

        # 写入 Mem0
        experience_text = self._build_experience_text(uni_name, result)
        if experience_text:
            try:
                ok = save_to_mem0(uni_name or "unknown", task_id, experience_text[:2000])
                if ok:
                    logger.info(f"[Hermes] 经验已写入 Mem0: {uni_name or 'unknown'}")
            except Exception as e:
                logger.warning(f"[Hermes] Mem0 写入失败: {e}")

        # 写入 Skills
        if experience_text and uni_name:
            try:
                self._write_to_skills(task_id, uni_name, experience_text)
            except Exception as e:
                logger.warning(f"[Hermes] Skills 写入失败: {e}")

        # 更新通用经验文件
        self._update_universal_tips(result, uni_name)

        return result

    def _update_universal_tips(self, extracted: dict, university: str) -> None:
        """爬取完成后更新通用经验文件。"""
        tips_path = Path(__file__).resolve().parent.parent / "skills" / "universal_crawling_tips.md"
        try:
            current = tips_path.read_text(encoding="utf-8").strip() if tips_path.exists() else ""
        except Exception:
            current = ""

        new_lines: list[str] = []
        waf_found = [p for p in extracted.get("waf_patterns", []) if any(kw in p.lower()
                      for kw in ["ztrust", "safeline", "cloudflare", "412", "js盾", "5秒盾"])]
        if waf_found:
            for w in waf_found:
                kw = w.strip()[:60]
                if kw not in current:
                    new_lines.append(f"- **WAF 记录**: `{kw}`（来自 {university}）")

        domains = extracted.get("email_domains", [])
        edu_domains = [d for d, c in domains if "edu" in d]
        if edu_domains and "邮箱格式" not in current:
            new_lines.append(f"- **主邮箱域名**: `@{edu_domains[0]}`（来自 {university}）")

        if new_lines:
            prefix = "\n## 新增经验\n\n" if "新增经验" not in current else "\n"
            current += prefix + "\n".join(new_lines) + "\n"

        line_count = len(current.split("\n"))
        if line_count > 300:
            try:
                brief = []
                for line in current.split("\n"):
                    if line.startswith("#") or line.strip() == "":
                        brief.append(line)
                    elif line.strip():
                        if any(kw in line for kw in ["**", "1.", "2.", "3.", "4.", "5.", "6.",
                                                      "7.", "8.", "9.", "10.", "- WAF", "- **主邮箱",
                                                      "## ", "> "]):
                            brief.append(line)
                compressed = "\n".join(brief)
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
        """将提取的经验追加写入 crawl_knowledge.md。"""
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
        """简单问答：委托给 HermesAgent。"""
        try:
            async for log in self._agent.execute_query(message, task_id, task_output_dir):
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
        """编排执行：简报注入 → 单次委托 HermesAgent → 后置知识提取。"""
        self._stopped_tasks.discard(task_id)

        uni_name = intent_result.university_name if intent_result else self._extract_university(message)
        run_id = create_run("hermes_execute", {
            "task_id": task_id,
            "university": uni_name,
            "message": message[:200],
        })

        try:
            # Phase 1: 生成历史简报并注入 prompt
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

            # 附加断点续传指令
            if task_id:
                cp_instruction = (
                    f"\n\n## 📍 断点续传指令\n"
                    f"任务目录: outputs/{task_id}/\n"
                    f"每完成一个学院的爬取，请在 outputs/{task_id}/checkpoint.json 中记录进度。\n"
                    f"格式: {{ \"done_colleges\": [{{\"name\": \"学院名\", \"found\": N, \"emails\": N, \"status\": \"done\"}}], \"total_colleges\": N }}\n"
                    f"后续连接会读取 checkpoint 跳过已完成的学院，不要重复爬取。\n"
                )
                enriched_message += cp_instruction

            # Phase 2: 单次委托 HermesAgent 执行（带超时兜底）
            got_done = False
            try:
                async with asyncio.timeout(3600):
                    async for log in self._agent.execute(enriched_message, task_id, **kwargs):
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
                logger.error(f"[Hermes] HermesAgent 执行异常: {e}")
                yield {
                    "type": "error",
                    "message": f"执行异常: {str(e)[:200]}",
                    "timestamp": self._timestamp(),
                }

            # Phase 3: 后置知识提取
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
