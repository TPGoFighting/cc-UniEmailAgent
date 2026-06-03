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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, UploadFile, File
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
    add_table_row,
    update_table_row,
    delete_table_row,
    upload_university_file,
    delete_university_file,
    rename_university_file,
    clean_university_tables,
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
    """统一的任务分类端点：前端不再自行实现 isCrawlTask，统一走后端。"""
    is_crawl = await agent._is_crawl_task(req.message)
    return {"is_crawl": is_crawl}


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


GLOBAL_SKILLS_FILE = SKILLS_DIR / "global_crawling_rules.md"
CRAWL_KNOWLEDGE_FILE = SKILLS_DIR / "crawl_knowledge.md"


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
            "# 🌍 全局高校教师邮箱爬取经验知识库 (Global Centralized Crawling Experience)\n",
            "\n",
            "本文件是由所有任务共同维护的全局经验共享文件。每当一个任务成功爬取完毕，"
            "系统会自动从中总结出可复用的最佳实践（包括特定高校官网的最优路径、HTML 选择器特征、反爬绕过方案等），"
            "以供后续新任务在执行前进行参考与学习。\n",
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
      with open(GLOBAL_SKILLS_FILE, "w", encoding="utf-8", newline="") as f:
        f.write(updated_text.replace(chr(0), ""))
      logger.info(f"Global skills knowledgebase updated for {uni_name}!")
    except OSError as e:
      logger.error(f"Global skills save failed: {e}")


def _generate_skills(task_id: str, task_data: dict) -> None:
    SKILLS_DIR.mkdir(exist_ok=True)

    # ── 每周清理一次无效 skill：删除 unknown_*.json，控制总数不超过 30 ──
    try:
        all_skills = sorted(SKILLS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
        # 删除所有 unknown_ 前缀的 JSON（由失败任务产生的无复用价值记录）
        for f in list(all_skills):
            if f.name.startswith("unknown_"):
                f.unlink()
                logger.info(f"清理无效 skill: {f.name}")
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

    # 1. 更新全局共享经验文件（Global shared experience file）
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

    # 导出到独立目录 __export__/{name}_{ts}/
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_task_id = f"__export__/{name}_{ts}"
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

    global_skills = _load_global_skills()

    if len(user_msgs) <= 1:
        # 新任务：如果有全局经验知识则在任务需求前注入
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
    # 追问场景：同样注入全局经验（最新知识库可能在上轮任务后有新增）
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

    user_message = ""
    for m in reversed(task_data.get("messages", [])):
        if m.get("role") == "user":
            user_message = m.get("content", "")
            break

    if not user_message:
        user_message = task_data.get("title", "no task found")

    prompt, first_user_msg, is_followup = _build_context_prompt(task_data, user_message, task_id)
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
        # 对追问重新分类：首条是爬取不代表本条也是（如"每个学院多少人"应该走问答）
        if is_followup:
            is_crawl = await agent._is_crawl_task(user_message)
        progress_stop = asyncio.Event()
        progress_task = None
        log_collector: list[str] = []  # 存放 agent 日志，供 LLM 进度生成使用
        if is_crawl:
            progress_task = asyncio.create_task(_progress_pump_llm(ws, progress_stop, log_collector))
        last_agent_line = ""
        downloads: list[dict] = []

        had_error = False
        # 聚合 text 消息（流式 token 先攒起来，done/error 时一次性写入历史）
        text_buffer: list[str] = []
        text_buffer_ts = ""  # 第一条 text 的时间戳
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
                    log_collector.append(text)  # 收集日志供 LLM 进度汇总
                logger.info("task %s agent: %s", task_id, text[:500])
            if msg_type == "text":
                text = log.get("message", "") or ""
                if text:
                    if not text_buffer:
                        text_buffer_ts = log.get("timestamp", "")
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
            agent.stop_task(task_id)
    else:
        # 正常完成：清除进程记录
        _running_agent_tasks.pop(task_id, None)
        _running_agent_info.pop(task_id, None)
        if hasattr(agent, "stop_task"):
            agent.stop_task(task_id)
