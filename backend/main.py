"""UniEmail Agent — FastAPI 后端服务 (Phase 5: 任务隔离 + 持久化 + 分页)"""

import os
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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from agent.claude_agent import ClaudeAgent
from agent.exporter import get_task_dir, cleanup_task_dir, _BASE_OUTPUT_DIR
from agent.history import history
from agent.universities import (
    build_university_response,
    get_university_records,
    parse_table_file,
    resolve_table_path,
)
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

agent = ClaudeAgent()

# 正在执行 Agent 的任务追踪（task_id -> asyncio.Task），防止重复执行
_running_agent_tasks: dict[str, asyncio.Task] = {}
_running_agent_info: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("UniEmail Agent 后端启动")
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
            role_map = {"log": "log", "download": "download", "error": "agent", "done": "agent"}
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


MIME_MAP = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".md": "text/markdown",
    ".html": "text/html",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _safe_resolve(base: Path, *parts: str) -> Path | None:
    p = base.resolve()
    for part in parts:
        p = (p / part).resolve()
        if not str(p).startswith(str(base.resolve()) + os.sep) and p != base.resolve():
            return None
    return p


@app.get("/api/download/{task_id}/{filename:path}")
async def download_file_tasked(task_id: str, filename: str):
    if ".." in filename or ".." in task_id:
        raise HTTPException(status_code=400, detail="invalid filename")
    safe_tid = task_id.replace("/", "_").replace("\\", "_").replace("..", "_")
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


GLOBAL_SKILLS_FILE = SKILLS_DIR / "global_crawling_rules.md"


def _update_global_skills(uni_name: str, task_data: dict) -> None:
    if uni_name == "unknown":
        return

    # 从历史执行消息中深度挖掘有商业可复用价值的技术资产 (URL、关键 CSS 类、反爬经验、JS 加载发现)
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
            # 过滤有价值的大学链接
            if any(x in u_clean for x in (uni_name, "tsinghua", "nju", "seu", "njust", "njupt", "bupt")):
                extracted_urls.add(u_clean)

        # 提取关键选择器 / DOM 标记
        selectors = re.findall(r'(\.[a-zA-Z0-9_-]{3,20}|#[a-zA-Z0-9_-]{3,20}|frag="[^"]+")', content)
        for s in selectors:
            if s not in (".xlsx", ".csv", ".json", ".html", ".png", ".py", ".md", ".pdf", ".docx"):
                extracted_selectors.add(s)

        # 特征提取
        keywords = ["description", "Article_Title", "内联", "反爬", "邮箱规则", "职称", "JS动态", "iframe", "requests", "Playwright"]
        for kw in keywords:
            if kw in content and kw not in special_tips:
                special_tips.append(kw)

    # 仅在挖掘出真实有效模式时才更新全局文件
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
            "# 🌍 全局高校教师邮箱爬取技能知识库 (Global Centralized Crawling Skills)\n",
            "\n",
            "本文件是由所有任务共同维护的全局经验共享文件。每当一个任务成功爬取完毕，后端便会自动从中提取出最成功的核心策略（包括特定高校官网的最佳路径、HTML 选择器结构、反爬绕过方案等），以供后续所有新任务在执行前进行自动读取、自主学习与智能升级。\n",
            "\n",
        ]

    full_text = "".join(content_lines)

    # 组装学校策略卡片
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

    # 正则精准更新，防止重复追加
    pattern = rf"## 🏫 {re.escape(uni_name)} 爬取策略与模式.*?(?=\n## 🏫 |\Z)"
    if re.search(pattern, full_text, re.DOTALL):
        updated_text = re.sub(pattern, new_school_text.strip(), full_text, flags=re.DOTALL)
    else:
        updated_text = full_text.rstrip() + "\n\n" + new_school_text

    try:
        with open(GLOBAL_SKILLS_FILE, "w", encoding="utf-8") as f:
            f.write(updated_text)
        logger.info(f"Global skills knowledgebase updated for {uni_name}!")
    except OSError as e:
        logger.error(f"Global skills save failed: {e}")


def _generate_skills(task_id: str, task_data: dict) -> None:
    SKILLS_DIR.mkdir(exist_ok=True)

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
            match = re.search(r"([一-防]{2,4}(?:大学|学院))", content)
            if not match:
                # 兼容汉字匹配范围扩展
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

    # 1. 共同维护并动态丰富同一个全局共享技能文件（Global shared skill file）
    _update_global_skills(uni_name, task_data)

    # 2. 依然保留隔离专属的元数据 JSON 供系统检索
    skill_file = SKILLS_DIR / f"{uni_name}_{task_id[:8]}.json"
    try:
        with open(skill_file, "w", encoding="utf-8") as f:
            json.dump(skill, f, ensure_ascii=False, indent=2)
        logger.info(f"Skill generated: {skill_file.name}")
    except OSError as e:
        logger.error(f"Skill save failed: {e}")


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
    """读取全局共享爬取技能知识库，供注入到 Agent 提示词中。

    返回格式化后的 Markdown 字符串；若文件不存在或为空则返回空字符串。
    """
    if not GLOBAL_SKILLS_FILE.exists():
        return ""
    try:
        text = GLOBAL_SKILLS_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not text:
        return ""
    return (
        "### 📚 全局共享技能与爬取经验库\n"
        "以下是系统从过往所有成功任务中自动提炼的高校爬取经验，"
        "请在执行本次任务前仔细阅读并优先使用其中已验证的 URL、选择器和反爬策略：\n\n"
        f"{text}\n\n"
        "---\n"
    )


def _build_context_prompt(task_data: dict, latest_user_msg: str) -> tuple[str, str, bool]:
    messages = task_data.get("messages", [])
    user_msgs = [m for m in messages if m.get("role") == "user"]

    global_skills = _load_global_skills()

    if len(user_msgs) <= 1:
        # 新任务：如果有全局技能则在任务需求前注入
        if global_skills:
            prompt = (
                global_skills
                + "### 具体任务需求\n"
                + latest_user_msg
            )
        else:
            prompt = latest_user_msg
        return prompt, latest_user_msg, False

    lines = []
    # 追问场景：同样注入全局技能（最新知识库可能在上轮任务后有新增）
    if global_skills:
        lines.append(global_skills)
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
    if files:
        seen = set()
        lines.append("### 已生成的文件")
        for f in files:
            if f not in seen:
                seen.add(f)
                lines.append(f"- {f}")
        lines.append("")

    agent_msgs = [m for m in messages if m.get("role") == "agent" and m.get("content")]
    if agent_msgs:
        last = agent_msgs[-1].get("content", "")
        if len(last) > 800:
            last = last[:800].rsplit("\n", 1)[0]
        lines.append("### 上次任务的回复摘要")
        lines.append(last)
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


PROGRESS_MESSAGES = [
    "正在识别目标高校",
    "正在访问官网与院系页面",
    "正在提取教师信息",
    "正在清洗邮箱数据",
    "正在生成结果文件",
]


def _final_summary(message: str, downloads: list[dict]) -> str:
    text = (message or "").strip()
    if not text:
        text = f"任务已完成，共生成 {len(downloads)} 个结果文件。" if downloads else "任务已完成。"
    if len(text) > 600:
        text = text[:600].rsplit("\n", 1)[0]
    return text


async def _progress_pump(ws: WebSocket, stop_event: asyncio.Event) -> None:
    idx = 0
    while not stop_event.is_set():
        try:
            await ws.send_text(json.dumps({
                "type": "progress",
                "message": PROGRESS_MESSAGES[min(idx, len(PROGRESS_MESSAGES) - 1)],
                "step": min(idx + 1, len(PROGRESS_MESSAGES)),
                "total": len(PROGRESS_MESSAGES),
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            }, ensure_ascii=False))
        except Exception:
            return
        idx += 1
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=8.0 if idx < len(PROGRESS_MESSAGES) else 14.0)
        except asyncio.TimeoutError:
            continue


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

    user_message = ""
    for m in reversed(task_data.get("messages", [])):
        if m.get("role") == "user":
            user_message = m.get("content", "")
            break

    if not user_message:
        user_message = task_data.get("title", "no task found")

    prompt, first_user_msg, is_followup = _build_context_prompt(task_data, user_message)
    file_requests = _detect_file_request(user_message)

    # 如果同一任务已有执行中的 handler，取消旧的（防止 Agent 挂起后死锁）
    if task_id in _running_agent_tasks:
        old_task = _running_agent_tasks[task_id]
        if not old_task.done():
            logger.warning(f"task {task_id} has running handler, cancelling old one")
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

        # 根据会话中的首条用户消息内容决定整个会话的类型（避免追问被误判为爬取任务）
        first_user_content = user_message
        for m in task_data.get("messages", []):
            if m.get("role") == "user":
                first_user_content = m.get("content", "")
                break

        is_crawl = await agent._is_crawl_task(first_user_content)
        progress_stop = asyncio.Event()
        progress_task = None
        if is_crawl:
            progress_task = asyncio.create_task(_progress_pump(ws, progress_stop))
        last_agent_line = ""
        downloads: list[dict] = []

        had_error = False
        async for log in agent.execute(
            prompt,
            task_id,
            is_continuation=is_followup,
            is_crawl_session=is_crawl,
            current_user_message=user_message
        ):
            msg_seq += 1
            msg_type = log.get("type", "agent")
            if msg_type == "log":
                text = log.get("message", "") or ""
                if text:
                    last_agent_line = (last_agent_line + " " + text).strip() if last_agent_line else text
                logger.info("task %s agent: %s", task_id, text[:500])
            if msg_type == "download":
                downloads.append(log)
                continue
            if msg_type == "done":
                last_agent_line = last_agent_line or log.get("message", "")
                continue
            if msg_type == "error":
                had_error = True
            role_map = {"log": "log", "download": "download", "error": "agent", "done": "agent"}
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
            history.add_message(task_id, {
                "id": f"done-{task_id[:8]}-{ts}",
                "role": "agent",
                "content": summary,
                "timestamp": ts,
            })
            await ws.send_text(json.dumps({"type": "done", "message": summary, "timestamp": ts}, ensure_ascii=False))
            history.update_status(task_id, "completed")

        final_task = history.get(task_id)
        if final_task:
            _generate_skills(task_id, final_task)

        await ws.close()

    except WebSocketDisconnect:
        # 前端刷新/断网导致 WS 断开：标记为 failed，避免任务永久 stuck 在 running
        logger.info(f"WebSocket disconnected: {task_id} — marking as failed")
        history.update_status(task_id, "failed")
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
            if hasattr(agent, "stop_task"):
                agent.stop_task(task_id)
