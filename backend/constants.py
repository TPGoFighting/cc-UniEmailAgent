"""项目共享常量和工具函数。

所有模块统一从此处导入正则、常量、工具函数，避免重复定义。
"""

import re

# ── 大学名匹配 ──
UNIVERSITY_NAME_RE = re.compile(
    r"([一-鿿]{2,4}(?:大学|学院|师范大学|科技大学|理工大学|工业大学|农业大学|医科大学|财经大学|外国语大学))"
)

DEPARTMENT_NAME_RE = re.compile(
    r"([一-鿿]{2,15}(?:学院|系|中心|研究所|研究室|实验室|部))"
)

# ── 邮箱验证 ──
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

ADMIN_EMAIL_PREFIXES = {
    "webmaster", "admin", "office", "info", "master", "root",
    "postmaster", "bgs", "dangzheng", "yuanban", "wxyxz", "xwcb",
    "yanjiu", "support", "contact", "hr", "service",
}


def is_valid_email_format(email: str) -> bool:
    """统一邮箱格式校验。"""
    if not email or not isinstance(email, str):
        return False
    return bool(EMAIL_RE.match(email.strip()))


def is_admin_or_public_email(email: str) -> bool:
    """判断是否为教务/公共邮箱。"""
    if not email or "@" not in email:
        return False
    local_part = email.strip().lower().split("@")[0]
    return local_part in ADMIN_EMAIL_PREFIXES
