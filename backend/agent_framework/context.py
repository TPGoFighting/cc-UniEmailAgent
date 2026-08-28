"""对话上下文管理 — 参考 Claude Code 的 context.ts。

管理消息列表的增删改、token 预估、上下文裁剪。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """粗略预估 token 数（~4 chars/token for Chinese, ~3 for English）。"""
    chinese_chars = sum(1 for c in text if ord(c) > 0x4E00)
    other_chars = len(text) - chinese_chars
    return chinese_chars // 2 + other_chars // 3 + 10


def trim_messages(
    messages: list[dict[str, Any]],
    max_tokens: int = 32000,
    reserve_tokens: int = 4000,
) -> list[dict[str, Any]]:
    """裁剪消息列表到指定 token 预算。

    策略（参考 Claude Code 的 context collapse）:
    1. 保留 system prompt
    2. 保留最近的 N 轮对话
    3. 如果仍然超限，丢弃早期的 user/assistant 对
    """
    if not messages:
        return messages

    # 计算总 token
    total = sum(_msg_tokens(m) for m in messages)
    budget = max_tokens - reserve_tokens

    if total <= budget:
        return messages

    # 需要裁剪
    # 保留 system 和最近的对话
    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]

    # 从最早的消息开始丢弃
    trimmed = list(system_msgs)
    current_tokens = sum(_msg_tokens(m) for m in trimmed)

    # 保留最后 10 轮
    keep_count = min(len(non_system), 20)
    recent = non_system[-keep_count:]

    for m in recent:
        mt = _msg_tokens(m)
        if current_tokens + mt <= budget:
            trimmed.append(m)
            current_tokens += mt

    # 如果裁剪后仍然超限，强截
    while current_tokens > budget and len(trimmed) > len(system_msgs) + 2:
        removed = trimmed.pop(len(system_msgs))  # 从最早的非 system 消息开始删
        current_tokens -= _msg_tokens(removed)

    logger.info(f"上下文裁剪: {total} → {current_tokens} tokens（丢弃 {len(messages) - len(trimmed)} 条）")
    return trimmed


def _msg_tokens(msg: dict[str, Any]) -> int:
    """估算单条消息的 token 数。"""
    total = 10  # 基础开销
    content = msg.get("content", "")
    if isinstance(content, str):
        total += estimate_tokens(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                total += estimate_tokens(str(item.get("text", "")))

    # tool_calls
    for tc in msg.get("tool_calls", []):
        total += estimate_tokens(tc.get("function", {}).get("name", ""))
        total += estimate_tokens(str(tc.get("function", {}).get("arguments", "")))

    return total
