"""UniEmail Agent — FastAPI 后端服务 (Phase 5: 任务隔离 + 持久化 + 分页)"""

import os
import re
import uuid
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent.claude_agent import ClaudeAgent
from agent.exporter import get_task_dir, cleanup_task_dir, _BASE_OUTPUT_DIR
from agent.history import history

# 日志配置
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局 Agent 实例
agent = ClaudeAgent()

# 正在执行 Agent 的任务 ID 集合（防止同一任务重复执行）
_running_agent_tasks: set[str] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("UniEmail Agent 后端启动")
    yield
    logger.info("UniEmail Agent 后端关闭")


app = FastAPI(title="UniEmail Agent", version="0.2.0", lifespan=lifespan)

# CORS — 允许前端跨域访问，从环境变量读取（逗号分隔）
cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# —————————————————————— 数据模型 ——————————————————————


class ChatRequest(BaseModel):
    message: str
    task_id: str | None = None


class ChatResponse(BaseModel):
    task_id: str


class RenameRequest(BaseModel):
    title: str


# —————————————————————— 路由 ——————————————————————


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/history")
async def get_history():
    """获取所有历史任务列表（不含消息内容）。"""
    tasks_list = history.get_all()
    return {"tasks": tasks_list}


@app.get("/api/history/search")
async def search_history(q: str = ""):
    """搜索历史任务。"""
    results = history.search(q)
    return {"tasks": results}


@app.get("/api/history/{task_id}")
async def get_history_task(
    task_id: str,
    limit: int = Query(default=0, ge=0, description="返回消息数量上限，0=全部"),
    offset: int = Query(default=0, ge=0, description="跳过的消息数量"),
):
    """获取指定任务的完整记录（含消息），支持分页。"""
    task = history.get(task_id)
    if task is None:
        return {"error": "任务不存在"}

    # 规范化消息：确保每条消息都有 role 字段
    messages = task.get("messages", [])
    total = len(messages)

    # 分页
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
        return {"error": "任务不存在"}
    return {"ok": True, "task": task}


@app.patch("/api/history/{task_id}/pin")
async def pin_task(task_id: str):
    task = history.toggle_pin(task_id)
    if task is None:
        return {"error": "任务不存在"}
    return {"ok": True, "pinned": task.get("pinned", False)}


@app.delete("/api/history/{task_id}")
async def delete_task(task_id: str):
    """删除任务，同时清理其输出文件。"""
    cleanup_task_dir(task_id)
    ok = history.delete_task(task_id)
    return {"ok": ok}


@app.post("/api/chat", response_model=ChatResponse)
async def create_task(req: ChatRequest):
    """接收用户消息，创建或复用任务并返回 task_id。

    任务消息持久化到 history，后端重启后可恢复。
    """
    task_id = req.task_id or str(uuid.uuid4())
    user_content = req.message or "新建任务"

    existing = history.get(task_id)
    if existing is None:
        history.create_task(task_id, user_content)
    else:
        history.update_status(task_id, "running")

    # 总是将用户消息追加到任务（无论新建还是追问）
    history.add_message(task_id, {
        "id": f"user-{task_id[:8]}-{len(existing.get('messages', [])) if existing else 0}",
        "role": "user",
        "content": user_content,
    })

    logger.info(f"任务 {task_id}: {req.message}")
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
    """安全解析路径，防止路径遍历。"""
    p = base.resolve()
    for part in parts:
        p = (p / part).resolve()
        if not str(p).startswith(str(base.resolve()) + os.sep) and p != base.resolve():
            return None
    return p


@app.get("/api/download/{task_id}/{filename:path}")
async def download_file_tasked(task_id: str, filename: str):
    """下载任务专属目录中的文件。"""
    if ".." in filename or ".." in task_id:
        return {"error": "无效的文件名"}
    safe_tid = task_id.replace("/", "_").replace("\\", "_").replace("..", "_")
    base = _BASE_OUTPUT_DIR.resolve()
    filepath = _safe_resolve(base, safe_tid, filename)
    if filepath is None or not filepath.exists():
        return {"error": "文件不存在"}
    ext = filepath.suffix.lower()
    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type=MIME_MAP.get(ext, "application/octet-stream"),
    )


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """下载根 outputs/ 目录中的文件（兼容旧版无 task_id 的链接）。"""
    if ".." in filename or "/" in filename or "\\" in filename:
        return {"error": "无效的文件名"}
    base = _BASE_OUTPUT_DIR.resolve()
    filepath = _safe_resolve(base, filename)
    if filepath is None or not filepath.exists():
        return {"error": "文件不存在"}
    ext = filepath.suffix.lower()
    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type=MIME_MAP.get(ext, "application/octet-stream"),
    )


# —————————————————————— Skills 管理 ——————————————————————


SKILLS_DIR = Path(__file__).parent / "skills"


def _generate_skills(task_id: str, task_data: dict) -> None:
    """从已完成任务中提取可复用知识，保存到全局 skills/ 目录。

    提取内容：发现的大学 URL、有效导航关键词、院系列表等。
    """
    SKILLS_DIR.mkdir(exist_ok=True)

    messages = task_data.get("messages", [])
    user_msg = ""
    for m in messages:
        if m.get("role") == "user":
            user_msg = m.get("content", "")
            break

    # 提取大学名称
    uni_name = "unknown"
    for m in messages:
        content = m.get("content", "")
        if "大学" in content or "学院" in content:
            import re
            match = re.search(r"([一-鿿]{2,4}(?:大学|学院))", content)
            if match:
                uni_name = match.group(1)
                break

    # 收集下载文件信息
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
        "extracted_at": __import__("datetime").datetime.now().isoformat(),
    }

    skill_file = SKILLS_DIR / f"{uni_name}_{task_id[:8]}.json"
    try:
        with open(skill_file, "w", encoding="utf-8") as f:
            json.dump(skill, f, ensure_ascii=False, indent=2)
        logger.info(f"Skill 已生成: {skill_file.name}")
    except OSError as e:
        logger.error(f"Skill 保存失败: {e}")


@app.get("/api/skills")
async def list_skills():
    """列出所有已生成的 skills。"""
    SKILLS_DIR.mkdir(exist_ok=True)
    skills = []
    for f in sorted(SKILLS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                skills.append(json.load(fp))
        except Exception:
            pass
    return {"skills": skills}


# —————————————————————— WebSocket ——————————————————————


def _build_context_prompt(task_data: dict, latest_user_msg: str) -> tuple[str, str, bool]:
    """为追问构建上下文 prompt。返回 (prompt, original_first_msg, is_followup)。

    首次对话：直接返回用户消息，不注入额外上下文。
    追问：注入历史摘要 + 产物清单，让 Agent 理解当前任务状态。
    """
    messages = task_data.get("messages", [])
    user_msgs = [m for m in messages if m.get("role") == "user"]

    # 只有 1 条用户消息 → 首次对话，不注入上下文
    if len(user_msgs) <= 1:
        return latest_user_msg, latest_user_msg, False

    # ── 构建追问上下文 ──
    lines = [
        "## 任务上下文（同一任务的后续追问）\n",
        "以下是本任务已完成工作的摘要，请基于此上下文处理当前请求：\n",
    ]

    # 历史用户需求
    prev_requests = [m.get("content", "") for m in user_msgs[:-1]]
    if prev_requests:
        lines.append("### 之前的需求")
        for i, req in enumerate(prev_requests, 1):
            lines.append(f"{i}. {req[:200]}")
        lines.append("")

    # 已生成的下载文件
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

    # Agent 的最后回复（截取关键信息）
    agent_msgs = [m for m in messages if m.get("role") == "agent" and m.get("content")]
    if agent_msgs:
        last = agent_msgs[-1].get("content", "")
        # 取前 800 字符，优先截断在换行处
        if len(last) > 800:
            last = last[:800].rsplit("\n", 1)[0]
        lines.append("### 上次任务的回复摘要")
        lines.append(last)
        lines.append("")

    lines.append(f"### 当前请求\n{latest_user_msg}\n")
    lines.append("请基于以上上下文处理当前请求。你可以引用或操作之前生成的文件。")
    lines.append("")
    lines.append(
        "### 📁 文件分享（必须严格遵守）\n"
        "任务完成时，用 [FILES]...[/FILES] 标记块列出要提供给用户下载的文件。\n"
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
    """检测用户消息中是否包含请求已有文件的操作。

    匹配 Windows 绝对路径（盘符:\\...\\文件名.扩展名），验证文件在 outputs/ 下且存在。
    返回 [{"path": Path, "task_id": str, "filename": str, "url": str}, ...]
    """
    base = _BASE_OUTPUT_DIR.resolve()
    results: list[dict] = []

    # 匹配双引号包裹的 Windows 绝对路径
    quoted = re.findall(r'["""]([A-Za-z]:\\[^"""]+?\.[a-zA-Z0-9]+)[""""]', message)
    # 匹配未被引号包裹的 Windows 绝对路径
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

        # 安全检查：必须在 _BASE_OUTPUT_DIR 下
        try:
            rel = p.relative_to(base)
        except ValueError:
            continue

        parts = rel.parts
        # 提取 task_id（outputs/ 下的第一级子目录）和文件路径
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


@app.websocket("/ws/{task_id}")
async def agent_logs(ws: WebSocket, task_id: str):
    """WebSocket 端点：实时推送 Agent 日志，任务结束后生成 skill。"""
    await ws.accept()
    logger.info(f"WebSocket 连接: {task_id}")

    # 从 history 恢复任务消息（支持后端重启后重连）
    task_data = history.get(task_id)
    if task_data is None:
        await ws.send_text(
            json.dumps({"type": "error", "message": "任务不存在，请重新发送"}, ensure_ascii=False)
        )
        await ws.close()
        return

    # 从消息历史中取最新的用户消息
    user_message = ""
    for m in reversed(task_data.get("messages", [])):
        if m.get("role") == "user":
            user_message = m.get("content", "")
            break

    if not user_message:
        user_message = task_data.get("title", "未找到任务")

    # 构建上下文（追问时注入历史 + 产物摘要）
    prompt, first_user_msg, is_followup = _build_context_prompt(task_data, user_message)

    # ── 检测文件请求：如果用户消息中包含 outputs/ 下的有效文件路径，直接推送下载 ──
    file_requests = _detect_file_request(user_message)

    # ── 防止重复执行：同一任务已有 Agent 在运行则拒绝 ──
    if task_id in _running_agent_tasks:
        logger.warning(f"任务 {task_id} 已在执行中，拒绝重复 WebSocket 连接")
        await ws.send_text(
            json.dumps({"type": "error", "message": "任务已在执行中"}, ensure_ascii=False)
        )
        await ws.close()
        return

    _running_agent_tasks.add(task_id)

    try:
        msg_seq = 0

        if file_requests:
            # 跳过 Agent 执行，直接推送下载链接
            logger.info(f"任务 {task_id}: 检测到文件请求，跳过 Agent，共 {len(file_requests)} 个文件")
            from datetime import datetime as _dt
            ts = _dt.now().strftime("%H:%M:%S")
            for fr in file_requests:
                log = {
                    "type": "download",
                    "message": f"📎 {fr['filename']}",
                    "filename": fr["filename"],
                    "url": fr["url"],
                    "timestamp": ts,
                }
                await ws.send_text(json.dumps(log, ensure_ascii=False))
                msg_seq += 1
                history.add_message(task_id, {
                    "id": f"download-{task_id[:8]}-{ts}-{msg_seq}",
                    "role": "download",
                    "content": log["message"],
                    "timestamp": ts,
                    "filename": fr["filename"],
                    "url": fr["url"],
                })
            # 推送完成消息
            done_msg = {"type": "done", "message": "文件已发送", "timestamp": ts}
            await ws.send_text(json.dumps(done_msg, ensure_ascii=False))
            history.add_message(task_id, {
                "id": f"done-{task_id[:8]}-{ts}",
                "role": "agent",
                "content": "文件已发送",
                "timestamp": ts,
            })
            history.update_status(task_id, "completed")
            await ws.close()
            return

        # 仅在首次对话时清理输出目录，追问保留之前生成的文件
        if not is_followup:
            cleanup_task_dir(task_id)
            get_task_dir(task_id)  # 预创建目录，Agent 无需再 mkdir

        # 确保 user 消息已持久化
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

        async for log in agent.execute(prompt, task_id, is_continuation=is_followup):
            await ws.send_text(json.dumps(log, ensure_ascii=False))
            msg_seq += 1
            msg_type = log.get("type", "agent")
            role_map = {"log": "log", "download": "download", "error": "agent", "done": "agent"}
            history.add_message(task_id, {
                "id": f"{msg_type}-{task_id[:8]}-{log.get('timestamp', '')}-{msg_seq}",
                "role": role_map.get(msg_type, "log"),
                "content": log.get("message", ""),
                "timestamp": log.get("timestamp", ""),
                "filename": log.get("filename", ""),
                "url": log.get("url", ""),
            })

        # 任务成功完成
        history.update_status(task_id, "completed")

        # 生成 skill 供其他任务参考
        final_task = history.get(task_id)
        if final_task:
            _generate_skills(task_id, final_task)

        await ws.close()

    except WebSocketDisconnect:
        logger.info(f"WebSocket 断开: {task_id}")
        history.update_status(task_id, "failed")
    except Exception as e:
        err_detail = f"{type(e).__name__}: {str(e)[:300]}"
        logger.error(f"WebSocket 错误 {task_id}: {err_detail}")
        history.update_status(task_id, "failed")
        try:
            await ws.send_text(
                json.dumps({"type": "error", "message": f"执行出错: {err_detail}"}, ensure_ascii=False)
            )
        except Exception:
            pass
        await ws.close()
    finally:
        _running_agent_tasks.discard(task_id)