"""LangSmith 全链路追踪客户端单例。

所有函数 try/except 兜底，失败时静默退化，绝不影响主流程。
通过环境变量配置：LANGCHAIN_TRACING_V2=true, LANGCHAIN_API_KEY, LANGCHAIN_PROJECT=UniEmailAgent
"""

import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    """延迟初始化 LangSmith Client 单例。"""
    global _client
    if _client is None:
        try:
            if os.environ.get("LANGCHAIN_TRACING_V2") == "true" and os.environ.get("LANGCHAIN_API_KEY"):
                from langsmith import Client
                _client = Client()
                logger.info("LangSmith 追踪已启用 (project=%s)", os.environ.get("LANGCHAIN_PROJECT", "UniEmailAgent"))
            else:
                logger.debug("LangSmith 未配置（缺少 LANGCHAIN_TRACING_V2 或 LANGCHAIN_API_KEY），追踪静默跳过")
        except Exception as e:
            logger.warning("LangSmith 初始化失败: %s", e)
    return _client


def get_tracer():
    """返回 LangSmith Client 实例（用于测试导入和手动操作）。"""
    return _get_client()


def create_run(name: str, inputs: dict | None = None, run_type: str = "chain") -> str | None:
    """创建顶层追踪 Run，返回 run_id。失败返回 None。"""
    try:
        client = _get_client()
        if client is None:
            return None
        run = client.create_run(
            name=name,
            inputs=inputs or {},
            run_type=run_type,
            project_name=os.environ.get("LANGCHAIN_PROJECT", "UniEmailAgent"),
        )
        run_id = str(run.id) if hasattr(run, "id") else str(run)
        logger.debug("LangSmith run created: %s (%s)", name, run_id[:8])
        return run_id
    except Exception as e:
        logger.debug("create_run 失败（已静默跳过）: %s", e)
        return None


def end_run(run_id: str | None, outputs: dict | None = None, error: str | None = None) -> None:
    """结束顶层 Run。"""
    if run_id is None:
        return
    try:
        client = _get_client()
        if client is None:
            return
        client.update_run(
            run_id,
            outputs=outputs,
            error=error,
            end_time=datetime.now(timezone.utc),
        )
        logger.debug("LangSmith run ended: %s", run_id[:8])
    except Exception as e:
        logger.debug("end_run 失败（已静默跳过）: %s", e)


def start_span(name: str, inputs: dict | None = None, parent_run_id: str | None = None) -> str | None:
    """创建子 Span，返回 span_id。失败返回 None。"""
    try:
        client = _get_client()
        if client is None:
            return None
        kwargs: dict = {
            "name": name,
            "inputs": inputs or {},
            "run_type": "span",
            "project_name": os.environ.get("LANGCHAIN_PROJECT", "UniEmailAgent"),
        }
        if parent_run_id:
            kwargs["parent_run_id"] = parent_run_id
        run = client.create_run(**kwargs)
        span_id = str(run.id) if hasattr(run, "id") else str(run)
        logger.debug("LangSmith span started: %s (%s)", name, span_id[:8])
        return span_id
    except Exception as e:
        logger.debug("start_span 失败（已静默跳过）: %s", e)
        return None


def end_span(span_id: str | None, outputs: dict | None = None, error: str | None = None) -> None:
    """结束 Span。"""
    if span_id is None:
        return
    try:
        client = _get_client()
        if client is None:
            return
        client.update_run(
            span_id,
            outputs=outputs,
            error=error,
            end_time=datetime.now(timezone.utc),
        )
        logger.debug("LangSmith span ended: %s", span_id[:8])
    except Exception as e:
        logger.debug("end_span 失败（已静默跳过）: %s", e)


def get_trace_url(run_id: str | None) -> str:
    """根据 run_id 生成 LangSmith Dashboard 链接。"""
    if not run_id:
        return ""
    project = os.environ.get("LANGCHAIN_PROJECT", "UniEmailAgent")
    return f"https://smith.langchain.com/projects/p/{project}/r/{run_id}?tab=traces"
