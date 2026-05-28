"""Runtime-only SMTP verification and send jobs."""

from __future__ import annotations

import asyncio
import csv
import io
import re
import smtplib
import ssl
import time
import uuid
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
VARIABLE_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
HIGH_VOLUME_THRESHOLD = 50

SMTP_PROVIDERS = {
    "qq.com": {"provider": "QQ 邮箱", "host": "smtp.qq.com", "port": 465, "secure": True},
    "foxmail.com": {"provider": "Foxmail / QQ 邮箱", "host": "smtp.qq.com", "port": 465, "secure": True},
    "163.com": {"provider": "网易 163", "host": "smtp.163.com", "port": 465, "secure": True},
    "126.com": {"provider": "网易 126", "host": "smtp.126.com", "port": 465, "secure": True},
    "yeah.net": {"provider": "网易 Yeah", "host": "smtp.yeah.net", "port": 465, "secure": True},
    "gmail.com": {"provider": "Gmail", "host": "smtp.gmail.com", "port": 465, "secure": True},
    "outlook.com": {"provider": "Outlook", "host": "smtp-mail.outlook.com", "port": 587, "secure": False},
    "hotmail.com": {"provider": "Hotmail", "host": "smtp-mail.outlook.com", "port": 587, "secure": False},
    "live.com": {"provider": "Microsoft Live", "host": "smtp-mail.outlook.com", "port": 587, "secure": False},
    "icloud.com": {"provider": "iCloud Mail", "host": "smtp.mail.me.com", "port": 587, "secure": False},
    "me.com": {"provider": "iCloud Mail", "host": "smtp.mail.me.com", "port": 587, "secure": False},
    "mac.com": {"provider": "iCloud Mail", "host": "smtp.mail.me.com", "port": 587, "secure": False},
}


@dataclass
class SmtpSession:
    host: str
    port: int
    secure: bool
    user: str
    password: str
    from_name: str
    verified_at: str


@dataclass
class SendJob:
    id: str
    status: str = "running"
    created_at: str = field(default_factory=lambda: _now_iso())
    updated_at: str = field(default_factory=lambda: _now_iso())
    totals: dict[str, int] = field(default_factory=lambda: {"total": 0, "sent": 0, "failed": 0, "skipped": 0, "pending": 0})
    logs: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""


smtp_sessions: dict[str, SmtpSession] = {}
send_jobs: dict[str, SendJob] = {}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(str(email or "").strip()))


def detect_smtp_provider(email: str) -> dict[str, Any]:
    match = re.search(r"@([^@\s]+)$", str(email or "").strip().lower())
    domain = match.group(1) if match else ""
    config = SMTP_PROVIDERS.get(domain)
    return {"domain": domain, "matched": bool(config), "provider": config["provider"] if config else "", "config": config}


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    return value is True or str(value).lower() in ("1", "true", "yes", "on")


def build_smtp_config(input_data: dict[str, Any]) -> dict[str, Any]:
    user = str(input_data.get("user", "")).strip()
    detected = detect_smtp_provider(user).get("config") or {}
    host = str(input_data.get("host") or detected.get("host") or "").strip()
    port = int(input_data.get("port") or detected.get("port") or 465)
    secure = _as_bool(input_data.get("secure", detected.get("secure")), port == 465)
    password = str(input_data.get("password") or input_data.get("pass") or "").replace(" ", "")
    from_name = str(input_data.get("fromName") or input_data.get("from_name") or user).strip()
    if not host or not port or not user or not password:
        raise ValueError("SMTP 配置不完整，请填写邮箱账号、授权码、Host、Port 和 SSL 设置。")
    if not is_valid_email(user):
        raise ValueError("发件邮箱格式不正确。")
    return {"host": host, "port": port, "secure": secure, "user": user, "password": password, "from_name": from_name}


def verify_smtp_config(input_data: dict[str, Any]) -> dict[str, Any]:
    smtp = build_smtp_config(input_data)
    try:
        if smtp["secure"]:
            server = smtplib.SMTP_SSL(smtp["host"], smtp["port"], timeout=15, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(smtp["host"], smtp["port"], timeout=15)
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
        with server:
            server.login(smtp["user"], smtp["password"])
    except smtplib.SMTPAuthenticationError as exc:
        raise ValueError("SMTP 认证失败，请确认使用的是授权码或应用专用密码。") from exc
    except OSError as exc:
        raise ValueError(f"SMTP 连接失败：{str(exc)[:120]}") from exc
    session_id = str(uuid.uuid4())
    smtp_sessions[session_id] = SmtpSession(**smtp, verified_at=_now_iso())
    return {
        "ok": True,
        "smtpSessionId": session_id,
        "smtp": {
            "host": smtp["host"],
            "port": smtp["port"],
            "secure": smtp["secure"],
            "user": smtp["user"],
            "fromName": smtp["from_name"],
            "hasPassword": True,
        },
    }


def render_template(template: str, row: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []

    def repl(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        aliases = {
            "学校": ("学校", "单位", "school", "company"),
            "姓名": ("姓名", "name"),
            "邮箱": ("邮箱", "email"),
            "学院": ("学院", "院系", "department"),
            "职称": ("职称", "title"),
        }.get(key, (key,))
        for alias in aliases:
            if alias in row and row[alias] not in (None, ""):
                return str(row[alias])
        missing.append(key)
        return ""

    return {"rendered": VARIABLE_RE.sub(repl, template), "missing": missing}


def _email_from_row(row: dict[str, Any]) -> str:
    for key in ("邮箱", "email", "Email", "EMAIL", "电子邮箱", "邮件"):
        if key in row:
            return str(row.get(key, "")).strip()
    for key, value in row.items():
        if "邮箱" in key or "email" in key.lower():
            return str(value or "").strip()
    return ""


def _name_from_row(row: dict[str, Any]) -> str:
    for key in ("姓名", "name", "Name"):
        if key in row:
            return str(row.get(key, "") or "")
    return ""


def build_preview(rows: list[dict[str, Any]], subject_template: str, body_template: str, limit: int = 10) -> dict[str, Any]:
    if not subject_template.strip() or not body_template.strip():
        raise ValueError("邮件主题和正文不能为空。")
    previews = []
    for idx, row in enumerate(rows[: max(1, min(limit, 50))], 1):
        subject = render_template(subject_template, row)
        body = render_template(body_template, row)
        email = _email_from_row(row)
        previews.append({
            "rowNumber": row.get("__rowNumber", idx),
            "email": email,
            "validEmail": is_valid_email(email),
            "subject": subject["rendered"],
            "body": body["rendered"],
            "missing": sorted(set(subject["missing"] + body["missing"])),
        })
    invalid_count = sum(1 for row in rows if not is_valid_email(_email_from_row(row)))
    return {
        "variables": sorted(set(VARIABLE_RE.findall(subject_template + body_template))),
        "previews": previews,
        "totalRows": len(rows),
        "invalidCount": invalid_count,
        "sendableCount": len(rows) - invalid_count,
        "threshold": HIGH_VOLUME_THRESHOLD,
    }


def create_send_job(
    *,
    rows: list[dict[str, Any]],
    subject_template: str,
    body_template: str,
    smtp_session_id: str,
    preview_confirmed: bool,
    confirmed: bool,
    high_volume_confirmed: bool = False,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or {}
    if not rows:
        raise ValueError("没有可发送的收件人数据。")
    if not preview_confirmed:
        raise ValueError("请先完成邮件预览确认。")
    if not confirmed:
        raise ValueError("发送前必须完成确认。")
    if not subject_template.strip() or not body_template.strip():
        raise ValueError("邮件主题和正文不能为空。")
    session = smtp_sessions.get(smtp_session_id)
    if not session:
        raise ValueError("请先完成 SMTP 测试连接，授权码不会落盘保存。")

    max_rows = int(settings.get("maxRows") or len(rows))
    candidate_rows = rows[: max(0, min(max_rows, len(rows)))]
    test_mode = bool(settings.get("testMode"))
    if test_mode:
        test_email = str(settings.get("testEmail") or "").strip()
        if not is_valid_email(test_email):
            raise ValueError("测试邮箱格式不正确。")
        sendable_count = min(int(settings.get("testLimit") or 1), len(candidate_rows))
    else:
        sendable_count = sum(1 for row in candidate_rows if is_valid_email(_email_from_row(row)))
    if not test_mode and sendable_count > HIGH_VOLUME_THRESHOLD and not high_volume_confirmed:
        raise ValueError(f"预计发送 {sendable_count} 封，超过阈值 {HIGH_VOLUME_THRESHOLD}，请再次确认。")

    job = SendJob(id=str(uuid.uuid4()))
    send_jobs[job.id] = job
    asyncio.create_task(_run_send_job(job.id, candidate_rows, subject_template, body_template, session, settings))
    return {"jobId": job.id, "sendableCount": sendable_count}


async def _send_one(session: SmtpSession, to: str, subject: str, body: str) -> None:
    def sync_send() -> None:
        msg = EmailMessage()
        msg["From"] = f"{session.from_name} <{session.user}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        if session.secure:
            server = smtplib.SMTP_SSL(session.host, session.port, timeout=20, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(session.host, session.port, timeout=20)
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
        with server:
            server.login(session.user, session.password)
            server.send_message(msg)

    await asyncio.to_thread(sync_send)


async def _run_send_job(job_id: str, rows: list[dict[str, Any]], subject_template: str, body_template: str, session: SmtpSession, settings: dict[str, Any]) -> None:
    job = send_jobs[job_id]
    test_mode = bool(settings.get("testMode"))
    recipients = rows[: int(settings.get("testLimit") or 1)] if test_mode else rows
    job.totals["total"] = len(recipients)
    job.totals["pending"] = len(recipients)
    interval_ms = max(0, int(settings.get("intervalMs") or 0))

    try:
        for idx, row in enumerate(recipients, 1):
            to = str(settings.get("testEmail") or "").strip() if test_mode else _email_from_row(row)
            subject = render_template(subject_template, row)["rendered"]
            body = render_template(body_template, row)["rendered"]
            log = {"rowNumber": row.get("__rowNumber", idx), "email": to, "name": _name_from_row(row), "subject": subject, "status": "pending", "reason": "", "sentAt": ""}
            job.logs.append(log)
            if not is_valid_email(to):
                _complete_log(job, log, "skipped", "邮箱为空或格式非法。")
                continue
            try:
                await _send_one(session, to, subject, body)
                _complete_log(job, log, "sent", "")
            except Exception as exc:
                _complete_log(job, log, "failed", str(exc)[:200])
            if interval_ms:
                await asyncio.sleep(interval_ms / 1000)
        job.status = "completed"
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)[:200]
    finally:
        job.totals["pending"] = 0
        job.updated_at = _now_iso()


def _complete_log(job: SendJob, log: dict[str, Any], status: str, reason: str) -> None:
    log["status"] = status
    log["reason"] = reason
    log["sentAt"] = _now_iso()
    job.totals["pending"] = max(0, job.totals["pending"] - 1)
    job.totals[status] = job.totals.get(status, 0) + 1
    job.updated_at = _now_iso()


def get_send_job(job_id: str) -> dict[str, Any] | None:
    job = send_jobs.get(job_id)
    if not job:
        return None
    return {
        "id": job.id,
        "status": job.status,
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
        "totals": job.totals,
        "logs": job.logs,
        "error": job.error,
    }


def export_send_job(job_id: str, fmt: str = "csv") -> tuple[str, bytes, str]:
    job = send_jobs.get(job_id)
    if not job:
        raise ValueError("未找到发送任务。")
    headers = ["rowNumber", "email", "name", "subject", "status", "reason", "sentAt"]
    if fmt == "xlsx":
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "send_logs"
        ws.append(headers)
        for log in job.logs:
            ws.append([log.get(h, "") for h in headers])
        bio = io.BytesIO()
        wb.save(bio)
        return f"send-logs-{job_id}.xlsx", bio.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    sio = io.StringIO()
    writer = csv.DictWriter(sio, fieldnames=headers)
    writer.writeheader()
    for log in job.logs:
        writer.writerow({h: log.get(h, "") for h in headers})
    return f"send-logs-{job_id}.csv", ("\ufeff" + sio.getvalue()).encode("utf-8"), "text/csv; charset=utf-8"
