"""UniEmail Agent — FastAPI 后端服务 (Phase 5: 任务隔离 + 持久化 + 分页)"""

import os
import time
from dotenv import load_dotenv
load_dotenv()
import re
import uuid
import json
import asyncio
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from agent.claude_agent import ClaudeAgent
from agent.hermes_agent import HermesOrchestrator
from agent.graph_agent import GraphAgent
from agent.exporter import get_task_dir, cleanup_task_dir, _BASE_OUTPUT_DIR
from agent.history import history
from agent.intent_router import classify_intent, IntentType, IntentResult
from agent.skill_manager import (
    load_skills_prompt,
    reflect_and_save,
    get_data_schema_prompt,
    get_task_isolation_prompt,
)
from agent.memory import search_mem0, save_to_mem0
from agent.data_memory import index_csv_to_memory, search_data, DataMemory
from agent.universities import (
    build_university_response,
    get_university_records,
    parse_table_file,
    resolve_table_path,
    add_table_row,
    update_table_row,
    delete_table_row,
    upload_university_file,
    delete_university_file,
    rename_university_file,
    clean_university_tables,
)
from agent.cleaner import is_valid_person_name, is_valid_email_format, is_admin_email
from agent.guardrails import check_input, check_output, sanitize_output, GUARD_MODE
from agent.evaluator import validate_crawl_output as eval_crawl, save_quality_report as eval_save
from agent.tracing import create_run, end_run, start_span, end_span, get_trace_url
from agent.mailer import (
    build_preview,
    create_send_job,
    detect_smtp_provider,
    export_send_job,
    get_send_job,
    verify_smtp_config,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 降低第三方库的日志噪音，防止控制台刷屏
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("agent.claude_agent").setLevel(logging.WARNING)

# Agent 选择策略（优先级：GRAPH_AGENT > Hermes > Claude）
# 可通过环境变量 GRAPH_AGENT_ENABLED=true 启用 LangGraph 状态机模式
try:
    import shutil
    if os.environ.get("GRAPH_AGENT_ENABLED", "").lower() in ("true", "1", "yes"):
        agent = GraphAgent()
        logger.info("使用 GraphAgent（LangGraph 状态机）")
    elif shutil.which("hermes"):
        agent = HermesOrchestrator()
        logger.info("使用 Hermes Agent（智能引擎）")
    else:
        agent = ClaudeAgent()
        logger.info("Hermes 未安装，使用 Claude Agent")
except Exception:
    agent = ClaudeAgent()
    logger.info("使用 Claude Agent（回退）")

# 正在执行 Agent 的任务追踪（task_id -> asyncio.Task），防止重复执行
_running_agent_tasks: dict[str, asyncio.Task] = {}
_running_agent_info: dict[str, dict] = {}
# Phase 1: 任务启动时间记录（用于计算耗时）
_task_start_times: dict[str, float] = {}
_trace_runs: dict[str, str] = {}  # task_id -> LangSmith run_id


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时清空 in-memory 状态（防止旧进程的残留数据）
    _running_agent_tasks.clear()
    _running_agent_info.clear()
    _task_start_times.clear()
    _trace_runs.clear()
    logger.info("UniEmail Agent 后端启动（状态已清空）")
    yield
    logger.info("UniEmail Agent 后端关闭")


app = FastAPI(title="UniEmail Agent", version="0.2.0", lifespan=lifespan)

cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    task_id: str | None = None


class ChatResponse(BaseModel):
    task_id: str


class ClassifyRequest(BaseModel):
    message: str


class RenameRequest(BaseModel):
    title: str


class SmtpDetectRequest(BaseModel):
    email: str = ""


class SmtpVerifyRequest(BaseModel):
    user: str
    password: str
    host: str | None = None
    port: int | None = None
    secure: bool | None = None
    fromName: str | None = None


class MailPreviewRequest(BaseModel):
    rows: list[dict]
    subjectTemplate: str
    bodyTemplate: str
    limit: int = 10


class MailSendRequest(BaseModel):
    rows: list[dict]
    subjectTemplate: str
    bodyTemplate: str
    smtpSessionId: str
    settings: dict = {}
    previewConfirmed: bool = False
    confirmed: bool = False
    highVolumeConfirmed: bool = False

class TerminateRequest(BaseModel):
    task_id: str


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/history")
async def get_history():
    tasks_list = history.get_all()
    return {"tasks": tasks_list}


@app.get("/api/history/search")
async def search_history(q: str = ""):
    results = history.search(q)
    return {"tasks": results}


@app.get("/api/history/{task_id}")
async def get_history_task(
    task_id: str,
    limit: int = Query(default=0, ge=0, description="return message count limit, 0=all"),
    offset: int = Query(default=0, ge=0, description="messages to skip"),
):
    task = history.get(task_id)
    if task is None:
        return {"error": "task not found"}

    messages = task.get("messages", [])
    total = len(messages)

    if offset > 0 or limit > 0:
        page = messages[offset:offset + limit] if limit > 0 else messages[offset:]
    else:
        page = messages

    normalized = []
    for m in page:
        if "role" not in m:
            msg_type = m.get("type", "log")
            role_map = {"log": "log", "download": "download", "error": "agent", "done": "agent", "text": "text"}
            m["role"] = role_map.get(msg_type, "log")
            if "message" in m and "content" not in m:
                m["content"] = m["message"]
        normalized.append(m)

    return {"task": task, "messages": normalized, "total": total, "limit": limit, "offset": offset}


@app.patch("/api/history/{task_id}/rename")
async def rename_task(task_id: str, req: RenameRequest):
    task = history.rename_task(task_id, req.title)
    if task is None:
        return {"error": "task not found"}
    return {"ok": True, "task": task}


@app.patch("/api/history/{task_id}/pin")
async def pin_task(task_id: str):
    task = history.toggle_pin(task_id)
    if task is None:
        return {"error": "task not found"}
    return {"ok": True, "pinned": task.get("pinned", False)}


@app.delete("/api/history/{task_id}")
async def delete_task(task_id: str):
    # 如果有正在运行的 Agent，先终止
    if hasattr(agent, "stop_task"):
        agent.stop_task(task_id)
    if task_id in _running_agent_tasks:
        coro_task = _running_agent_tasks.pop(task_id, None)
        if coro_task and not coro_task.done():
            coro_task.cancel()
    _running_agent_info.pop(task_id, None)
    cleanup_task_dir(task_id)
    ok = history.delete_task(task_id)
    return {"ok": ok}


@app.get("/api/agent/active")
async def get_active_agents():
    return {"active_tasks": list(_running_agent_info.values())}


@app.post("/api/agent/terminate")
async def terminate_agent(req: TerminateRequest):
    task_id = req.task_id
    terminated = False

    # 1. 终止 Agent 进程中的外部子进程
    if hasattr(agent, "stop_task"):
        terminated = agent.stop_task(task_id)

    # 2. 取消 websocket 和协程任务
    if task_id in _running_agent_tasks:
        coro_task = _running_agent_tasks[task_id]
        if not coro_task.done():
            coro_task.cancel()
            terminated = True

    # 3. 更新历史记录中的状态为失败，并添加中断系统消息
    if terminated:
        history.update_status(task_id, "failed")
        ts = datetime.now().strftime("%H:%M:%S")
        history.add_message(task_id, {
            "id": f"terminate-{task_id[:8]}-{ts}",
            "role": "agent",
            "content": "任务已被人工强制关闭，后台 Agent 进程已被安全终止以节省资源与额度。",
            "timestamp": ts,
        })
        return {"ok": True, "message": "Task successfully terminated"}
    else:
        return {"ok": False, "message": "Task not running or already finished"}


@app.post("/api/chat", response_model=ChatResponse)
async def create_task(req: ChatRequest):
    task_id = req.task_id or str(uuid.uuid4())
    user_content = req.message or "new task"

    existing = history.get(task_id)
    if existing is None:
        history.create_task(task_id, user_content)
    else:
        history.update_status(task_id, "running")

    history.add_message(task_id, {
        "id": f"user-{task_id[:8]}-{len(existing.get('messages', [])) if existing else 0}",
        "role": "user",
        "content": user_content,
    })

    logger.info(f"task {task_id}: {req.message}")
    return ChatResponse(task_id=task_id)


@app.post("/api/classify")
async def classify_task(req: ClassifyRequest):
    """统一的任务分类端点：返回完整的三路意图分类结果。"""
    result = await classify_intent(req.message, has_existing_data=False, existing_university="")
    return {
        "is_crawl": result.is_crawl,
        "intent": result.intent.value,
        "university": result.university_name,
        "departments": result.target_departments,
        "reason": result.reason,
    }


MIME_MAP = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".md": "text/markdown",
    ".html": "text/html",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _safe_resolve(base: Path, *parts: str) -> Path | None:
    """安全的路径解析，防止路径遍历攻击。"""
    base_resolved = base.resolve(strict=False)
    for part in parts:
        # 拒绝路径分隔符、 . 和 ..
        if "/" in part or "\\" in part or part in (".", "..") or not part:
            return None
    try:
        p = base_resolved
        for part in parts:
            p = (p / part).resolve(strict=False)
        p_str = str(p)
        base_str = str(base_resolved)
        if p_str == base_str:
            return p
        if not p_str.startswith(base_str + os.sep):
            return None
        return p
    except (OSError, ValueError):
        return None


@app.get("/api/download/{task_id}/{filename:path}")
async def download_file_tasked(task_id: str, filename: str):
    if ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    safe_tid = task_id.replace("..", "_")
    base = _BASE_OUTPUT_DIR.resolve()
    filepath = _safe_resolve(base, safe_tid, filename)
    if filepath is None or not filepath.exists():
        # 后备方案：如果任务专属目录下未找到（可能是自定义脚本写到了根目录），尝试在 outputs 根目录下查找该文件
        fallback = _safe_resolve(base, filename)
        if fallback and fallback.exists():
            filepath = fallback
        else:
            raise HTTPException(status_code=404, detail="file not found")
    ext = filepath.suffix.lower()
    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type=MIME_MAP.get(ext, "application/octet-stream"),
    )


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    base = _BASE_OUTPUT_DIR.resolve()
    filepath = _safe_resolve(base, filename)
    if filepath and filepath.exists():
        ext = filepath.suffix.lower()
        return FileResponse(
            path=str(filepath),
            filename=filename,
            media_type=MIME_MAP.get(ext, "application/octet-stream"),
        )
    # 根目录未找到，尝试在所有任务子目录中查找
    for child in base.iterdir():
        if child.is_dir():
            candidate = _safe_resolve(base, child.name, filename)
            if candidate and candidate.exists():
                ext = candidate.suffix.lower()
                return FileResponse(
                    path=str(candidate),
                    filename=filename,
                    media_type=MIME_MAP.get(ext, "application/octet-stream"),
                )
    raise HTTPException(status_code=404, detail="file not found")


SKILLS_DIR = Path(__file__).parent / "skills"


async def _post_task_reflection(task_id: str, task_data: dict, university_name: str) -> None:
    """任务完成后的反思钩子：异步执行，不影响主流程。

    拦截 AI 回复中的 [REFLECTION]...[/REFLECTION] 标签，由后端统一处理持久化。
    """
    try:
        messages = task_data.get("messages", [])

        # 检查最后一条 agent 消息是否包含 [REFLECTION] 标签
        reflection_content = None
        for m in reversed(messages):
            msg_content = m.get("content", "") or m.get("message", "")
            if isinstance(msg_content, str):
                match = re.search(r'\[REFLECTION\](.*?)\[/REFLECTION\]', msg_content, re.DOTALL)
                if match:
                    inner = match.group(1).strip()
                    if inner.lower() == "none" or "无新" in inner:
                        reflection_content = ""  # 标记为无新内容
                    else:
                        reflection_content = inner
                    break

        if reflection_content == "":
            logger.info(f"[Reflection] task {task_id[:8]} AI 标记为无新经验")
            return

        if reflection_content:
            # 有内联反射内容，直接写入
            from agent.skill_manager import atomic_write_reflection
            result = await atomic_write_reflection(task_id, university_name, reflection_content)
            if result:
                logger.info(f"[Reflection] task {task_id[:8]} 内联反思已写入: {result}")
            # Mem0 双写：同步写入持久记忆
            save_to_mem0(university_name, task_id, reflection_content)
            return

        # 无内联标签，走原有 LLM 反思流程
        result = await reflect_and_save(task_id, university_name, messages)
        if result:
            logger.info(f"[Reflection] task {task_id[:8]} 新经验已写入: {result}")
            # Mem0 双写：从 skill 文件中读取刚写入的内容并同步
            _mem0_sync_from_skills(university_name, task_id)
        else:
            logger.info(f"[Reflection] task {task_id[:8]} 无新经验需要记录")
    except Exception as e:
        logger.warning(f"[Reflection] task {task_id[:8]} 反思失败（不影响任务结果）: {e}")


def _mem0_sync_from_skills(university_name: str, task_id: str) -> None:
    """从文件系统技能库读取最新经验，同步写入 Mem0（双写兼容辅助）。"""
    try:
        skill_file = SKILLS_DIR / f"{university_name}_{task_id[:8]}.json"
        if not skill_file.exists():
            return
        data = json.loads(skill_file.read_text(encoding="utf-8"))
        # 优先使用 LLM 反思结果，否则用任务摘要
        experience = data.get("reflection", "")
        if not experience:
            query = data.get("user_query", "")
            files = data.get("files", [])
            if query:
                parts = [f"任务: {query}"]
                if files:
                    parts.append(f"产出文件: {', '.join(files[:5])}")
                experience = " | ".join(parts)
        if experience:
            save_to_mem0(university_name, task_id, experience)
    except Exception:
        pass  # Mem0 写入失败不影响主流程


GLOBAL_SKILLS_FILE = SKILLS_DIR / "global_crawling_rules.md"
CRAWL_KNOWLEDGE_FILE = SKILLS_DIR / "crawl_knowledge.md"

# 全局技能写入锁（保护 global_crawling_rules.md 和 crawl_knowledge.md 的并发写入）
_SKILL_WRITE_LOCK = asyncio.Lock()


async def _update_global_skills(uni_name: str, task_data: dict) -> None:
    if uni_name == "unknown":
        return

    async with _SKILL_WRITE_LOCK:
        # 从历史执行消息中深度挖掘有商业可复用价值的技术资产
        messages = task_data.get("messages", [])
        extracted_urls = set()
        extracted_selectors = set()
        special_tips = []

        for m in messages:
            content = m.get("content", "")
            # 提取 URL
            urls = re.findall(r'https?://[^\s\'"）]+', content)
            for u in urls:
                u_clean = u.rstrip(".,;:，；。)")
                if any(x in u_clean for x in (uni_name, "tsinghua", "nju", "seu", "njust", "njupt", "bupt")):
                    if uni_name == "南京大学" and "njupt" in u_clean:
                        continue
                    if uni_name == "南京邮电大学" and "nju." in u_clean and "njupt" not in u_clean:
                        continue
                    extracted_urls.add(u_clean)

            selectors = re.findall(r'(\.[a-zA-Z0-9_-]{3,20}|#[a-zA-Z0-9_-]{3,20}|frag="[^"]+")', content)
            for s in selectors:
                if s not in (".xlsx", ".csv", ".json", ".html", ".png", ".py", ".md", ".pdf", ".docx"):
                    extracted_selectors.add(s)

            keywords = ["description", "Article_Title", "内联", "反爬", "邮箱规则", "职称", "JS动态", "iframe", "requests", "Playwright"]
            for kw in keywords:
                if kw in content and kw not in special_tips:
                    special_tips.append(kw)

        if not extracted_urls and not extracted_selectors:
            return

        SKILLS_DIR.mkdir(exist_ok=True)
        content_lines = []
        if GLOBAL_SKILLS_FILE.exists():
            try:
                with open(GLOBAL_SKILLS_FILE, "r", encoding="utf-8") as f:
                    content_lines = f.readlines()
            except OSError:
                pass

        if not content_lines:
            content_lines = [
                "# 🌍 全局高校教师邮箱爬取经验知识库 (Global Centralized Crawling Experience)\n",
                "\n",
                "本文件是由所有任务共同维护的全局经验共享文件。每当一个任务成功爬取完毕，"
                "系统会自动从中总结出可复用的最佳实践（包括特定高校官网的最优路径、HTML 选择器特征、反爬绕过方案等），"
                "以供后续新任务在执行前进行参考与学习。\n",
                "\n",
            ]

        full_text = "".join(content_lines)

        school_header = f"## 🏫 {uni_name} 爬取策略与模式"
        school_content = []
        school_content.append(f"{school_header}\n")
        school_content.append(f"*   **最近优化时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        if extracted_urls:
            school_content.append("*   **经验证可用的师资/院系 URL 导航**：\n")
            for u in sorted(extracted_urls):
                school_content.append(f"    *   {u}\n")
        if extracted_selectors:
            school_content.append("*   **关键 HTML 提取特征及 DOM 选择器**：\n")
            for s in sorted(extracted_selectors):
                school_content.append(f"    *   `{s}`\n")
        if special_tips:
            school_content.append(f"*   **智能反爬与信息提取策略发现**：系统验证 `{', '.join(special_tips)}` 模式有特效，请优先延续此类提取策略。\n")
        school_content.append("\n")

        new_school_text = "".join(school_content)

        pattern = rf"## 🏫 {re.escape(uni_name)} 爬取策略与模式.*?(?=\n## 🏫 |\Z)"
        if re.search(pattern, full_text, re.DOTALL):
            updated_text = re.sub(pattern, new_school_text.strip(), full_text, flags=re.DOTALL)
        else:
            updated_text = full_text.rstrip() + "\n\n" + new_school_text

        try:
            _safe_write(GLOBAL_SKILLS_FILE, updated_text.replace(chr(0), ""))
            logger.info(f"Global skills knowledgebase updated for {uni_name}!")
        except OSError as e:
            logger.error(f"Global skills save failed: {e}")


async def _generate_skills(task_id: str, task_data: dict) -> None:
    SKILLS_DIR.mkdir(exist_ok=True)

    # ── 每周清理一次无效 skill：删除 unknown_、_legacy_、_orchestrator_memory_ 前缀的文件，控制总数不超过 30 ──
    try:
        all_skills = sorted(SKILLS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
        # 删除所有 unknown_ 前缀的 JSON（由失败任务产生的无复用价值记录）
        for f in list(all_skills):
            if f.name.startswith("unknown_"):
                f.unlink()
                logger.info(f"清理无效 skill: {f.name}")
        # 删除 _legacy_ 和 _orchestrator_memory_ 前缀的 JSON（历史遗留/系统内部文件）
        for f in list(all_skills):
            if f.name.startswith("_legacy_") or f.name.startswith("_orchestrator_memory_"):
                f.unlink()
                logger.info(f"清理系统内部 skill: {f.name}")
        # 重新读取（清理后重新排序）
        all_skills = sorted(SKILLS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
        if len(all_skills) > 30:
            for f in all_skills[:-30]:  # 保留最新 30 个
                f.unlink()
                logger.info(f"清理过期 skill: {f.name}")
    except Exception as e:
        logger.warning(f"Skill 目录清理异常（不影响流程）: {e}")

    messages = task_data.get("messages", [])
    user_msg = ""
    for m in messages:
        if m.get("role") == "user":
            user_msg = m.get("content", "")
            break

    uni_name = "unknown"
    for m in messages:
        content = m.get("content", "")
        if "大学" in content or "学院" in content:
            import re
            match = re.search(r"([一-鿿]{2,4}(?:大学|学院))", content)
            if match:
                uni_name = match.group(1)
                break

    files = []
    for m in messages:
        if m.get("role") == "download" and m.get("filename"):
            files.append(m.get("filename", ""))

    skill = {
        "task_id": task_id,
        "university": uni_name,
        "user_query": user_msg[:200],
        "files": files,
        "message_count": len(messages),
        "status": task_data.get("status", ""),
        "date": task_data.get("date", ""),
        "extracted_at": datetime.now().isoformat(),
    }

    # 1. 更新全局共享经验文件（Global shared experience file）
    await _update_global_skills(uni_name, task_data)

    # 2. 依然保留隔离专属的元数据 JSON 供系统检索
    skill_file = SKILLS_DIR / f"{uni_name}_{task_id[:8]}.json"
    try:
        with open(skill_file, "w", encoding="utf-8") as f:
            json.dump(skill, f, ensure_ascii=False, indent=2)
        logger.info(f"Skill generated: {skill_file.name}")
    except OSError as e:
        logger.error(f"Skill save failed: {e}")

    # 3. Mem0 双写：同步从消息中提取的关键发现到持久记忆
    _mem0_sync_from_skills(uni_name, task_id)


@app.get("/api/skills")
async def list_skills():
    SKILLS_DIR.mkdir(exist_ok=True)
    skills = []
    for f in sorted(SKILLS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                skills.append(json.load(fp))
        except Exception:
            pass
    return {"skills": skills}


@app.get("/api/universities")
async def list_universities(
    province: str = "",
    tier: str = "",
    q: str = "",
):
    return build_university_response(province=province, tier=tier, q=q)


@app.get("/api/universities/{name}/records")
async def university_records(name: str):
    return get_university_records(name)


@app.get("/api/universities/{name}/table")
async def university_table(
    name: str,
    task_id: str = "",
    file: str = "",
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    q: str = "",
    department: str = "",
    valid_only: bool = False,
):
    path = resolve_table_path(task_id, file)
    if path is None or name not in path.name:
        raise HTTPException(status_code=404, detail="table file not found")
    try:
        return parse_table_file(path, limit=limit, offset=offset, q=q, department=department, valid_only=valid_only)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"table parse failed: {type(exc).__name__}") from exc


@app.post("/api/universities/{name}/files")
async def upload_university_file_route(name: str, file: UploadFile = File(...)):
    """上传文件到高校目录。"""
    content = await file.read()
    try:
        result = upload_university_file(name, content, file.filename or "unnamed")
        return result
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.delete("/api/universities/{name}/files")
async def delete_university_file_route(name: str, task_id: str = "", filename: str = ""):
    """删除高校目录中的文件。"""
    try:
        delete_university_file(task_id, filename)
        return {"ok": True}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/universities/{name}/files")
async def rename_university_file_route(name: str, body: dict):
    """重命名高校目录中的文件。"""
    try:
        rename_university_file(
            body.get("task_id", ""),
            body.get("filename", ""),
            body.get("new_filename", ""),
        )
        return {"ok": True}
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/universities/{name}/table/rows")
async def add_table_row_route(name: str, body: dict):
    """在表格末尾添加新行。"""
    path = resolve_table_path(body.get("task_id", ""), body.get("file", ""))
    if path is None or name not in path.name:
        raise HTTPException(status_code=404, detail="表格文件未找到")
    try:
        return add_table_row(path, body.get("row", {}))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"添加行失败: {exc}")


@app.put("/api/universities/{name}/table/rows/{row_index}")
async def update_table_row_route(name: str, row_index: int, body: dict):
    """更新表格中指定索引的行。"""
    path = resolve_table_path(body.get("task_id", ""), body.get("file", ""))
    if path is None or name not in path.name:
        raise HTTPException(status_code=404, detail="表格文件未找到")
    try:
        return update_table_row(path, row_index, body.get("row", {}))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"更新行失败: {exc}")


@app.delete("/api/universities/{name}/table/rows/{row_index}")
async def delete_table_row_route(name: str, row_index: int, task_id: str = "", file: str = ""):
    """删除表格中指定索引的行。"""
    path = resolve_table_path(task_id, file)
    if path is None or name not in path.name:
        raise HTTPException(status_code=404, detail="表格文件未找到")
    try:
        return delete_table_row(path, row_index)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"删除行失败: {exc}")


@app.post("/api/universities/{name}/clean")
async def clean_university_tables_route(name: str):
    """一键清洗高校所有表格文件：去重、过滤非法姓名、排除公共邮箱。"""
    try:
        result = clean_university_tables(name)
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"清洗失败: {exc}")


@app.post("/api/universities/{name}/export")
async def export_university_table(name: str, body: dict):
    """将高校表格数据导出为指定格式，返回下载 URL。

    body 示例: {"task_id": "...", "file": "...", "formats": ["csv", "xlsx", "md", "html", "pdf", "docx"]}
    """
    from agent.exporter import export_all, _BASE_OUTPUT_DIR, _build_rows
    from agent.universities import resolve_table_path, _read_csv, _read_xlsx

    path = resolve_table_path(body.get("task_id", ""), body.get("file", ""))
    if path is None or name not in path.name:
        raise HTTPException(status_code=404, detail="table file not found")

    formats = body.get("formats", ["xlsx"])
    # 读取表格数据
    if path.suffix.lower() == ".csv":
        _, rows = _read_csv(path)
    elif path.suffix.lower() == ".xlsx":
        _, rows = _read_xlsx(path)
    else:
        raise HTTPException(status_code=400, detail="unsupported file format")

    # 转换 rows 为 export_all 需要的格式
    data = []
    for r in rows:
        data.append({
            "name": r.get("姓名", "") or r.get("name", ""),
            "email": r.get("邮箱", "") or r.get("email", ""),
            "department": r.get("学院", "") or r.get("department", ""),
            "title": r.get("职称", "") or r.get("title", ""),
            "url": r.get("主页链接", "") or r.get("url", ""),
        })

    # 导出到独立目录 __export__{name}_{ts}/
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = name.replace("/", "_").replace("\\", "_")
    export_task_id = f"__export__{safe_name}_{ts}"
    result = export_all(data, name, export_task_id, formats=formats)

    download_urls = {}
    for fmt, filename in result.items():
        download_urls[fmt] = f"/api/download/{export_task_id}/{filename}"

    return {"ok": True, "name": name, "files": download_urls}


@app.post("/api/smtp/detect")
async def smtp_detect(req: SmtpDetectRequest):
    return detect_smtp_provider(req.email)


@app.post("/api/smtp/verify")
async def smtp_verify(req: SmtpVerifyRequest):
    try:
        return verify_smtp_config(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/mail/preview")
async def mail_preview(req: MailPreviewRequest):
    try:
        return build_preview(req.rows, req.subjectTemplate, req.bodyTemplate, req.limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/mail/send")
async def mail_send(req: MailSendRequest):
    try:
        return create_send_job(
            rows=req.rows,
            subject_template=req.subjectTemplate,
            body_template=req.bodyTemplate,
            smtp_session_id=req.smtpSessionId,
            preview_confirmed=req.previewConfirmed,
            confirmed=req.confirmed,
            high_volume_confirmed=req.highVolumeConfirmed,
            settings=req.settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/mail/jobs/{job_id}")
async def mail_job(job_id: str):
    job = get_send_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/api/mail/jobs/{job_id}/export")
async def mail_job_export(job_id: str, format: str = "csv"):
    try:
        filename, payload, media_type = export_send_job(job_id, "xlsx" if format == "xlsx" else "csv")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _load_global_skills() -> str:
    """读取全局共享爬取经验知识库，供注入到 Agent 提示词中。

    返回格式化后的 Markdown 字符串；若文件不存在或为空则返回空字符串。
    优先读取 crawl_knowledge.md，再补充 global_crawling_rules.md。两个文件都完整追加到 prompt。"""
    parts = []

    # 1. 读取 crawl_knowledge.md（标准 skill 格式汇总文件）
    if CRAWL_KNOWLEDGE_FILE.exists():
        try:
            text = CRAWL_KNOWLEDGE_FILE.read_text(encoding="utf-8").strip()
            if text.startswith("---"):
                end = text.find("---", 3)
                if end != -1:
                    text = text[end + 3:].strip()
            if text:
                parts.append(text)
        except OSError:
            pass

    # 2. 读取 global_crawling_rules.md（含踩坑记录、正确流程等）
    if GLOBAL_SKILLS_FILE.exists():
        try:
            text = GLOBAL_SKILLS_FILE.read_text(encoding="utf-8").strip()
            if text:
                parts.append(text)
        except OSError:
            pass

    if not parts:
        return ""

    return (
        "### 📚 全局共享爬取经验库（含历史踩坑记录）\n"
        "以下是系统从过往所有任务中自动提炼的高校爬取经验与踩坑教训，"
        "请在执行本次任务前仔细阅读并严格遵守：\n\n"
        + "\n\n---\n\n".join(parts) + "\n\n"
        "---\n"
    )


def _read_file_preview(file_path: Path, max_rows: int = 20) -> str:
    """读取 CSV/XLSX 文件的前 max_rows 行作为预览，并返回统计信息。"""
    import csv as _csv
    suffix = file_path.suffix.lower()
    preview_lines = []
    total_rows = 0

    try:
        if suffix == ".csv":
            with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = _csv.reader(f)
                for i, row in enumerate(reader):
                    if i == 0:
                        preview_lines.append(f"表头: {' | '.join(row)}")
                    elif i <= max_rows:
                        preview_lines.append(f"  {row[0] if row else '?'}: {' | '.join(row)}")
                    total_rows += 1
        elif suffix == ".xlsx":
            try:
                import openpyxl
                wb = openpyxl.load_workbook(file_path, read_only=True)
                ws = wb.active
                for i, row in enumerate(ws.iter_rows(values_only=True)):
                    vals = [str(v or "") for v in row]
                    if i == 0:
                        preview_lines.append(f"表头: {' | '.join(vals)}")
                    elif i <= max_rows:
                        preview_lines.append(f"  {vals[0] if vals else '?'}: {' | '.join(vals)}")
                    total_rows += 1
                wb.close()
            except ImportError:
                preview_lines.append("(需要安装 openpyxl 才能预览 XLSX)")
    except Exception as e:
        preview_lines.append(f"(读取文件失败: {e})")

    data_rows = max(0, total_rows - 1)  # 减表头
    preview = "\n".join(preview_lines[:max_rows + 1])
    return preview, total_rows, data_rows


def _resolve_file_in_task(task_id: str, filename: str) -> str:
    """查找 task_id 专属目录下是否存在 filename，返回绝对路径字符串或空字符串。"""
    if not task_id or not filename:
        return ""
    safe_tid = task_id.replace("/", "_").replace("\\", "_").replace("..", "_")
    candidate = _BASE_OUTPUT_DIR / safe_tid / filename
    if candidate.exists():
        return str(candidate.resolve())
    # 也在根 outputs 下查找
    root_candidate = _BASE_OUTPUT_DIR / filename
    if root_candidate.exists():
        return str(root_candidate.resolve())
    return ""


def _build_context_prompt(task_data: dict, latest_user_msg: str, task_id: str = "") -> tuple[str, str, bool]:
    messages = task_data.get("messages", [])
    user_msgs = [m for m in messages if m.get("role") == "user"]

    if len(user_msgs) <= 1:
        # 新任务：不在此处注入技能（由 WS handler 统一注入，避免重复）
        prompt = latest_user_msg
        return prompt, latest_user_msg, False

    lines = []
    # 追问场景：全局经验知识由 WS handler 统一注入（避免重复）
    lines += [
        "## 任务上下文（同一任务的后续追问）\n",
        "以下是本任务已完成工作的摘要，请基于此上下文处理当前请求：\n",
    ]

    prev_requests = [m.get("content", "") for m in user_msgs[:-1]]
    if prev_requests:
        lines.append("### 之前的需求")
        for i, req in enumerate(prev_requests, 1):
            lines.append(f"{i}. {req[:200]}")
        lines.append("")

    downloads = [m for m in messages if m.get("role") == "download"]
    files = [d.get("filename", "") for d in downloads if d.get("filename")]
    file_msgs = [m for m in messages if m.get("role") == "file"]
    if files:
        seen = set()
        lines.append("### 已生成的文件")
        for f in files:
            if f not in seen:
                seen.add(f)
                # 尝试获取实际路径
                fp = _resolve_file_in_task(task_id, f)
                path_info = f"（路径: {fp}）" if fp else ""
                lines.append(f"- {f} {path_info}")
        lines.append("")

    if file_msgs:
        lines.append("### 已创建的脚本文件")
        for fm in file_msgs:
            fpath = fm.get("filepath", "")
            lines.append(f"- `{fm.get('filename', '')}`（路径: {fpath}）")
        lines.append(
            "💡 以上脚本文件由之前的任务创建，仍然保存在磁盘上，可以直接用 bash 读取或运行。\n"
        )
        lines.append("")

    # ── 从历史消息中提取关键日志 ──
    log_msgs = [m for m in messages if m.get("role") == "log" and m.get("content")]
    key_logs = []
    import re as _re_log
    for lm in log_msgs[-100:]:  # 只看最近 100 条日志
        content = lm.get("content", "")
        # 提取访问 URL
        urls = _re_log.findall(r'https?://[^\s\'"）\)]+', content)
        for u in urls[:3]:
            key_logs.append(f"访问: {u[:150]}")
        # 提取邮箱数/教师数信息
        if re.search(r'(\d+)\s*个?(?:邮箱|教师|邮件|记录|数据|email)', content, re.I):
            key_logs.append(content[:200])
        # 提取反爬/错误关键词
        if any(kw in content.lower() for kw in ["反爬", "验证码", "ip限制", "超时", "403", "502", "no such", "timeout"]):
            key_logs.append(f"[异常] {content[:150]}")

    if key_logs:
        lines.append("### 爬取过程中的关键日志")
        for kl in key_logs[-10:]:  # 最多 10 条
            lines.append(f"- `{kl}`")
        lines.append("")

    agent_msgs = [m for m in messages if m.get("role") == "agent" and m.get("content")]
    if agent_msgs:
        last = agent_msgs[-1].get("content", "")
        if len(last) > 800:
            last = last[:800].rsplit("\n", 1)[0]
        lines.append("### 上次任务的回复摘要")
        lines.append(last)
        lines.append("")

    # ── 扫描 outputs/{task_id} 下的现有数据文件（failed/stopped 续爬） ──
    task_status = task_data.get("status", "")
    if task_id and task_status in ("failed", "stopped"):
        output_dir = _BASE_OUTPUT_DIR / task_id.replace("/", "_").replace("\\", "_").replace("..", "_")
        if output_dir.exists():
            data_files = []
            py_files = []
            for f in sorted(output_dir.iterdir()):
                if f.suffix.lower() in (".csv", ".xlsx") and f.stat().st_size > 0:
                    data_files.append(f)
                elif f.suffix.lower() == ".py" and f.stat().st_size > 0:
                    py_files.append(f)

            if data_files:
                lines.append("### 📂 已有的数据文件（续爬参考）")
                for df in data_files:
                    preview, total_rows, data_rows = _read_file_preview(df, max_rows=20)
                    lines.append(f"#### {df.name}")
                    lines.append(f"- **绝对路径**: `{df.resolve()}`")
                    lines.append(f"- **总行数（含表头）**: {total_rows}")
                    lines.append(f"- **数据行数**: {data_rows}")
                    lines.append("")
                    lines.append(f"预览（前 {min(20, data_rows)} 行）:")
                    lines.append("```")
                    lines.append(preview[:2000])
                    lines.append("```")
                    lines.append("")
                    lines.append(
                        f"💡 已有 {data_rows} 条数据。请在已有基础上补充缺失的教师，"
                        f"完成去重后输出完整文件。读取文件后用 bash 的 `head` 或 python 脚本确认现有数据。"
                    )
                    lines.append("")

            if py_files:
                lines.append("### 📜 已创建的脚本文件")
                for pf in py_files:
                    lines.append(f"- `{pf.resolve()}`（你之前写的，可以直接用 bash 运行）")
                lines.append("")

    lines.append(f"### 当前请求\n{latest_user_msg}\n")
    lines.append("请基于以上上下文处理当前请求。你可以引用或操作之前生成的文件。")
    lines.append("")
    lines.append(
        "### 文件分享（必须严格遵守）\n"
        "任务完成时，用 [FILES][/FILES] 标记块列出要提供给用户下载的文件。\n"
        "只有在这个块中列出的文件才会在前端显示下载链接。\n"
        "格式：每行 `文件名 | 简短描述`，文件名只需写文件名（不含路径）。\n"
        "示例：\n"
        "[FILES]\n"
        "结果文件.csv | CSV 表格（数据处理结果）\n"
        "结果文件.xlsx | Excel 表格（含样式表头）\n"
        "[/FILES]"
    )

    prompt = "\n".join(lines)
    first_msg = user_msgs[0].get("content", latest_user_msg)
    return prompt, first_msg, True


def _detect_file_request(message: str) -> list[dict]:
    base = _BASE_OUTPUT_DIR.resolve()
    results: list[dict] = []

    quoted = re.findall(r'["""]([A-Za-z]:\\[^"""]+?\.[a-zA-Z0-9]+)[""""]', message)
    bare = re.findall(r'(?<![a-zA-Z])([A-Za-z]:\\[^\s,，。；;]+?\.[a-zA-Z0-9]+)', message)

    seen = set()
    for path_str in quoted + bare:
        if path_str in seen:
            continue
        seen.add(path_str)

        try:
            p = Path(path_str).resolve()
        except OSError:
            continue

        if not p.is_file():
            continue

        try:
            rel = p.relative_to(base)
        except ValueError:
            continue

        parts = rel.parts
        if len(parts) == 1:
            task_id = ""
            filename = parts[0]
            url = f"/api/download/{quote(parts[0])}"
        else:
            task_id = parts[0]
            filename = p.name
            url = f"/api/download/{quote(parts[0])}/{quote('/'.join(parts[1:]))}"

        results.append({
            "path": p,
            "task_id": task_id,
            "filename": filename,
            "url": url,
        })

    return results


def _final_summary(message: str, downloads: list[dict]) -> str:
    text = (message or "").strip()
    if not text:
        text = f"任务已完成，共生成 {len(downloads)} 个结果文件。" if downloads else "任务已完成。"
    if len(text) > 600:
        text = text[:600].rsplit("\n", 1)[0]
    elif downloads and len(text) < 10:
        # 如果摘要太短但有下载文件，补充文件信息
        filenames = ", ".join(d.get("filename", "") for d in downloads[:3])
        text = f"任务完成，已生成 {filenames}{' 等' if len(downloads) > 3 else ''}"
    return text


def _validate_crawl_output(task_id: str, target_depts: list[str] | None = None) -> dict:
    """质量门：Agent 完成后自动校验输出数据质量。
    
    检查项目：
    1. 脏数据（导航词冒充教师姓名）
    2. 学院范围（如果指定了学院）
    3. 邮箱格式异常
    4. 重复记录
    
    自动修复可明确的脏数据。
    返回校验报告。
    """
    import csv
    from pathlib import Path
    
    output_dir = _BASE_OUTPUT_DIR / task_id.replace("/", "_").replace("\\", "_")
    if not output_dir.exists():
        return {"status": "skip", "reason": "no output directory"}
    
    csv_files = list(output_dir.glob("*.csv"))
    if not csv_files:
        return {"status": "skip", "reason": "no CSV files"}
    
    report = {
        "status": "ok",
        "files_checked": [],
        "total_rows": 0,
        "dirty_rows_removed": 0,
        "invalid_emails_found": 0,
        "out_of_scope_rows": 0,
        "duplicates_removed": 0,
        "issues": [],
    }
    
    for csv_file in csv_files:
        # 读取
        with open(csv_file, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        original_count = len(rows)
        report["files_checked"].append(str(csv_file.name))
        
        dirty_before = len(rows)
        # 1. 脏数据过滤
        clean_rows = [r for r in rows if is_valid_person_name(r.get("姓名", ""))]
        dirty_count = dirty_before - len(clean_rows)
        if dirty_count > 0:
            report["dirty_rows_removed"] += dirty_count
            report["issues"].append(f"发现了 {dirty_count} 条脏数据（导航词当姓名），已自动过滤")
        
        # 2. 学院范围检查
        if target_depts:
            # 模糊匹配：只要行中学名包含任一目标学院名
            def matches_scope(row):
                dept = row.get("学院", row.get("department", "")).strip()
                if not dept:
                    return False
                for target in target_depts:
                    if target[:2] in dept:  # 前两个字匹配即可（如计算机→信息科学技术学院不算匹配，但信息→信息科学技术学院算）
                        return True
                return False
            
            out_of_scope = [r for r in clean_rows if not matches_scope(r)]
            if out_of_scope:
                report["out_of_scope_rows"] = len(out_of_scope)
                report["issues"].append(
                    f"发现了 {len(out_of_scope)} 条非目标学院数据（学院名: "
                    f"{', '.join(set(r.get('学院','') for r in out_of_scope[:5]))}）"
                )
        
        # 3. 邮箱格式异常
        invalid_emails = []
        for r in clean_rows:
            email = r.get("邮箱", "").strip()
            if email and not is_valid_email_format(email) and not is_admin_email(email):
                invalid_emails.append((r.get("姓名", ""), email))
        if invalid_emails:
            report["invalid_emails_found"] = len(invalid_emails)
            bad_samples = ", ".join(f"{n}:{e}" for n, e in invalid_emails[:5])
            report["issues"].append(f"发现了 {len(invalid_emails)} 个格式异常的邮箱（如 {bad_samples}）")
        
        # 4. 重复检测
        seen = set()
        deduped = []
        for r in clean_rows:
            name = r.get("姓名", "").strip()
            dept = r.get("学院", "").strip()
            email = r.get("邮箱", "").strip()
            key = (name, dept)
            if key in seen:
                continue  # 保留第一条
            seen.add(key)
            deduped.append(r)
        dup_count = len(clean_rows) - len(deduped)
        if dup_count > 0:
            report["duplicates_removed"] += dup_count
            report["issues"].append(f"发现了 {dup_count} 条重复记录（同名同学院），已去重")
        
        # 如果有问题，写回清理后的文件
        issues_found = dirty_count > 0 or dup_count > 0
        if issues_found:
            with open(csv_file, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=reader.fieldnames)
                writer.writeheader()
                writer.writerows(deduped if deduped else clean_rows)
            logger.info(f"质量门修复: {csv_file.name} 移除 {dirty_count} 脏+{dup_count} 重，{original_count}→{len(deduped)}行")
        
        report["total_rows"] += original_count
    
    if report["dirty_rows_removed"] > 0 or report["invalid_emails_found"] > 0 or report["out_of_scope_rows"] > 0 or report["duplicates_removed"] > 0:
        report["status"] = "fixed" if report["dirty_rows_removed"] > 0 or report["duplicates_removed"] > 0 else "warn"
    
    return report


# ── Phase 1: 技术消息正则匹配表 ──
TECHNICAL_PATTERNS = [
    r"^🔧\s*调用工具",
    r"^\s{4}参数:",
    r"^\s{4}\{",
    r"^📋\s*结果:",
    r"^🧠\s*Hermes\s*Orchestrator:",
    r"^🔄\s*决策循环",
    r"^🎯\s*决策:",
    r"Claude Code",
    r"^claude",
    r"Hermes.*[Oo]rchestrator",
    r"正在调用",
    r"^参数:",
    r"JSON.*(?:parse|格式|打印|输出)",
    r"执行策略|策略执行",
    r"检索状态",
    r"timeout.*(?:block|command)",
    r"^block=|^command=",
    r"Command running",
    r"tool_use_error",
    r"InputValidationError",
    r"<retrieval_status>",
    r"达到最大步数限制",
    r"达到最大决策循环数",
    r"File created successfully",
    r"Exit code \d+",
    r"SyntaxError",
    r"Traceback \(most recent call last\)",
    r"playwright_agent\.py",
    r"hermes_agent\.py",
    r"claude_agent\.py",
    r"main\.py",
]

def _parse_structured_log(raw_msg: str) -> dict | None:
    """尝试从日志中提取结构化数据，返回 stage/stats 消息。
    
    返回 None 表示无法解析，走传统过滤逻辑。
    """
    if not raw_msg:
        return None
    msg = raw_msg.strip()
    
    # 阶段导航消息 → "📌 第N阶段: ..."
    m = re.match(r"📌\s*第(\d)阶段[：:]\s*(.+)", msg)
    if m:
        stage_map = {"1": "explore", "2": "scrape", "3": "verify", "4": "export"}
        return {
            "type": "stage",
            "stage": stage_map.get(m.group(1), "unknown"),
            "stage_name": m.group(2).strip(),
            "progress_pct": int(m.group(1)) * 20,
        }
    
    # 学院完成消息 → "✅ XX学院：提取到N位教师邮箱"
    m = re.search(r"✅\s*(.+?)[：:]\s*提取到\s*(\d+)\s*位", msg)
    if m:
        return {
            "type": "stats",
            "teachers_found": int(m.group(2)),
            "department": m.group(1).strip(),
            "is_final": False,
        }
    
    # 汇总消息 → "🎉 全部爬取完成！共N位教师"
    m = re.search(r"🎉.*?共\s*(\d+)\s*位教师", msg)
    if m:
        return {
            "type": "stats",
            "teachers_found": int(m.group(1)),
            "is_final": True,
        }
    
    return None


def _is_technical_message(msg: str) -> bool:
    """检测消息是否包含技术细节，应隐藏。"""
    if not msg:
        return True
    for pattern in TECHNICAL_PATTERNS:
        if re.search(pattern, msg):
            return True
    return False


_USER_FRIENDLY_ERRORS = [
    (r"HTTP \d{3}.*Forbidden.*", "该页面暂时无法访问（权限限制），已自动跳过"),
    (r"HTTP \d{3}.*Not Found", "该页面不存在（404），已自动跳过"),
    (r"timeout", "页面加载超时，已自动跳过"),
    (r"SyntaxError", "数据处理遇到小问题，已自动修复并继续"),
    (r"Exit code \d+", "脚本执行遇到临时问题，已自动跳过"),
    (r"Traceback", "系统运行遇到一个小故障，已自动恢复"),
    (r"ConnectionError|Connection refused", "网络连接暂时不稳定，已自动跳过"),
    (r"Cannot find.*page", "未找到该页面，可能是链接已失效"),
    (r"404", "页面不存在，已自动跳过"),
    (r"403", "页面无法访问（权限限制），已自动跳过"),
    (r"500", "服务器内部错误，已自动跳过"),
]

def _translate_error(raw_error: str) -> str:
    """将技术错误翻译为用户友好的中文提示。"""
    if not raw_error:
        return "系统遇到了一个意外问题"
    for pattern, friendly in _USER_FRIENDLY_ERRORS:
        if re.search(pattern, raw_error, re.IGNORECASE):
            return friendly
    return "系统遇到了一个意外问题，已自动继续执行后续任务"


def _user_facing_message(raw_msg: str, msg_type: str = "log") -> str | None:
    """Phase 1: 两层过滤 — 结构化解析 + 正则隐藏。
    
    返回 None → 完全隐藏。
    返回 dict → 结构化消息（stage/stats），由调用方处理。
    返回 字符串 → 用户友好的文本。
    """
    if not raw_msg:
        return None
    
    msg = raw_msg.strip()
    
    # 第1层：结构化解析
    structured = _parse_structured_log(msg)
    if structured:
        return structured  # 调用方拿到 dict 会做特殊处理
    
    # 第2层：技术消息过滤
    if _is_technical_message(msg):
        return None
    
    # 第3层：友好翻译
    if msg.startswith("❌"):
        if "处理失败" in msg:
            return msg.replace("处理失败", "暂未获取到数据，跳过")
        return msg
    
    if msg.startswith("⏹️"):
        return "任务已手动停止"
    
    if "启动多级深层爬取引擎" in msg or "启动动态编排引擎" in msg:
        return "开始采集数据..."
    
    if msg.startswith("收到任务"):
        return "正在处理您的请求..."
    
    if msg.startswith("🎉") or msg.startswith("📌 第") or msg.startswith("🚀") or msg.startswith("✅"):
        return msg
    
    # 简单问答场景：不包含技术关键词的消息直接通过
    if "Hermes" not in msg and "Claude" not in msg and "工具" not in msg and "策略" not in msg:
        return msg
    
    # 兜底：可能仍有技术内容，只保留看起来友好的
    if len(msg) < 80 and not re.search(r"[{}[\]<>]", msg):
        return msg
    
    return None


def _extract_stats_from_logs(logs: list[str]) -> dict:
    """Phase 1: 从日志中提取实时统计信息。"""
    stats = {
        "teachers_found": 0,
        "emails_extracted": 0,
        "departments_done": 0,
        "department_names": [],
    }
    seen_depts = set()
    for log in logs[-50:]:  # 只看最近50条，避免累积膨胀
        # ✅ XX学院：提取到N位教师邮箱
        m = re.search(r"✅\s*(.+?)[：:]\s*提取到\s*(\d+)\s*位", log)
        if m:
            dept = m.group(1).strip()
            if dept not in seen_depts:
                seen_depts.add(dept)
                stats["departments_done"] += 1
                stats["department_names"].append(dept)
            stats["teachers_found"] += int(m.group(2))
        
        # 共N个邮箱
        m = re.search(r"共\s*(\d+)\s*个邮箱", log)
        if m:
            stats["emails_extracted"] = max(stats["emails_extracted"], int(m.group(1)))
    
    return stats


def _compute_duration(t0: float) -> str:
    elapsed = int(time.time() - t0)
    if elapsed < 60:
        return f"{elapsed}秒"
    elif elapsed < 3600:
        return f"{elapsed // 60}分{elapsed % 60}秒"
    else:
        return f"{elapsed // 3600}时{elapsed % 3600 // 60}分"


def _append_agent_log(task_id: str, msg_type: str, content: str, ts: str = "") -> None:
    """持久化 Agent 输出到任务目录的 agent_output.log，不依赖 WS 连接状态"""
    if not content:
        return
    # LangSmith 追踪子 span（失败时静默退化）
    span_id = start_span("agent_log", {"type": msg_type, "content": content[:100], "task_id": task_id})
    safe = task_id.replace("/", "_").replace("\\", "_").replace("..", "_")
    log_path = _BASE_OUTPUT_DIR / safe / "agent_output.log"
    try:
        timestamp = ts or datetime.now().strftime("%H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{msg_type}] {content}\n")
    except Exception:
        pass  # 日志写入失败不干扰主流程
    finally:
        end_span(span_id)


async def _generate_progress_summary(recent_logs: list[str]) -> str:
    """调用大模型生成笼统的爬取进度描述。

    收集最近 agent 日志，用 LLM 生成一句高层次的进度中文描述。
    若无法调用大模型，回退到本地关键词匹配。
    """
    import os as _os
    api_key = _os.environ.get("DEEPSEEK_API_KEY") or _os.environ.get("OPENAI_API_KEY")
    if api_key:
        try:
            from openai import AsyncOpenAI
            if _os.environ.get("DEEPSEEK_API_KEY"):
                client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
                model = "deepseek-chat"
            else:
                base_url = _os.environ.get("OPENAI_BASE_URL") or None
                model = _os.environ.get("OPENAI_API_MODEL") or "gpt-4o-mini"
                client = AsyncOpenAI(api_key=api_key, base_url=base_url)

            combined = "\n".join(recent_logs[-10:])  # 最近 10 条日志
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你是一个进度汇总助手。请根据以下 Agent 日志，用一句简洁的中文（不超过15字）概括当前进度。直接概括，不需要顾虑，不要使用固定模板。示例：'正在浏览教师列表页' '逐一点击教师个人主页' '扫描页面中的邮箱字段' '整理爬取到的教师数据' '正在合并各学院结果'"},
                    {"role": "user", "content": f"Agent 最近日志：\n{combined[:2000]}"}
                ],
                max_tokens=30,
                temperature=0.3
            )
            result = response.choices[0].message.content.strip()
            if result:
                return result
        except Exception:
            pass

    # 回退：本地关键词匹配
    combined = "\n".join(recent_logs[-5:]).lower()
    if any(kw in combined for kw in ["下载", "download", "文件", "csv", "xlsx"]):
        return "整理爬取结果，生成表格文件"
    if any(kw in combined for kw in ["邮箱", "email", "@"]):
        return "逐条提取并验证教师邮箱"
    if any(kw in combined for kw in ["教师", "教授", "faculty", "页面", "访问"]):
        return "访问教师个人页面，查找联系方式"
    if any(kw in combined for kw in ["搜索", "查找", "查找", "寻找", "search"]):
        return "搜索结果页面，定位教师列表"
    return "执行爬取任务中"


async def _progress_pump_llm(ws: WebSocket, stop_event: asyncio.Event, log_collector: list) -> None:
    """每 30 秒用大模型生成一条笼统的进度描述。

    若生成的描述与上一条相同则不推送，避免刷屏。
    log_collector 由调用方传入，存放所有 agent log 消息文本。
    """
    prev_message = ""

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=30)
            continue  # 被通知停止
        except asyncio.TimeoutError:
            pass  # 30 秒到，继续

        recent = log_collector[-20:] if log_collector else []
        if not recent:
            continue

        summary = await _generate_progress_summary(recent)
        if summary and summary != prev_message:
            prev_message = summary
            try:
                await ws.send_text(json.dumps({
                    "type": "progress",
                    "message": summary,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                }, ensure_ascii=False))
            except Exception:
                return


@app.websocket("/ws/{task_id}")
async def agent_logs(ws: WebSocket, task_id: str):
    await ws.accept()
    logger.info(f"WebSocket connected: {task_id}")

    task_data = history.get(task_id)
    if task_data is None:
        for _ in range(20):
            await asyncio.sleep(0.1)
            task_data = history.get(task_id)
            if task_data is not None:
                logger.info(f"task {task_id} created after wait")
                break
    if task_data is None:
        await ws.send_text(
            json.dumps({"type": "error", "message": "task not found, please resend"}, ensure_ascii=False)
        )
        await ws.close()
        return

    # 获取最新的用户消息（需要在状态检查之前，用于意图判断）
    user_message = ""
    for m in reversed(task_data.get("messages", [])):
        if m.get("role") == "user":
            user_message = m.get("content", "")
            break
    if not user_message:
        user_message = task_data.get("title", "no task found")

    # 已完成/已失败的任务 → 回放历史消息，不重新执行 Agent
    task_status = task_data.get("status", "")
    if task_status in ("completed", "failed"):
        logger.info(f"task {task_id} already {task_status}, replaying history")
        for m in task_data.get("messages", []):
            role = m.get("role", "")
            if role == "user":
                continue  # 用户消息由前端自己存，不推送
            # 历史 role"agent"→WS type"text", role"text"→WS type"text"
            ws_type = "text" if role in ("agent", "text") else role
            replay = {
                "type": ws_type,
                "message": m.get("content", ""),
                "timestamp": m.get("timestamp", ""),
            }
            if m.get("filename"):
                replay["filename"] = m["filename"]
            if m.get("url"):
                replay["url"] = m["url"]
            await ws.send_text(json.dumps(replay, ensure_ascii=False))
        await ws.send_text(json.dumps({"type": "done", "message": "任务已完成", "timestamp": datetime.now().strftime("%H:%M:%S")}))
        await ws.close()
        return

    # 从最新收到的消息中获取 user_message（非重放场景）

    if not user_message:
        user_message = task_data.get("title", "no task found")

    # ── 输入安全检测 ──
    input_guard = check_input(user_message)
    if input_guard["blocked"] and GUARD_MODE == "enforce":
        ts = datetime.now().strftime("%H:%M:%S")
        block_msg = {
            "type": "error",
            "message": f"输入内容触发安全检测，任务已被拦截。原因: {input_guard['reason']}",
            "timestamp": ts,
        }
        await ws.send_text(json.dumps(block_msg, ensure_ascii=False))
        history.add_message(task_id, {
            "id": f"guard-{task_id[:8]}-{ts}",
            "role": "agent",
            "content": block_msg["message"],
            "timestamp": ts,
        })
        history.update_status(task_id, "failed")
        await ws.close()
        return

    prompt, first_user_msg, is_followup = _build_context_prompt(task_data, user_message, task_id)
    file_requests = _detect_file_request(user_message)

    # 如果同一任务已有执行中的 handler，取消旧的（防止 Agent 挂起后死锁）
    if task_id in _running_agent_tasks:
        old_task = _running_agent_tasks[task_id]
        if not old_task.done():
            logger.warning(f"task {task_id} has running handler, cancelling old one")
            # 先杀 Claude Code 子进程
            try:
                old_proc = agent._claude.active_procs.pop(task_id, None)
                if old_proc:
                    old_proc.kill()
            except Exception:
                pass
            old_task.cancel()
            try:
                await asyncio.wait_for(old_task, timeout=3.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        _running_agent_tasks.pop(task_id, None)

    current_task = asyncio.current_task()
    _running_agent_tasks[task_id] = current_task
    _running_agent_info[task_id] = {
        "task_id": task_id,
        "title": user_message or "未命名任务",
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    try:
        msg_seq = 0

        if file_requests:
            logger.info(f"task {task_id}: file request detected, skipping agent, {len(file_requests)} file(s)")
            ts = datetime.now().strftime("%H:%M:%S")
            for fr in file_requests:
                log = {
                    "type": "download",
                    "message": f"file: {fr['filename']}",
                    "filename": fr["filename"],
                    "url": fr["url"],
                    "timestamp": ts,
                }
                msg_seq += 1
                history.add_message(task_id, {
                    "id": f"download-{task_id[:8]}-{ts}-{msg_seq}",
                    "role": "download",
                    "content": log["message"],
                    "timestamp": ts,
                    "filename": fr["filename"],
                    "url": fr["url"],
                })
                await ws.send_text(json.dumps(log, ensure_ascii=False))
            done_msg = {"type": "done", "message": "files sent", "timestamp": ts}
            history.add_message(task_id, {
                "id": f"done-{task_id[:8]}-{ts}",
                "role": "agent",
                "content": "files sent",
                "timestamp": ts,
            })
            await ws.send_text(json.dumps(done_msg, ensure_ascii=False))
            history.update_status(task_id, "completed")
            await ws.close()
            return

        if not is_followup:
            cleanup_task_dir(task_id)
            get_task_dir(task_id)

        existing_user_msg = None
        for m in task_data.get("messages", []):
            if m.get("role") == "user":
                existing_user_msg = m
                break
        if not existing_user_msg:
            history.add_message(task_id, {
                "id": f"user-{task_id[:8]}",
                "role": "user",
                "content": user_message,
            })

        # ── 智能意图路由（三路分类）—— 提前到文件检测之前执行 ──
        # 判断当前任务是否已有数据
        has_data = False
        existing_uni = ""
        if task_id:
            output_dir = _BASE_OUTPUT_DIR / task_id.replace("/", "_").replace("\\", "_")
            if output_dir.exists():
                csv_files = list(output_dir.glob("*.csv")) + list(output_dir.glob("*.xlsx"))
                has_data = any(f.stat().st_size > 200 for f in csv_files)
            # 从历史消息中提取大学名称
            for m in task_data.get("messages", []):
                content = m.get("content", "")
                uni_match = re.search(r"([一-鿿]{2,6}(?:大学|学院))", content)
                if uni_match:
                    existing_uni = uni_match.group(1)
                    break

        intent_result = await classify_intent(
            user_message,
            has_existing_data=has_data,
            existing_university=existing_uni,
        )
        logger.info(
            f"[IntentRouter] task {task_id[:8]}: intent={intent_result.intent.value} "
            f"uni={intent_result.university_name} reason={intent_result.reason}"
        )

        # ── 已有产出文件 + 已有历史消息 → 跳过执行，回放历史（仅限非增量任务） ──
        output_dir = _BASE_OUTPUT_DIR / task_id.replace("/", "_").replace("\\", "_")
        existing_files = list(output_dir.glob("*.csv")) + list(output_dir.glob("*.xlsx"))
        has_valid_files = any(f.stat().st_size > 200 for f in existing_files)
        if has_valid_files and intent_result.intent != IntentType.INCREMENTAL_CRAWL:
            existing_msgs = task_data.get("messages", [])
            has_agent_msgs = any(m.get("role") == "agent" for m in existing_msgs)
            if has_agent_msgs:
                # 如果任务状态还是 running，先修正为 completed
                if task_data.get("status") == "running":
                    history.update_status(task_id, "completed")
                    logger.info(f"task {task_id} status fixed: running → completed (output files exist)")
                logger.info(f"task {task_id} has output files and intent is {intent_result.intent.value}, replaying history")
                for m in existing_msgs:
                    role = m.get("role", "")
                    if role == "user":
                        continue
                    ws_type = "text" if role in ("agent", "text") else role
                    replay = {
                        "type": ws_type,
                        "message": m.get("content", ""),
                        "timestamp": m.get("timestamp", ""),
                    }
                    if m.get("filename"): replay["filename"] = m["filename"]
                    if m.get("url"): replay["url"] = m["url"]
                    await ws.send_text(json.dumps(replay, ensure_ascii=False))
                await ws.send_text(json.dumps({"type": "done", "message": "任务已完成", "timestamp": datetime.now().strftime("%H:%M:%S")}))
                await ws.close()
                return

        # ── 按意图分发 ──
        if intent_result.intent == IntentType.SIMPLE_QUERY:
            # 简单问答：检查是否有已索引的爬取数据可回答
            from openai import AsyncOpenAI
            api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
            base_url = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
            model = "deepseek-chat"

            # 尝试从 DataMemory 检索相关数据
            data_results = search_data(user_message, intent_result.university_name)
            if data_results:
                # 有数据 → 构造带数据的 prompt，让 LLM 回答
                univ = intent_result.university_name or data_results[0]["university"]
                stats = DataMemory.get_instance().get_stats(univ) if data_results else {}
                data_lines = []
                for r in data_results[:30]:
                    line = f"  {r['name']} | {r['email']} | {r['title']} | {r['department']}"
                    data_lines.append(line)
                data_text = "\n".join(data_lines)

                system_prompt = f"""你是 UniEmail Agent。当前查询的是「{univ}」的教师数据。

已有数据共 {stats.get('total', 0)} 条记录。
以下是部分相关数据（{len(data_results)} 条）：
{data_text}

根据以上数据回答用户的问题。如果数据不足以回答，如实说。"""

                try:
                    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
                    resp = await client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message}
                        ],
                        max_tokens=800, temperature=0.3,
                    )
                    reply = resp.choices[0].message.content or ""
                except Exception as e:
                    reply = f"查询数据时出错: {str(e)[:100]}"
            else:
                # 无数据 → 通用回答
                try:
                    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
                    resp = await client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": "你是 UniEmail Agent，一个高校教师邮箱爬取助手。回答简洁直接。"},
                            {"role": "user", "content": user_message}
                        ],
                        max_tokens=500, temperature=0.7,
                    )
                    reply = resp.choices[0].message.content or ""
                except Exception as e:
                    reply = f"抱歉，我暂时无法回答。错误: {str(e)[:100]}"

            ts = datetime.now().strftime("%H:%M:%S")
            await ws.send_text(json.dumps({"type": "text", "message": reply, "timestamp": ts}))
            history.add_message(task_id, {"id": f"text-{task_id[:8]}-{ts}", "role": "agent", "content": reply, "timestamp": ts})
            await ws.send_text(json.dumps({"type": "done", "message": "回答完毕", "timestamp": ts}))
            history.update_status(task_id, "completed")
            await ws.close()
            return

        # ── NEW_CRAWL / INCREMENTAL_CRAWL 共用执行路径 ──
        is_crawl = True
        is_incremental = intent_result.intent == IntentType.INCREMENTAL_CRAWL

        # 构建爬取提示词：技能注入 + 数据规范 + 任务隔离
        skill_prompt = load_skills_prompt(intent_result.university_name)
        schema_prompt = get_data_schema_prompt()
        inherited_tid = task_id if is_incremental else ""  # 增量任务可读取自己历史目录
        isolation_prompt = get_task_isolation_prompt(task_id, inherited_tid)

        # ── 学院范围约束（P0: 用户指定学院时，限制爬取范围） ──
        target_depts = intent_result.target_departments
        scope_prompt = ""
        if target_depts:
            dept_list = "\n".join(f"- {d}" for d in target_depts)
            scope_prompt = (
                "## 🔒 爬取范围约束\n\n"
                "用户指定了以下学院/系作为爬取范围：\n"
                f"{dept_list}\n\n"
                "请严格遵守以下规则：\n"
                "1. **只爬取以上指定学院的教师数据**，不要爬取其他不相关的学院\n"
                "2. 如果找不到名称完全匹配的学院，查找含义最接近的学院（例如用户要求「计算机科学与技术学院」但学校只有「信息科学技术学院」，则后者可能包含计算机类专业）\n"
                "3. 最终的数据文件只包含指定学院的数据，不要混入其他学院\n"
            )

        # ── 合并规则（P0: 防止好数据被差数据覆盖） ──
        merge_rule_prompt = (
            "## 🔄 数据合并规则\n\n"
            "当合并多个来源的数据时，请严格执行以下优先级：\n"
            "1. **按邮箱去重** — 有邮箱的记录优先于无邮箱的记录\n"
            "2. **字段完整性优先** — 同为有邮箱的记录时，保留字段更完整的一条（不要用空字段替换有值字段）\n"
            "3. **学院名称统一** — 同一学院尽量使用同一名称，不要因学院名不一致导致同一人重复出现\n"
            "4. **脏数据过滤** — 名称若为导航关键词（如「师资队伍」「教授」「副教授」「讲师」「兼职教授」「首页」等），应剔除\n"
        )

        # ── 硬性爬取规范（P0: 必须遵守，由 Hermes 统一派发） ──
        strategy_prompt = (
            "## 🔥 硬性爬取规范（必须逐条遵守，违者视为执行失败）\n\n"
            "### 1. 执行模式：每个学院独立 + 3 学院并行\n"
            "- 每个学院写一个独立的爬取函数，不能共用通用脚本\n"
            "- **必须同时启动 3 个学院的爬取**（使用 asyncio.gather 或 ThreadPoolExecutor(3)）\n"
            "- 例：启动线程1爬中医学院 + 线程2爬药学院 + 线程3爬医学院，同时跑\n"
            "- 一个学院完成后，立即启动下一个学院，始终保持 3 个并发\n\n"
            "### 2. 质量阈值：每学院 ≥35 人且 ≥35 邮箱\n"
            "- 每个学院爬完后，**立即统计**该学院的教师数和邮箱数\n"
            "- 如果该学院教师数 < 35 或邮箱数 < 35，**必须立即执行二次检查**：\n"
            "  1. 检查是否只爬了部分子分类（如只爬了教授没爬副教授）\n"
            "  2. 检查 URL 模式是否遗漏了其他师资入口\n"
            "  3. 尝试备选 URL 或备选选择器重新爬取\n"
            "  4. 记录缺失原因到日志\n"
            "- 二次检查完成后才可认为该学院完成\n\n"
            "### 3. 邮箱提取规则\n"
            "- 只提取教师个人邮箱，忽略学院公共邮箱（webmaster、wxyxz 等）\n"
            "- 反爬恢复：`xxx[at]xxx.com` → `xxx@xxx.com`，`xxx#@xxx.com` → `xxx@xxx.com`\n"
            "- 无邮箱的留空，不要填「无邮箱」\n\n"
            "### 4. 关键要点\n"
            "- 必须进个人详情页才有邮箱，列表页没有\n"
            "- 遇到反爬或失败继续下一个，不要重试同一页面超过 2 次\n"
        )

        # 注入到 prompt 前面
        injection_parts = []
        if skill_prompt:
            injection_parts.append(skill_prompt)
        # Mem0 持久记忆搜索（与文件系统技能库互补）
        mem0_prompt = search_mem0(first_user_msg, intent_result.university_name)
        if mem0_prompt:
            injection_parts.append(mem0_prompt)
        if scope_prompt:
            injection_parts.append(scope_prompt)
        injection_parts.append(schema_prompt)
        injection_parts.append(isolation_prompt)
        injection_parts.append(merge_rule_prompt)
        injection_parts.append(strategy_prompt)
        if is_incremental:
            injection_parts.append(
                "## 🔄 增量爬取说明（必须严格遵守）\n\n"
                "这是一个**增量补充任务**。现有的 CSV/XLSX 文件已在任务目录下，请按以下步骤执行：\n\n"
                "### 第一步：读取现有数据\n"
                "1. 先 `ls outputs/{task_id}/` 查看有哪些文件\n"
                "2. 读取已有的 CSV 文件，了解已覆盖的学院和每学院教师数\n"
                "3. 与该校的完整学院列表对比，找出缺失或数据不足的学院\n\n"
                "### 第二步：只补充缺失部分\n"
                "4. **只对缺失学院或数据严重不足的学院进行补充爬取**\n"
                "5. 已有数据的学院不要重复爬取\n"
                "6. 如果某个学院之前因动态加载/PDF 失败，换策略再试：\n"
                "   - 动态 JS 页面 → 用 Playwright 的 `wait_for_selector` + 延迟等待渲染完成\n"
                "   - PDF 教师名录 → 先用 requests 下载 PDF，再用 PyMuPDF/PDFPlumber 提取\n"
                "   - iframe 内嵌页面 → 切换到 iframe context 再操作\n"
                "   - 跨域 API 加载 → 在浏览器 Network 面板找 XHR/JSON 接口直接调\n\n"
                "### 第三步：合并输出\n"
                "7. 新数据与已有数据去重合并后输出完整文件\n"
                "8. 不要覆盖已有的正确数据，只补充缺失部分\n"
            )
        # Phase 3: 用户可读输出指令
        user_output_guide = (
            "## 📊 用户可读输出指令（重要）\n\n"
            "你的输出将直接展示给终端用户，请严格遵守：\n\n"
            "1. **输出格式要求**\n"
            "   - 每完成一个学院/系的邮箱提取，以 `✅ XX学院：提取到N位教师邮箱` 开头输出一行\n"
            "   - 当整体爬取完成时，以 `🎉 全部爬取完成！共N位教师，覆盖M个学院` 结尾\n"
            "   - 遇到进度变更时（如从\"探索学院\"进入\"提取邮箱\"），以 `📌 第N阶段：阶段名称` 开头输出\n\n"
            "2. **禁止输出的内容**\n"
            "   - ❌ 不要输出技术工具名（\"Claude Code\"、\"Hermes\"、\"Playwright\"）\n"
            "   - ❌ 不要输出文件路径（\"/outputs/xxx/...\"）\n"
            "   - ❌ 不要输出文件创建消息\n"
            "   - ❌ 不要输出脚本代码、JSON 片段、命令参数\n"
            "   - ❌ 不要输出 Exit code、Traceback、SyntaxError 等错误代码\n\n"
            "3. **错误处理**\n"
            "   - 遇到某个学院数据无法获取时，用中文自然语言描述问题\n"
            "   - 正确：✅ 材料学院页面暂时无法访问，已自动跳过\n"
            "   - 错误：❌ HTTP 404 from https://...\n\n"
            "4. **自然语言要求**\n"
            "   - 使用纯中文自然语言回复用户\n"
            "   - 每个输出步骤前加 emoji 前缀\n"
            "   - 每段输出控制在一行内，不超过 80 字\n"
        )
        injection_parts.append(user_output_guide)
        skill_injection = "\n\n".join(injection_parts)

        # 将技能注入插入到 prompt 构建之前
        if is_followup:
            # 追问场景：在已有上下文 prompt 前插入技能注入
            prompt = skill_injection + "\n\n" + prompt
        else:
            # 新任务：技能注入放在 context prompt 之前
            prompt = skill_injection + "\n\n" + prompt

        progress_stop = asyncio.Event()
        progress_task = None
        log_collector: list[str] = []  # 存放 agent 日志，供 LLM 进度生成使用
        if is_crawl:
            progress_task = asyncio.create_task(_progress_pump_llm(ws, progress_stop, log_collector))
        last_agent_line = ""
        downloads: list[dict] = []

        had_error = False
        # Phase 1: 记录任务开始时间
        _task_start_times[task_id] = time.time()
        # ── LangSmith 全链路追踪 ──
        trace_run_id: str | None = None
        if is_crawl:
            try:
                uni_name = intent_result.university_name or "未知大学"
                trace_run_id = create_run(f"crawl:{uni_name}", {"task_id": task_id, "user_message": user_message})
                if trace_run_id:
                    _trace_runs[task_id] = trace_run_id
                    trace_url = get_trace_url(trace_run_id)
                    await ws.send_text(json.dumps({
                        "type": "trace",
                        "run_id": trace_run_id,
                        "trace_url": trace_url,
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                    }, ensure_ascii=False))
            except Exception as e:
                logger.error(f"创建 LangSmith trace 失败（不影响任务）: {e}")
        # 聚合 text 消息（流式 token 先攒起来，done/error 时一次性写入历史）
        text_buffer: list[str] = []
        text_buffer_ts = ""  # 第一条 text 的时间戳
        async for log in agent.execute(
            prompt,
            task_id,
            intent_result=intent_result,
            is_continuation=is_followup,
            is_crawl_session=is_crawl,
            current_user_message=user_message
        ):
            msg_seq += 1
            msg_type = log.get("type", "agent")
            # 持久化所有 Agent 输出到日志文件（不依赖 WS 状态）
            _append_agent_log(task_id, msg_type, str(log.get("message", "")), log.get("timestamp", ""))
            if msg_type == "log":
                text = log.get("message", "") or ""
                if text:
                    # ── 原始日志：直接推 WS 供日志面板显示（不受用户友好过滤影响）──
                    raw_log_ws = {
                        "type": "log",
                        "message": text,
                        "timestamp": log.get("timestamp", datetime.now().strftime("%H:%M:%S")),
                    }
                    try:
                        await ws.send_text(json.dumps(raw_log_ws, ensure_ascii=False))
                    except Exception:
                        pass
                    # ── Phase 1: 应用用户友好过滤 —— 可能返回 dict(stage/stats) ──
                    translated = _user_facing_message(text)
                    if translated is None:
                        continue  # 完全隐藏该消息，跳过后续处理
                    if isinstance(translated, dict):
                        # 结构化消息（stage/stats），直接推送 WS
                        stype = translated.get("type", "log")
                        translated["timestamp"] = log.get("timestamp", datetime.now().strftime("%H:%M:%S"))
                        await ws.send_text(json.dumps(translated, ensure_ascii=False))
                        # 统计消息存历史以便前端回溯
                        if stype in ("stats", "stage"):
                            history.add_message(task_id, {
                                "id": f"{stype}-{task_id[:8]}-{translated.get('timestamp','')}",
                                "role": stype,
                                "content": json.dumps(translated, ensure_ascii=False),
                                "timestamp": translated.get("timestamp", ""),
                            })
                        continue
                    if translated != text:
                        log["message"] = translated  # 用翻译后的消息替换
                        text = translated
                    log_collector.append(text)  # 收集日志供 LLM 进度汇总
                    # ── Phase 1: 每 5 条 log 推送一次实时 stats ──
                    if "_stats_log_counter" not in dir():
                        _stats_log_counter = 0
                    _stats_log_counter += 1
                    if _stats_log_counter >= 5:
                        _stats_log_counter = 0
                        stats = _extract_stats_from_logs(log_collector)
                        if stats["teachers_found"] > 0 or stats["departments_done"] > 0:
                            stats_msg = {
                                "type": "stats",
                                "teachers_found": stats["teachers_found"],
                                "emails_extracted": stats["emails_extracted"],
                                "departments_done": stats["departments_done"],
                                "department_names": stats["department_names"][-3:],  # 最近3个
                                "timestamp": datetime.now().strftime("%H:%M:%S"),
                            }
                            await ws.send_text(json.dumps(stats_msg, ensure_ascii=False))
                logger.info("task %s agent: %s", task_id, text[:500])
                # 持久化用户可见的 log 消息到历史（刷新后日志面板也能看到）
                history.add_message(task_id, {
                    "id": f"log-{task_id[:8]}-{log.get('timestamp', datetime.now().strftime('%H:%M:%S'))}-{msg_seq}",
                    "role": "log",
                    "content": text[:500],
                    "timestamp": log.get("timestamp", datetime.now().strftime("%H:%M:%S")),
                })
                continue  # ❗️ log 类型只做收集，不落入后续的 common path（不写 history、不发 WS）
            if msg_type == "text":
                text = log.get("message", "") or ""
                if text:
                    if not text_buffer:
                        text_buffer_ts = log.get("timestamp", "")
                    # ── Phase 1+3: text 消息也要过过滤 ──
                    filtered = _user_facing_message(text)
                    if filtered is None:
                        logger.info("Phase1-filter: hiding text msg: %s", text[:80])
                        continue  # 隐藏技术文本
                    if isinstance(filtered, dict):
                        # 结构化消息直接推
                        filtered["timestamp"] = log.get("timestamp", datetime.now().strftime("%H:%M:%S"))
                        await ws.send_text(json.dumps(filtered, ensure_ascii=False))
                        continue
                    text = filtered if isinstance(filtered, str) else text
                    log["message"] = text  # 更新 log 对象，后续 WS 发送时会用过滤后的文本
                    text_buffer.append(text)
                    last_agent_line = text
                    log_collector.append(text)
                logger.info("task %s text: %s", task_id, text[:500])
                # 流式 token 先缓冲，不立即写入历史；仅转发 WS 给前端实时显示
                await ws.send_text(json.dumps(log, ensure_ascii=False))
                continue
            if msg_type == "download":
                downloads.append(log)
                history.add_message(task_id, {
                    "id": f"download-{task_id[:8]}-{log.get('timestamp', '')}-{msg_seq}",
                    "role": "download",
                    "content": log.get("message", ""),
                    "timestamp": log.get("timestamp", ""),
                    "filename": log.get("filename", ""),
                    "url": log.get("url", ""),
                })
                await ws.send_text(json.dumps(log, ensure_ascii=False))
                continue
            if msg_type == "file":
                # 脚本/中间文件只存历史不推送到前端，只展示产物结果文件
                history.add_message(task_id, {
                    "id": f"file-{task_id[:8]}-{log.get('timestamp', '')}-{msg_seq}",
                    "role": "file",
                    "content": log.get("message", ""),
                    "timestamp": log.get("timestamp", ""),
                    "filename": log.get("filename", ""),
                    "filepath": log.get("filepath", ""),
                })
                # 不推送到 WS——前端不展示中间脚本创建通知
                continue
            if msg_type == "done":
                last_agent_line = log.get("message", "Agent 任务执行完毕")
                # flush 文本缓冲区到历史
                if text_buffer:
                    aggregated = "".join(text_buffer)
                    history.add_message(task_id, {
                        "id": f"text-{task_id[:8]}-{text_buffer_ts}-agg",
                        "role": "agent",
                        "content": aggregated,
                        "timestamp": text_buffer_ts,
                    })
                    text_buffer.clear()
                continue
            if msg_type == "error":
                had_error = True
                # ── Phase 1: 将技术错误翻译为用户友好提示 ──
                raw_err = log.get("message", "") or ""
                friendly = _translate_error(raw_err)
                # 同时发送友好版和原始版（友好版给用户，原始版存日志）
                if friendly and friendly != raw_err:
                    log["message"] = friendly
                    log["type"] = "error_user"  # 用新类型区分
                    # 把原始错误存到另一个字段供调试
                await ws.send_text(json.dumps({
                    "type": "error_user",
                    "message": friendly,
                    "severity": "warning",
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                }, ensure_ascii=False))
                # 错误的 text 内容也要 flush，不丢失上下文
                if text_buffer:
                    aggregated = "".join(text_buffer)
                    history.add_message(task_id, {
                        "id": f"text-{task_id[:8]}-{text_buffer_ts}-agg",
                        "role": "agent",
                        "content": aggregated,
                        "timestamp": text_buffer_ts,
                    })
                    text_buffer.clear()
            role_map = {"log": "log", "download": "download", "error": "agent", "done": "agent", "text": "text"}
            # 先写历史再发 WS，防止刷新时消息丢失
            history.add_message(task_id, {
                "id": f"{msg_type}-{task_id[:8]}-{log.get('timestamp', '')}-{msg_seq}",
                "role": role_map.get(msg_type, "log"),
                "content": log.get("message", ""),
                "timestamp": log.get("timestamp", ""),
                "filename": log.get("filename", ""),
                "url": log.get("url", ""),
            })
            await ws.send_text(json.dumps(log, ensure_ascii=False))

        # Agent 流结束，flush 剩余的 text_buffer
        if text_buffer:
            aggregated = "".join(text_buffer)
            history.add_message(task_id, {
                "id": f"text-{task_id[:8]}-{text_buffer_ts}-agg",
                "role": "agent",
                "content": aggregated,
                "timestamp": text_buffer_ts,
            })
            text_buffer.clear()

        progress_stop.set()
        if progress_task:
            try:
                await progress_task
            except Exception:
                pass

        if had_error:
            history.update_status(task_id, "failed")
        else:
            ts = datetime.now().strftime("%H:%M:%S")
            summary = _final_summary(last_agent_line, downloads)

            # ── 质量门：Agent 完成后自动校验输出数据质量 ──
            try:
                quality_report = _validate_crawl_output(task_id, target_depts)
                if quality_report["status"] != "skip" and quality_report["issues"]:
                    # 把校验结果发到 WS
                    quality_msg = "📋 **自我审查报告**\n"
                    for issue in quality_report["issues"]:
                        quality_msg += f"  {issue}\n"
                    quality_msg += f"\n原始数据 {quality_report['total_rows']} 条"
                    if quality_report["dirty_rows_removed"] > 0:
                        quality_msg += f" | 清理 {quality_report['dirty_rows_removed']} 条脏数据"
                    if quality_report["duplicates_removed"] > 0:
                        quality_msg += f" | 去重 {quality_report['duplicates_removed']} 条"
                    if quality_report["out_of_scope_rows"] > 0:
                        quality_msg += f" | ⚠️ {quality_report['out_of_scope_rows']} 条非目标学院数据"
                    # 发送质量报告
                    await ws.send_text(json.dumps({
                        "type": "agent",
                        "message": quality_msg,
                        "timestamp": ts,
                    }, ensure_ascii=False))
                    history.add_message(task_id, {
                        "id": f"quality-{task_id[:8]}-{ts}",
                        "role": "agent",
                        "content": quality_msg,
                        "timestamp": ts,
                    })
                    logger.info(f"质量门报告 task {task_id[:8]}: {quality_report['status']} - {len(quality_report['issues'])} issues")
            except Exception as e:
                logger.error(f"质量门校验失败（不影响任务结果）: {e}")

            # ── IntellAgent 自动评估 ──
            try:
                output_dir = _BASE_OUTPUT_DIR / task_id.replace("/", "_").replace("\\", "_")
                if output_dir.exists():
                    uni_config = {"departments": target_depts} if target_depts else None
                    for csv_file in output_dir.glob("*.csv"):
                        eval_report = eval_crawl(str(csv_file), task_id, uni_config)
                        eval_save(eval_report, str(output_dir))
                        # 提取 email_rate 和 colleges_found
                        email_rate = eval_report.get("details", {}).get("email_coverage", {}).get("rate", 0)
                        colleges_found = eval_report.get("details", {}).get("department_coverage", {}).get("matched", [])
                        eval_msg = (
                            f"📊 **质量评估** (得分: {eval_report['quality_score']}/100, "
                            f"{'通过' if eval_report['passed'] else '未通过'})\n"
                        )
                        for w in eval_report["warnings"]:
                            eval_msg += f"  ⚠ {w}\n"
                        await ws.send_text(json.dumps({
                            "type": "eval",
                            "message": eval_msg,
                            "quality_score": eval_report["quality_score"],
                            "passed": eval_report["passed"],
                            "warnings": eval_report["warnings"],
                            "email_rate": email_rate,
                            "colleges_found": colleges_found,
                            "timestamp": ts,
                        }, ensure_ascii=False))
                        history.add_message(task_id, {
                            "id": f"eval-{task_id[:8]}-{ts}",
                            "role": "agent",
                            "content": eval_msg,
                            "timestamp": ts,
                        })
                        logger.info(
                            f"IntellAgent 评估 task {task_id[:8]}: "
                            f"score={eval_report['quality_score']}, passed={eval_report['passed']}"
                        )
            except Exception as e:
                logger.error(f"IntellAgent 评估失败（不影响任务结果）: {e}")

            # ── Phase 1: 完成时推送结构化 summary ──
            if is_crawl:
                try:
                    task_start = _task_start_times.get(task_id, time.time())
                    duration = _compute_duration(task_start)
                    # 统计各个 CSV 行数
                    total_rows = 0
                    total_emails = 0
                    output_dir = _BASE_OUTPUT_DIR / task_id.replace("/", "_").replace("\\", "_")
                    if output_dir.exists():
                        import csv as csv_mod
                        for csv_file in output_dir.glob("*.csv"):
                            try:
                                with open(csv_file, "r", encoding="utf-8-sig") as f:
                                    reader = csv_mod.DictReader(f)
                                    rows = list(reader)
                                    total_rows += len(rows)
                                    total_emails += sum(1 for r in rows if r.get("邮箱", "").strip())
                            except Exception:
                                pass
                    # 只提取大学名（去掉请求中的多余文字）
                    uni_display = intent_result.university_name or "未知大学"
                    summary_data = {
                        "type": "summary",
                        "university": uni_display,
                        "total_teachers": total_rows,
                        "total_emails": total_emails,
                        "departments_covered": 0,  # 由前端从前面的 stats 消息累计
                        "total_departments": 0,
                        "duration": duration,
                        "files": [d.get("filename", "") for d in downloads],
                        "timestamp": ts,
                    }
                    await ws.send_text(json.dumps(summary_data, ensure_ascii=False))
                except Exception as e:
                    logger.error(f"推送 summary 失败（不影响任务结果）: {e}")

            history.add_message(task_id, {
                "id": f"done-{task_id[:8]}-{ts}",
                "role": "agent",
                "content": summary,
                "timestamp": ts,
            })
            await ws.send_text(json.dumps({"type": "done", "message": summary, "timestamp": ts}, ensure_ascii=False))
            history.update_status(task_id, "completed")

            # ── 索引爬取结果到 DataMemory（与 CrawlMemory 分离） ──
            if uni_name:
                output_dir = _BASE_OUTPUT_DIR / task_id.replace("/", "_").replace("\\", "_")
                if output_dir.exists():
                    for csv_file in sorted(output_dir.glob("*.csv")):
                        if csv_file.stat().st_size > 200:
                            indexed = index_csv_to_memory(str(csv_file), uni_name, task_id)
                            if indexed > 0:
                                logger.info(f"[DataMemory] 已索引 {indexed} 条 ({csv_file.name})")

            # ── 结束 LangSmith trace ──
            _run_id = _trace_runs.get(task_id)
            if _run_id:
                try:
                    end_run(_run_id, outputs={"status": "completed", "summary": summary[:500]})
                    trace_url = get_trace_url(_run_id)
                    await ws.send_text(json.dumps({
                        "type": "trace",
                        "run_id": _run_id,
                        "trace_url": trace_url,
                        "timestamp": ts,
                    }, ensure_ascii=False))
                except Exception as e:
                    logger.error(f"结束 LangSmith trace 失败: {e}")
                finally:
                    _trace_runs.pop(task_id, None)

        final_task = history.get(task_id)
        if final_task:
            # 生成技能文件（受异常保护，不影响后续操作）
            try:
                await _generate_skills(task_id, final_task)
            except Exception as e:
                logger.error(f"生成技能文件失败（不影响任务结果）: {e}")
            # ── 后置反思：爬取/增量任务完成后，LLM 分析日志提取新经验 ──
            if is_crawl and not had_error:
                asyncio.create_task(
                    _post_task_reflection(task_id, final_task, intent_result.university_name)
                )

        await ws.close()

    except WebSocketDisconnect:
        # 前端刷新/断网导致 WS 断开：不标记 failed，保持 running 状态
        # 前端重连后会重新取得进度
        logger.info(f"WebSocket disconnected: {task_id} — agent still running, ready for reconnect")
        # 不修改状态，不终止 Agent
        _running_agent_tasks.pop(task_id, None)
        _running_agent_info.pop(task_id, None)
        return
    except asyncio.CancelledError:
        logger.info(f"task {task_id} cancelled, cleaning up")
        history.update_status(task_id, "failed")
        _ts = datetime.now().strftime("%H:%M:%S")
        history.add_message(task_id, {
            "id": f"cancel-{task_id[:8]}-{_ts}",
            "role": "agent",
            "content": "任务已被取消",
            "timestamp": _ts,
        })
        # 结束 LangSmith trace（失败/取消）
        _r_id = _trace_runs.pop(task_id, None)
        if _r_id:
            try:
                end_run(_r_id, error="task_cancelled")
            except Exception:
                pass
        if _running_agent_tasks.get(task_id) is current_task:
            _running_agent_tasks.pop(task_id, None)
            _running_agent_info.pop(task_id, None)
        if hasattr(agent, "stop_task"):
            agent.stop_task(task_id)
    except Exception as e:

        err_detail = f"{type(e).__name__}: {str(e)[:300]}"
        logger.error(f"WebSocket error {task_id}: {err_detail}")
        history.update_status(task_id, "failed")
        err_msg = {"type": "error", "message": f"execution error: {err_detail}"}
        history.add_message(task_id, {
            "id": f"error-{task_id[:8]}-{datetime.now().strftime('%H%M%S')}",
            "role": "agent",
            "content": err_msg["message"],
        })
        # 结束 LangSmith trace（失败）
        _r_id = _trace_runs.pop(task_id, None)
        if _r_id:
            try:
                end_run(_r_id, error=err_detail[:500])
            except Exception:
                pass
        try:
            await ws.send_text(json.dumps(err_msg, ensure_ascii=False))
        except Exception:
            pass
        try:
            await ws.close()
        except Exception:
            pass
        if _running_agent_tasks.get(task_id) is current_task:
            _running_agent_tasks.pop(task_id, None)
            _running_agent_info.pop(task_id, None)
        if hasattr(agent, "stop_task"):
            agent.stop_task(task_id)
    else:
        # 正常完成：清除进程记录
        _running_agent_tasks.pop(task_id, None)
        _running_agent_info.pop(task_id, None)
        # 正常完成不需要 stop_task，避免干扰其他任务
