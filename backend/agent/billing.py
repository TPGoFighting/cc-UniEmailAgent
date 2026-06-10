"""Token 计费与统计管理器。

通过 Monkeypatch 拦截所有 OpenAI SDK 的聊天调用，自动提取并累计 Token 消耗，
支持多任务上下文隔离与未来官方云计费对接。
"""

import logging
from typing import Optional
from contextvars import ContextVar

logger = logging.getLogger(__name__)

# 用于在异步协程上下文中隐式传递当前的任务 ID，防止侵入业务逻辑
current_task_id: ContextVar[str] = ContextVar("current_task_id", default="")

# 内存会话计数器（程序本次运行以来的总消耗）
_session_stats = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
}

def record_token_usage(prompt_tokens: int, completion_tokens: int, task_id: Optional[str] = None):
    """记录一次大模型交互消耗的 Token 数，并持久化到任务历史中。"""
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return

    global _session_stats
    total_tokens = prompt_tokens + completion_tokens

    # 累加会话消耗
    _session_stats["prompt_tokens"] += prompt_tokens
    _session_stats["completion_tokens"] += completion_tokens
    _session_stats["total_tokens"] += total_tokens

    logger.info(
        f"[Billing] Token 统计 -> 输入: {prompt_tokens}, 输出: {completion_tokens}, 本次: {total_tokens}. "
        f"当前任务: {task_id or '全局'}, 累计: {_session_stats['total_tokens']}"
    )

    # 累加到特定任务数据中
    if task_id:
        from agent.history import history
        try:
            task = history.get(task_id)
            if task:
                usage = task.get("token_usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
                usage["prompt_tokens"] += prompt_tokens
                usage["completion_tokens"] += completion_tokens
                usage["total_tokens"] += total_tokens
                task["token_usage"] = usage
                history._save(task)
        except Exception as e:
            logger.warning(f"写入任务 {task_id} 的 Token 统计失败: {e}")

    # ── 官方云端计费扩展点 (Billing Hook) ──
    try:
        from agent.config import load_config, save_config
        config = load_config()
        if config.get("service_mode") == "cloud":
            # 30倍溢价费率：输入 30元/M, 输出 60元/M
            input_cost = (prompt_tokens * 30.0 / 1_000_000)
            output_cost = (completion_tokens * 60.0 / 1_000_000)
            total_cost = input_cost + output_cost
            
            config["balance_yuan"] = max(0.0, config.get("balance_yuan", 5.00) - total_cost)
            save_config(config)
            logger.info(f"[Billing] 官方云服务扣费 -> 输入消耗: {prompt_tokens}, 输出消耗: {completion_tokens}, 扣除金额: {total_cost:.4f} 元, 剩余余额: {config['balance_yuan']:.2f} 元")
    except Exception as e:
        logger.warning(f"执行官方计费扣款失败: {e}")

def get_session_token_usage() -> dict:
    """获取当前程序启动以来的总 Token 消耗。"""
    return _session_stats

# ── Monkeypatch 注入 ──
_patched = False

def init_billing_patch():
    """初始化大模型接口拦截，自动审计 Token 消耗。"""
    global _patched
    if _patched:
        return
    try:
        from openai.resources.chat.completions import AsyncCompletions
        original_create = AsyncCompletions.create

        async def patched_create(self, *args, **kwargs):
            response = await original_create(self, *args, **kwargs)
            try:
                if hasattr(response, "usage") and response.usage:
                    prompt = response.usage.prompt_tokens
                    completion = response.usage.completion_tokens
                    # 获取当前协程关联的 task_id
                    tid = current_task_id.get()
                    record_token_usage(prompt, completion, tid)
            except Exception as err:
                logger.warning(f"拦截并记录 Token 失败: {err}")
            return response

        AsyncCompletions.create = patched_create
        _patched = True
        logger.info("成功注入 OpenAI AsyncCompletions.create，已开启自动计费审计。")
    except Exception as e:
        logger.error(f"注入大模型计费审计失败: {e}")
