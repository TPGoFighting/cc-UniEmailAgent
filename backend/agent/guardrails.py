"""安全 Guardrails 系统 — 输入/输出内容安全检测与过滤。

InputGuardrail: 检测用户 prompt 中的注入攻击、敏感路径、危险操作
OutputGuardrail: 检测 Agent 输出中的手机号、身份证号等敏感信息
"""

import os
import re
import logging

logger = logging.getLogger(__name__)

GUARD_MODE = os.environ.get("GUARD_MODE", "log_only").strip().lower()
if GUARD_MODE not in ("log_only", "enforce"):
    logger.warning(f"无效的 GUARD_MODE='{GUARD_MODE}'，回退为 log_only")
    GUARD_MODE = "log_only"


# ═══════════════════════════════════════════════════
#  输入检测规则
# ═══════════════════════════════════════════════════

PROMPT_INJECTION_PATTERNS = [
    (r"ignore\s+all\s+previous\s+instructions?", "提示注入: 要求忽略先前指令"),
    (r"forget\s+everything", "提示注入: 要求忘记一切"),
    (r"system\s+prompt", "提示注入: 尝试获取系统提示"),
    (r"you\s+are\s+(now|programmed|configured)", "提示注入: 角色重新定义"),
    (r"disregard\s+(all\s+)?(previous|prior|above)", "提示注入: 要求无视上下文"),
    (r"override\s+your\s+(instructions?|settings?)", "提示注入: 覆盖指令"),
    (r"pretend\s+you\s+(are|were)", "提示注入: 角色扮演"),
    (r"act\s+as\s+if", "提示注入: 行为伪装"),
    (r"bypass\s+(all\s+)?(restrictions?|permissions?)", "提示注入: 绕过限制"),
    (r"do\s+not\s+(follow|obey)\s+(instructions?|rules?)", "提示注入: 要求不遵守规则"),
    (r"new\s+system\s+prompt", "提示注入: 新系统提示"),
    (r"reset\s+your\s+(instructions?|personality)", "提示注入: 重置指令"),
]

SENSITIVE_PATH_PATTERNS = [
    (r"/etc/(passwd|shadow|group|sudoers)", "敏感路径: Linux 系统文件"),
    (r"C:\\Windows\\(System32|system)", "敏感路径: Windows 系统目录"),
    (r"/root/\.ssh", "敏感路径: SSH 密钥"),
    (r"/var/log/(secure|auth\.log)", "敏感路径: 系统认证日志"),
    (r"/proc/(self|[\d]+)", "敏感路径: proc 文件系统"),
    (r"\.\./\.\./(etc|root|var)", "敏感路径: 路径遍历"),
    (r"%SystemRoot%", "敏感路径: Windows 系统根"),
    (r"%AppData%", "敏感路径: Windows 应用数据"),
    (r"~/.ssh", "敏感路径: SSH 目录"),
    (r"~/.aws", "敏感路径: AWS 凭证"),
    (r"/\.env\b", "敏感路径: 环境变量文件"),
]

DANGEROUS_OPERATIONS = [
    (r"\brm\s+-rf\b", "危险操作: 递归删除"),
    (r"\bchmod\s+777\b", "危险操作: 宽泛权限变更"),
    (r"\bdrop\s+(database|table)\b", "危险操作: 数据库删除"),
    (r"\bdelete\s+from\b", "危险操作: SQL 删除"),
    (r"\btruncate\s+table\b", "危险操作: SQL 截断"),
    (r"\bwget\s+.*\|\s*(sh|bash)\b", "危险操作: 远程脚本执行"),
    (r"\bcurl\s+.*\|\s*(sh|bash)\b", "危险操作: 远程脚本执行"),
    (r"\beval\s*\(.*\)", "危险操作: eval 执行"),
    (r"\bexec\s*\(.*\)", "危险操作: exec 执行"),
]


def check_input(text: str, enforce: bool | None = None) -> dict:
    """检测用户输入中的恶意内容。

    Args:
        text: 用户输入文本
        enforce: 强制执行模式（None 时读取 GUARD_MODE 环境变量）

    Returns:
        {"blocked": bool, "reason": str, "matched_rules": list[str]}
    """
    if not text:
        return {"blocked": False, "reason": "", "matched_rules": []}

    is_enforce = enforce if enforce is not None else (GUARD_MODE == "enforce")
    matched = []

    for pattern, label in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            matched.append(label)

    for pattern, label in SENSITIVE_PATH_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            matched.append(label)

    for pattern, label in DANGEROUS_OPERATIONS:
        if re.search(pattern, text, re.IGNORECASE):
            matched.append(label)

    blocked = len(matched) > 0
    reason = ""
    if blocked:
        reason = f"检测到 {len(matched)} 条安全规则匹配"
        if is_enforce:
            reason += " [已拦截]"
            logger.warning(f"[Guardrail:Input] {reason}: {matched}")
        else:
            reason += " [仅记录]"
            logger.info(f"[Guardrail:Input] {reason}: {matched}")

    return {
        "blocked": blocked,
        "reason": reason,
        "matched_rules": matched,
    }


# ═══════════════════════════════════════════════════
#  输出检测规则
# ═══════════════════════════════════════════════════

# 中国手机号: 1[3-9] 开头，共 11 位
_PHONE_RE = re.compile(r"1[3-9]\d{9}")

# 中国身份证号: 18 位（地区码 + 出生日期 + 顺序码 + 校验位）
_ID_RE = re.compile(r"[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]")


def check_output(text: str, enforce: bool | None = None) -> dict:
    """检测 Agent 输出中的敏感信息。

    Returns:
        {"blocked": bool, "reason": str, "matched_rules": list[str]}
    """
    if not text:
        return {"blocked": False, "reason": "", "matched_rules": []}

    is_enforce = enforce if enforce is not None else (GUARD_MODE == "enforce")
    matched = []

    phones = _PHONE_RE.findall(text)
    if phones:
        matched.append(f"检测到 {len(phones)} 个手机号")

    ids = _ID_RE.findall(text)
    if ids:
        matched.append(f"检测到 {len(ids)} 个身份证号")

    blocked = len(matched) > 0
    reason = ""
    if blocked:
        reason = f"检测到 {len(matched)} 类敏感信息"
        if is_enforce:
            reason += " [已拦截]"
            logger.warning(f"[Guardrail:Output] {reason}: {matched}")
        else:
            reason += " [已脱敏]"
            logger.info(f"[Guardrail:Output] {reason}: {matched}")

    return {
        "blocked": blocked,
        "reason": reason,
        "matched_rules": matched,
    }


def sanitize_output(text: str) -> str:
    """替换输出中的敏感信息为占位符。

    - 身份证号 → [ID-CARD]（必须先于手机号，避免生日段被误判为手机号）
    - 手机号 → [PHONE]
    """
    if not text:
        return text

    # 先替换身份证号再替换手机号（身份证中的生日段可能被手机正则误匹配）
    result = _ID_RE.sub("[ID-CARD]", text)
    result = _PHONE_RE.sub("[PHONE]", result)

    return result
