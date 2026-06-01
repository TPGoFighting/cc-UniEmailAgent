"""Claude Code Agent Runtime — 通过子进程调用 claude CLI，智能驱动浏览器任务。"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

MAX_STEPS = 2000
TIMEOUT_SECONDS = 3600
CLAUDE_STARTUP_TIMEOUT = 30

# 爬取策略 system prompt — 注入到用户消息前，指导 Agent 如何深层爬取
CRAWL_STRATEGY_PROMPT = """## 任务指令

爬取高校教师邮箱，按以下层次操作，不可停留在列表页：

### 大学识别
精确提取用户消息中的目标大学全称，不要自行替换或纠正。

### 爬取流程
1. 打开目标大学官网 → 「师资队伍」「教师名录」入口 → 指定学院列表页
2. 从列表页提取每位教师的姓名链接 → 进入个人详情页 → 查找邮箱
3. 忽略导航链接（如「学院概况」「通知公告」），只认含完整姓名的教师条目

### 邮箱规则
- 只提取教师个人邮箱，忽略学院公共邮箱（webmaster、wxyxz 等）
- 反爬恢复：`xxx[at]xxx.com` → `xxx@xxx.com`
- 无邮箱的标记为「无邮箱」

### CSV 字段
姓名、邮箱、学院、职称、主页链接

### 关键要点
- 必须进个人详情页才有邮箱，列表页没有
- 文件名：`大学名_教师邮箱_时间戳.csv`，保存到 {{OUTPUT_DIR}}
- 输出目录已由系统创建，直接使用即可，无需 mkdir
- 遇到反爬或失败继续下一个，不要重试同一页面超过 2 次

### 📁 文件分享
任务完成时用以下格式列出下载文件（只有列出的才会显示下载链接）：
[FILES]
文件名.csv | 简短描述
[/FILES]

以下是要爬取的具体任务："""


class ClaudeAgent:
    """Claude Code Agent 包装器。

    通过 asyncio 子进程调用 `claude -p --output-format stream-json`，
    解析流式 JSON 输出，实时推送日志。

    如果 claude CLI 不可用，自动降级到 PlaywrightAgent。
    """

    def __init__(self):
        self._last_stderr = ""
        self.active_procs = {}
        self._check_claude()

    def _check_claude(self) -> bool:
        import shutil

        path = shutil.which("claude")
        if not path:
            logger.warning("claude CLI 未找到，将使用回退模式")
            return False
        logger.info(f"claude CLI 已就绪: {path}")
        return True

    def stop_task(self, task_id: str) -> bool:
        """终止正在运行的任务子进程。"""
        proc = self.active_procs.pop(task_id, None)
        if proc:
            try:
                proc.kill()
                logger.info(f"成功终止 Task {task_id} 的子进程")
                return True
            except Exception as e:
                logger.error(f"终止 Task {task_id} 的子进程失败: {e}")
        return False

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    async def execute(
        self,
        message: str,
        task_id: str = "",
        is_continuation: bool = False,
        is_crawl_session: bool = True,
        current_user_message: str | None = None
    ) -> AsyncGenerator[dict, None]:
        """执行任务。先尝试 Claude Code，失败则回退到 Playwright。

        task_id 用于任务隔离：输出文件写入 outputs/{task_id}/ 子目录。
        is_continuation 为 True 时跳过爬取策略注入（上下文已由 main.py 构建）。"""
        # 如果不是爬取任务，直接进行智能分流（免拉起 CLI 进程以达到毫秒级响应）
        if not is_crawl_session:
            eval_msg = current_user_message or message
            has_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
            if has_key:
                async for log in self._respond_conversational(eval_msg):
                    yield log
                return
            else:
                # 无 Key 时，先发一条友好的秒回优化提示，然后自动降级使用 Claude CLI 获取真实回答
                yield {
                    "type": "text",
                    "message": "💡 **提示**：检测到当前尚未配置 `DEEPSEEK_API_KEY`。系统已自动为你降级为 Claude CLI 流程（冷启动及索引需要约 10 秒）。\n\n*   **秒回优化建议**：在 `backend/.env` 中配置 `DEEPSEEK_API_KEY` 环境变量即可彻底激活 DeepSeek 毫秒级流式秒回通道！\n\n---\n\n正在为你生成回答...\n",
                    "timestamp": self._timestamp()
                }

        try:
            async for log in self._run_claude(message, task_id, is_continuation):
                yield log
        except Exception as e:
            import traceback as _tb
            err_detail = f"{type(e).__name__}: {str(e)[:200]}"
            tb_lines = _tb.format_exc().replace("\n", " | ")
            logger.warning(f"V2 Claude Code 执行失败: {err_detail} || TRACEBACK: {tb_lines}")

            # 仅爬取任务才回退到 Playwright，追问/普通问答不回退
            if is_crawl_session and not is_continuation:
                yield {
                    "type": "log",
                    "message": f"V2 Claude Code 不可用（{err_detail}），切换到内置浏览器 Agent",
                    "timestamp": self._timestamp(),
                }
                from agent.playwright_agent import PlaywrightAgent
                fallback = PlaywrightAgent()
                try:
                    async for log in fallback.execute(message, task_id):
                        yield log
                except Exception as pe:
                    logger.error(f"V2 Playwright 回退也失败: {type(pe).__name__}: {str(pe)[:200]}")
                    yield {
                        "type": "error",
                        "message": f"V2 Playwright 浏览器 Agent 也执行失败: {type(pe).__name__}: {str(pe)[:200]}",
                        "timestamp": self._timestamp(),
                    }
            else:
                yield {
                    "type": "error",
                    "message": f"V2 Claude Code 执行失败（{err_detail}）。这不是爬取任务，请检查 claude CLI 是否正常工作。",
                    "timestamp": self._timestamp(),
                }

    async def _is_crawl_task(self, message: str) -> bool:
        """使用 DeepSeek 大模型对用户意图进行精准分类，判定是否为爬取/数据采集类任务。
        
        若无 API 密钥，回退到本地关键词硬匹配规则，保障系统鲁棒性。
        """
        import os
        import json
        
        # 1. 尝试调用 DeepSeek API 进行意图识别
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if api_key:
            try:
                import openai
                from openai import AsyncOpenAI
                
                # 配置 Client，支持 DeepSeek 官方和 OpenAI 兼容代理
                if os.environ.get("DEEPSEEK_API_KEY"):
                    base_url = "https://api.deepseek.com/v1"
                    model = "deepseek-chat"
                else:
                    base_url = os.environ.get("OPENAI_BASE_URL") or None
                    model = os.environ.get("OPENAI_API_MODEL") or ("deepseek-chat" if base_url and "deepseek" in base_url else "gpt-4o-mini")
                
                client = AsyncOpenAI(api_key=api_key, base_url=base_url)
                
                system_prompt = (
                    "你是一个精准的任务意图分类器。请判断用户输入的请求是否是关于高校教师邮箱抓取、"
                    "师资队伍信息采集、网页邮箱抓取、爬虫提取等数据采集或批量清洗任务。\n"
                    "请仅回复 CRAWL（若是爬虫/抓取/采集/提取任务）或 CHAT（若是日常闲聊、通用问答、代码解释或系统配置类普通会话）。\n"
                    "绝对不能回复除 CRAWL 和 CHAT 以外的任何其他内容或标点符号！"
                )
                
                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message}
                    ],
                    max_tokens=5,
                    temperature=0.0
                )
                
                result = response.choices[0].message.content.strip().upper()
                logger.info(f"[Intent Classifier] Model {model} classified message intent: {result}")
                if "CRAWL" in result:
                    return True
                if "CHAT" in result:
                    return False
            except Exception as e:
                logger.warning(f"[Intent Classifier] DeepSeek 意图识别异常（将回退本地规则）: {e}")
                
        # 2. 兜底策略：本地关键词硬匹配规则
        keywords = [
            "抓取", "爬取", "爬虫", "邮箱", "教师",
            "crawl", "scrape", "email", "faculty", "teacher", "学院",
        ]
        lower = message.lower()
        hits = sum(1 for kw in keywords if kw in lower)
        # 强信号多词短语直接判定
        combos = ["教师邮箱", "crawl email", "scrape email"]
        if any(c in lower for c in combos):
            return True
        return hits >= 2

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

    def _start_subprocess_thread(
        self, cmd: list[str], env: dict, queue: asyncio.Queue, task_id: str
    ) -> None:
        """Windows 兼容：在后台线程启动 subprocess.Popen，stdout 行写入 asyncio.Queue。

        调用方通过 queue 获取已解码的 stdout 行，每行为 {"_type": "line", "data": str}。"""
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
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    startupinfo=si,
                )
                self.active_procs[task_id] = proc

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
                            pass  # 队列满了丢弃（极端情况）

                proc.wait()
                stderr_thread.join(timeout=2)

                if proc.returncode != 0:
                    err = getattr(self, "_last_stderr", "")
                    logger.warning(f"claude 进程退出码 {proc.returncode}: {err[-300:]}")
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

    async def _process_stream(
        self,
        process,
        task_id: str,
        task_start: float,
        message: str,
    ) -> AsyncGenerator[dict, None]:
        """处理子进程的 stdout 流，提取 Claude Code 输出并推送下载文件。

        process 可以是 asyncio.subprocess.Process 或 asyncio.Queue（线程方案）。"""
        import asyncio

        is_threaded = isinstance(process, asyncio.Queue)

        if not is_threaded:
            try:
                process.stdout._limit = 10 * 1024 * 1024  # 10MB
            except AttributeError:
                pass
            stderr_task = asyncio.create_task(self._drain_stderr(process.stderr))

        step_count = 0
        has_output = False
        tracked_files: list[Path] = []
        collected_text: list[str] = []

        should_stop = False

        async def _handle_line(line: str):
            nonlocal step_count, has_output, should_stop
            step_count += 1
            if step_count > MAX_STEPS:
                if not is_threaded:
                    process.kill()
                should_stop = True
                yield {
                    "type": "log",
                    "message": f"达到最大步数限制 ({MAX_STEPS})，任务已终止",
                    "timestamp": self._timestamp(),
                }
                return

            parsed = self._parse_stream_line(line)
            if parsed:
                for tu in parsed.get("_tool_uses", []):
                    if tu.get("name") == "Write":
                        fp = tu.get("input", {}).get("file_path", "")
                        if fp:
                            tracked_files.append(Path(fp))

                msg_type = parsed.get("_msg_type", "")
                if msg_type == "assistant":
                    for chunk in parsed.get("_chunks", []):
                        collected_text.append(chunk)
                        has_output = True
                        yield {
                            "type": "log",
                            "message": chunk,
                            "timestamp": self._timestamp(),
                        }
                elif msg_type == "result":
                    has_output = True
                    if parsed.get("is_error"):
                        yield {
                            "type": "error",
                            "message": parsed.get("_text", "Claude Code 执行出错"),
                            "timestamp": self._timestamp(),
                        }
                    else:
                        text = parsed.get("_text", "")
                        # 去重：result 的文本通常与 assistant 已输出的 content 相同
                        if text and text not in collected_text:
                            collected_text.append(text)
                            yield {
                                "type": "log",
                                "message": text,
                                "timestamp": self._timestamp(),
                            }
                elif msg_type == "system":
                    pass

        try:
            if is_threaded:
                while True:
                    msg = await process.get()
                    logger.info("[SUBDEBUG] 收到队列消息 _type=%s", msg.get("_type", "?"))
                    if msg["_type"] == "line":
                        line_preview = msg["data"][:100] if isinstance(msg.get("data"), str) else "?"
                        logger.info("[SUBDEBUG] 处理行: %s", line_preview)
                        async for log in _handle_line(msg["data"]):
                            yield log
                        if should_stop:
                            logger.info("[SUBDEBUG] 达到最大步数，停止处理")
                            break
                    elif msg["_type"] == "done":
                        logger.info("[SUBDEBUG] 收到线程完成信号")
                        break
            else:
                async for raw_line in process.stdout:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    async for log in _handle_line(line):
                        yield log
                    if should_stop:
                        break

                await asyncio.wait_for(process.wait(), timeout=10)

        except asyncio.TimeoutError:
            if not is_threaded:
                process.kill()
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

        if not has_output:
            err_text = getattr(self, "_last_stderr", "无 stderr 输出")
            raise RuntimeError(f"Claude Code 无输出: {err_text}")

        # ── 推送下载文件 ──
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
                if task_id:
                    candidate = _BASE_OUTPUT_DIR / task_id / safe_name
                else:
                    candidate = _BASE_OUTPUT_DIR / safe_name
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
                logger.info(f"[FILES] 声明推送: {safe_name} ({label})")

        if not pushed:
            logger.info("Agent 未使用 [FILES] 声明，回退到 Write 工具追踪")
            for fp in tracked_files:
                if fp.suffix.lower() not in (".csv", ".xlsx"):
                    continue
                if fp.name.startswith(".") or fp.suffix == ".tmp":
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
                    fmt_label = {"csv": "CSV 表格", "xlsx": "Excel 表格"}
                    label = fmt_label.get(fp.suffix.lower(), fp.suffix.lower())
                    yield {
                        "type": "download",
                        "message": f"{label}（Agent 已生成）",
                        "filename": filename,
                        "url": f"/api/download/{task_id}/{filename}" if task_id else f"/api/download/{filename}",
                        "timestamp": self._timestamp(),
                    }
                    logger.info(f"Agent Write 追踪推送: {filename}")
                except Exception as e:
                    logger.warning(f"文件推送失败 {fp}: {e}")

        if not pushed:
            logger.info("Write 追踪无文件，回退到时间戳扫描")
            for dl in self._detect_downloads(task_id, message, task_start):
                yield dl

        yield {
            "type": "done",
            "message": "Agent 任务执行完毕",
            "timestamp": self._timestamp(),
        }

    async def _run_claude(
        self, message: str, task_id: str = "", is_continuation: bool = False
    ) -> AsyncGenerator[dict, None]:
        """通过子进程运行 claude -p。is_continuation=True 时跳过爬取策略注入。"""
        import shutil

        if not shutil.which("claude"):
            raise RuntimeError("claude CLI 未安装")

        # 爬取任务自动注入策略 prompt（追问时跳过，上下文已由 main.py 构建）
        if await self._is_crawl_task(message) and not is_continuation:
            output_dir = f"outputs/{task_id}" if task_id else "outputs"
            prompt = CRAWL_STRATEGY_PROMPT.replace("{{OUTPUT_DIR}}", output_dir) + "\n" + message
            logger.info("检测到爬取任务，已注入爬取策略 prompt")
        else:
            prompt = message

        cmd = [
            "claude",
            "-p", prompt,
            "--output-format", "stream-json",
            "--verbose",
            "--no-session-persistence",
            "--permission-mode", "bypassPermissions",
            "--max-budget-usd", "20.0",
        ]

        env = os.environ.copy()

        # 记录任务启动时间戳，供后续文件检测隔离旧文件
        task_start = time.time()

        # 调试：记录事件循环信息
        try:
            _loop = asyncio.get_running_loop()
            logger.info(f"事件循环类型: {type(_loop).__name__}, "
                        f"has_subprocess_exec={hasattr(_loop, 'subprocess_exec')}, "
                        f"policy={type(asyncio.get_event_loop_policy()).__name__}")
        except Exception:
            pass

        # Windows 上 SelectorEventLoop 不支持 create_subprocess_exec，
        # 使用线程 + subprocess.Popen + asyncio.Queue 桥接方案
        if sys.platform == "win32":
            queue = asyncio.Queue()
            self._start_subprocess_thread(cmd, env, queue, task_id)
            async for log in self._process_stream(queue, task_id, task_start, message):
                yield log
            return

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            self.active_procs[task_id] = process
        except NotImplementedError as nie:
            logger.warning(f"create_subprocess_exec 不可用，回退线程方案: {nie}")
            queue = asyncio.Queue()
            self._start_subprocess_thread(cmd, env, queue, task_id)
            async for log in self._process_stream(queue, task_id, task_start, message):
                yield log
            return
        except Exception as proc_err:
            import traceback as _tb3
            _detail2 = _tb3.format_exc()
            logger.error(f"子进程启动异常 详细: {_detail2}")
            raise RuntimeError(f"无法启动 claude 子进程: {type(proc_err).__name__}: {str(proc_err)[:200]}") from proc_err

        async for log in self._process_stream(process, task_id, task_start, message):
            yield log

    def _parse_file_declarations(self, text: str) -> list[tuple[str, str]]:
        """从 Agent 输出文本中解析 [FILES]...[/FILES] 文件声明块。

        格式：每行 `文件名 | 简短描述`
        返回 [(filename, label), ...] 列表。"""
        import re as _re

        results: list[tuple[str, str]] = []
        pattern = r"\[FILES\]\s+(.*?)\[/FILES\]"
        for match in _re.finditer(pattern, text, _re.DOTALL | _re.IGNORECASE):
            for line in match.group(1).strip().split("\n"):
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("//"):
                    continue
                # 格式：filename | label
                parts = line.split("|", 1)
                filename = parts[0].strip().strip("`").strip('"').strip("'")
                label = parts[1].strip() if len(parts) > 1 else filename
                if filename:
                    results.append((filename, label))
        return results

    def _detect_downloads(
        self, task_id: str = "", message: str = "", after_timestamp: float = 0
    ) -> list[dict]:
        """检测任务执行期间新生成的 CSV 文件，推送 CSV + XLSX 下载。

        隔离策略：
        1. 递归扫描 outputs/ 下所有 CSV（不限目录，claude CLI 可能自建目录）
        2. 只认 mtime > after_timestamp 的文件（杜绝旧残留）
        3. 按大学名称匹配度 + 数据行数评分，选取最佳
        """
        from agent.exporter import export_all, _BASE_OUTPUT_DIR
        from agent.cleaner import clean_records
        import csv as _csv
        import re as _re

        results: list[dict] = []

        # ── 递归收集所有 CSV ──
        candidates: list[Path] = []
        for f in _BASE_OUTPUT_DIR.rglob("*.csv"):
            try:
                # 增加 10 秒时间戳差值容差，杜绝不同操作系统/文件系统精度或轻微时钟偏移引起的新文件漏检
                if f.stat().st_mtime < after_timestamp - 10 or f.stat().st_size < 200:
                    continue
                
                # 任务隔离强校验：如果文件处于其他任务子目录下，则进行过滤排除，防止跨任务数据交叉污染
                if task_id:
                    safe_tid = task_id.replace("/", "_").replace("\\", "_")
                    try:
                        parent_parts = f.relative_to(_BASE_OUTPUT_DIR).parts
                        if len(parent_parts) > 1:
                            subfolder = parent_parts[0]
                            if subfolder != safe_tid:
                                continue
                    except ValueError:
                        continue
                
                candidates.append(f)
            except OSError:
                continue

        if not candidates:
            logger.info("任务期间未生成新的 CSV 文件")
            return results

        logger.info(
            f"发现 {len(candidates)} 个新 CSV: {[c.name for c in candidates]}"
        )

        # ── 从用户消息提取目标大学名称 ──
        target_uni = ""
        if message:
            m = _re.search(r"([一-鿿]{2,4}(?:大学|学院))", message)
            if m:
                target_uni = m.group(1)

        # ── 评分：匹配度 + 数据行数 ──
        def _score_file(f: Path) -> tuple:
            # 大学名称匹配
            uni_score = 0
            if target_uni:
                if target_uni in f.stem:
                    uni_score = 100
                else:
                    for i in range(len(target_uni), 1, -1):
                        if target_uni[:i] in f.stem:
                            uni_score = i
                            break
            # 数据行数
            rows = 0
            try:
                with open(f, "r", encoding="utf-8-sig") as fp:
                    reader = _csv.reader(fp)
                    next(reader, None)  # 跳过表头
                    for row in reader:
                        if row and any(cell.strip() for cell in row):
                            rows += 1
            except Exception:
                pass
            return (uni_score, rows, f.stat().st_size)

        scored = [(_score_file(f), f) for f in candidates]
        scored.sort(key=lambda x: x[0], reverse=True)

        # ── 推送所有有效的新 CSV 文件（不只是最佳的一个） ──
        pushed_names: set[str] = set()
        for score_val, csv_path in scored:
            if score_val[1] == 0:  # 无数据行，跳过
                continue

            csv_name = csv_path.name
            if csv_name in pushed_names:
                continue
            pushed_names.add(csv_name)

            # 根据文件实际位置生成正确的下载 URL
            rel = csv_path.relative_to(_BASE_OUTPUT_DIR)
            if len(rel.parts) == 1:
                csv_url = f"/api/download/{csv_name}"
            else:
                csv_url = f"/api/download/{rel.parts[0]}/{csv_name}"

            results.append({
                "type": "download",
                "message": f"CSV: {csv_name}",
                "filename": csv_name,
                "url": csv_url,
                "timestamp": self._timestamp(),
            })

            # 检查同名的 XLSX 文件是否已存在
            xlsx_path = csv_path.with_suffix(".xlsx")
            if xlsx_path.exists() and xlsx_path.stat().st_size > 0:
                xlsx_name = xlsx_path.name
                # XLSX URL 与 CSV 使用相同的前缀路径
                xlsx_url = csv_url.rsplit("/", 1)[0] + "/" + xlsx_name
                results.append({
                    "type": "download",
                    "message": f"XLSX: {xlsx_name}",
                    "filename": xlsx_name,
                    "url": xlsx_url,
                    "timestamp": self._timestamp(),
                })

            logger.info(f"推送下载: {csv_name} (行数={score_val[1]})")

        if not results:
            logger.warning("新 CSV 文件无有效数据行")
        return results

    def _parse_stream_line(self, line: str) -> dict | None:
        """解析 stream-json 行，提取可展示的文本片段。"""
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            return None

        msg_type = data.get("type", "")

        # assistant 消息
        if msg_type == "assistant":
            message = data.get("message", {})
            content_list = message.get("content", [])
            chunks = []
            tool_uses = []  # 收集本条消息中的工具调用信息
            for item in content_list:
                if item.get("type") == "text":
                    text = item.get("text", "").strip()
                    if text:
                        chunks.append(text)
                elif item.get("type") == "tool_use":
                    tool_name = item.get("name", "unknown")
                    tool_input = item.get("input", {})
                    tool_uses.append({"name": tool_name, "input": tool_input})
                    chunks.append(f"🔧 调用工具: {tool_name}")
                    input_str = json.dumps(tool_input, ensure_ascii=False)
                    if len(input_str) < 200:
                        chunks.append(f"   参数: {input_str}")

            return {"_msg_type": "assistant", "_chunks": chunks, "_tool_uses": tool_uses}

        # tool_result
        if msg_type == "user" and data.get("message", {}).get("role") == "user":
            content_list = data.get("message", {}).get("content", [])
            for item in content_list:
                if item.get("type") == "tool_result":
                    result_text = item.get("content", "")
                    if isinstance(result_text, list):
                        result_text = " ".join(
                            r.get("text", "") for r in result_text if isinstance(r, dict)
                        )
                    if result_text:
                        text = str(result_text)
                        # 超大结果（如文件内容）只显示摘要
                        if len(text) > 500:
                            text = text[:200] + f"\n... (共 {len(text)} 字符，已截断)"
                        return {
                            "_msg_type": "assistant",
                            "_chunks": [f"📋 结果: {text}"],
                        }
            return None

        # 最终结果
        if msg_type == "result":
            subtype = data.get("subtype", "")
            is_error = subtype != "success"
            result_text = data.get("result", "")
            duration = data.get("duration_ms", 0)
            cost = data.get("total_cost_usd", 0)

            # 结果可能很长，截断
            if isinstance(result_text, str):
                result_text = result_text[:1000]

            return {
                "_msg_type": "result",
                "_text": result_text,
                "is_error": is_error,
                "duration_ms": duration,
                "cost_usd": cost,
            }

        # 系统消息
        if msg_type == "system":
            return {
                "_msg_type": "system",
                "subtype": data.get("subtype", ""),
                "model": data.get("model", ""),
            }

        return None

    async def _respond_conversational(self, message: str) -> AsyncGenerator[dict, None]:
        """轻量级直接 API 响应非爬取类日常会话，避免拉起 CLI 进程。
        
        如果配置了 API Key，直接请求大模型 API，否则使用本地规则响应常见问答。
        """
        import os

        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

        # 有 API Key 时优先走大模型，仅无 Key 时使用本地规则兜底
        if not api_key:
            lower_msg = message.strip().lower()
        
            # 1. 你好等问候
            if any(x in lower_msg for x in ["你好", "hello", "hi", "hey"]):
                yield {
                    "type": "text",
                    "message": "你好！我是 **UniEmail Agent**。\n\n我是一个专为学术界和高校设计的教师邮箱自动抓取与分析助手。我可以帮你自动爬取各高校官网的教师邮箱，并支持导出 CSV/XLSX 等多种格式。\n\n你可以对我说：“帮我抓取南京大学计算机学院的教师邮箱”，或者问我高校抓取的规则与支持的学校！",
                    "timestamp": self._timestamp()
                }
                yield {
                    "type": "done",
                    "message": "已完成本地秒回响应",
                    "timestamp": self._timestamp()
                }
                return
            
            # 2. 你是谁/自我介绍
            if any(x in lower_msg for x in ["你是谁", "介绍", "功能", "who are you"]):
                yield {
                    "type": "text",
                    "message": "我是 **UniEmail Agent**！\n\n### 🌟 我的主要功能包括：\n1. **多源多路径爬取**：深度挖掘高校院系「师资队伍」页面，支持个人详情页深度抓取。\n2. **智能数据清洗**：清洗各种复杂的混淆字符（如 `[at]` -> `@`），过滤无效或公共邮箱。\n3. **多格式数据导出**：支持 CSV, Excel (XLSX), Markdown, HTML, PDF, Word (DOCX) 导出。\n4. **任务与文件隔离**：每个任务专属输出目录，防止数据交叉污染。\n5. **全局技能库**：从过往成功的抓取中自动沉淀提取高校官网的最佳 DOM 选择器和反爬经验。\n\n你可以尝试输入高校抓取任务，我会立即为你启动浏览器自动化爬取进程！",
                    "timestamp": self._timestamp()
                }
                yield {
                    "type": "done",
                    "message": "已完成本地秒回响应",
                    "timestamp": self._timestamp()
                }
                return

        # 3. 尝试调用大模型 API (优先使用 DeepSeek，其次是 OpenAI/Anthropic 兼容 fallback)
        if api_key:
            try:
                # 1. 优先使用 DeepSeek 官方通道
                if os.environ.get("DEEPSEEK_API_KEY"):
                    import openai
                    from openai import AsyncOpenAI
                    
                    client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
                    
                    response = await client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[
                            {"role": "system", "content": "You are UniEmail Agent, a helpful assistant specialized in scraping university faculty emails."},
                            {"role": "user", "content": message}
                        ],
                        stream=True
                    )
                    
                    async for chunk in response:
                        content = chunk.choices[0].delta.content or ""
                        if content:
                            yield {
                                "type": "text",
                                "message": content,
                                "timestamp": self._timestamp()
                            }
                    yield {
                        "type": "done",
                        "message": "DeepSeek API 响应完毕",
                        "timestamp": self._timestamp()
                    }
                    return
                # 2. 回退使用 OpenAI (支持中转)
                elif os.environ.get("OPENAI_API_KEY"):
                    import openai
                    from openai import AsyncOpenAI
                    
                    # 自动读取环境变量中的 OPENAI_BASE_URL (如配置了中转或 DeepSeek 中转)
                    base_url = os.environ.get("OPENAI_BASE_URL") or None
                    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
                    
                    # 如果 base_url 含有 deepseek，使用 deepseek-chat，否则使用 gpt-4o-mini
                    model = os.environ.get("OPENAI_API_MODEL") or ("deepseek-chat" if base_url and "deepseek" in base_url else "gpt-4o-mini")
                    
                    response = await client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": "You are UniEmail Agent, a helpful assistant specialized in scraping university faculty emails."},
                            {"role": "user", "content": message}
                        ],
                        stream=True
                    )
                    
                    async for chunk in response:
                        content = chunk.choices[0].delta.content or ""
                        if content:
                            yield {
                                "type": "text",
                                "message": content,
                                "timestamp": self._timestamp()
                            }
                    yield {
                        "type": "done",
                        "message": "OpenAI/DeepSeek-API 响应完毕",
                        "timestamp": self._timestamp()
                    }
                    return
                # 3. 回退使用 Anthropic
                elif os.environ.get("ANTHROPIC_API_KEY"):
                    # 使用 httpx 直接调用 Anthropic API 保证轻量无依赖
                    import httpx
                    headers = {
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    }
                    data = {
                        "model": os.environ.get("ANTHROPIC_API_MODEL") or "claude-3-5-sonnet-latest",
                        "messages": [{"role": "user", "content": message}],
                        "max_tokens": 1024,
                        "stream": True
                    }
                    # 自动读取环境变量中的 ANTHROPIC_BASE_URL (如配置了中转)
                    base_url = os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
                    url = f"{base_url.rstrip('/')}/v1/messages"
                    
                    # 异步 HTTP 流式调用
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        async with client.stream("POST", url, headers=headers, json=data) as r:
                            if r.status_code == 200:
                                async for line in r.aiter_lines():
                                    line = line.strip()
                                    if line.startswith("data:"):
                                        line_data = line[5:].strip()
                                        if line_data == "[DONE]":
                                            break
                                        try:
                                            evt = json.loads(line_data)
                                            if evt.get("type") == "content_block_delta":
                                                delta_text = evt.get("delta", {}).get("text", "")
                                                if delta_text:
                                                    yield {
                                                        "type": "text",
                                                        "message": delta_text,
                                                        "timestamp": self._timestamp()
                                                    }
                                        except Exception:
                                            pass
                                yield {
                                    "type": "done",
                                    "message": "Anthropic API 响应完毕",
                                    "timestamp": self._timestamp()
                                }
                                return
                            else:
                                logger.warning(f"Anthropic API error: {r.status_code}")
            except Exception as e:
                logger.error(f"直接调用大模型 API 异常: {e}")
                # 异常后自动向下执行进入友好提示

        # 4. 无 Key 时的默认优雅反馈
        yield {
            "type": "text",
            "message": "您好！检测到您发送的是日常闲聊/通用问答。由于您当前尚未在环境变量中配置 `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY`，系统目前仅对**高校教师邮箱爬取任务**自动启用全套 Claude Code CLI 流程。\n\n*   **若要直接爬取**：请使用类似于 **“帮我抓取南京大学计算机学院教师邮箱”** 的指令，系统将立即为您拉起自动化浏览器抓取进程。\n*   **若要启用闲聊/通用问答**：建议在运行环境（或 `.env` 文件）中配置 `DEEPSEEK_API_KEY` 环境变量，系统即可自动通过高速轻量的 DeepSeek `deepseek-chat` 大模型 API 实时响应您的普通日常问答，实现秒回体验！",
            "timestamp": self._timestamp()
        }
        yield {
            "type": "done",
            "message": "已完成本地友好提示响应",
            "timestamp": self._timestamp()
        }
