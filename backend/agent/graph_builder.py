"""LangGraph 有向图定义 — plan → crawl → verify → export → complete。

纯状态机层：节点函数做轻量级状态转换，路由函数决定下一阶段。
实际的爬取执行（ClaudeAgent 流式调用）由 graph_agent.py 协调，
在节点间注入实时流式输出。
"""

import logging
from typing import TypedDict, Literal

from langgraph.graph import StateGraph, START, END

logger = logging.getLogger(__name__)

# ── 最大重试次数 ──
MAX_RETRIES = 3


class CrawlState(TypedDict, total=False):
    """LangGraph 状态 Schema。

    贯穿整个 plan→crawl→verify→export→complete 生命周期。
    """

    # ── 任务标识 ──
    task_id: str
    message: str                    # 用户原始消息（或 main.py 组装后的 prompt）

    # ── 感知上下文 ──
    university_name: str
    target_departments: list[str]

    # ── 流程控制 ──
    phase: str                      # plan | crawl | verify | export | complete
    retry_count: int
    error: str

    # ── 数据产物 ──
    crawl_data: list[dict]          # 爬取到的教师记录
    quality_report: dict | None     # evaluator 返回的质量报告
    output_files: list[str]         # 导出文件名列表


# ──────────────────────────────────────────────────────────────
# 节点函数
# ──────────────────────────────────────────────────────────────


def plan_node(state: CrawlState) -> dict:
    """接收意图 → 输出爬取策略。

    提取大学名称，设定初始策略。失败则标记 error 进入 complete。
    """
    uni = state.get("university_name", "")
    msg = state.get("message", "")

    if not uni:
        # 尝试从 message 中提取
        import re
        m = re.search(r"([一-鿿]{2,6}(?:大学|学院))", msg)
        uni = m.group(1) if m else ""

    if not uni:
        logger.warning("plan_node: 无法从消息中提取大学名称")
        return {"phase": "complete", "error": "无法识别目标大学"}

    logger.info(f"plan_node: → crawl, university={uni}")
    return {
        "phase": "crawl",
        "university_name": uni,
        "retry_count": state.get("retry_count", 0),
    }


def crawl_post_node(state: CrawlState) -> dict:
    """爬取完成后的状态更新：将阶段推进到 verify。

    实际的 ClaudeAgent 调用由 graph_agent 在节点间完成，
    此节点只做状态标记。
    """
    logger.info(f"crawl_post_node: → verify, task={state.get('task_id', '')[:8]}")
    return {"phase": "verify"}


def verify_node(state: CrawlState) -> dict:
    """质量门：调用 evaluator.validate_crawl_output。

    检查：
    1. 邮箱覆盖率是否 ≥ 70%
    2. 是否有脏数据冒充教师姓名
    3. 邮箱格式是否合法
    4. 学院覆盖是否达标
    """
    import csv
    from pathlib import Path
    from agent.evaluator import validate_crawl_output

    task_id = state.get("task_id", "")
    target_depts = state.get("target_departments", []) or None

    output_dir = Path(__file__).parent.parent / "outputs" / task_id.replace("/", "_").replace("\\", "_")
    csv_files = list(output_dir.glob("*.csv")) if output_dir.exists() else []

    if not csv_files:
        logger.info("verify_node: 无 CSV 文件，跳过验证")
        return {
            "phase": "export",
            "quality_report": {"passed": True, "quality_score": 0, "warnings": ["无数据文件可验证"]},
        }

    # 对每个 CSV 文件运行评估
    reports = []
    for csv_file in csv_files:
        uni_config = {"departments": target_depts} if target_depts else None
        report = validate_crawl_output(str(csv_file), task_id, uni_config)
        reports.append(report)

    # 取综合结果
    best = max(reports, key=lambda r: r.get("quality_score", 0)) if reports else {}
    all_warnings = []
    for r in reports:
        all_warnings.extend(r.get("warnings", []))

    merged = {
        "passed": all(r.get("passed", True) for r in reports),
        "quality_score": best.get("quality_score", 0),
        "warnings": all_warnings,
    }

    passed = merged["passed"]
    retry = state.get("retry_count", 0)

    if passed:
        logger.info(f"verify_node: passed (score={merged['quality_score']}) → export")
        return {"phase": "export", "quality_report": merged}
    elif retry < MAX_RETRIES:
        logger.info(f"verify_node: failed, retry {retry+1}/{MAX_RETRIES} → plan")
        return {
            "phase": "plan",
            "quality_report": merged,
            "error": f"质量验证未通过（得分 {merged['quality_score']}），重试第 {retry+1} 次",
        }
    else:
        logger.info(f"verify_node: max retries ({MAX_RETRIES}) exceeded → complete")
        return {
            "phase": "complete",
            "quality_report": merged,
            "error": f"质量验证未通过，已达最大重试次数（{MAX_RETRIES}）",
        }


def export_node(state: CrawlState) -> dict:
    """导出为 CSV/XLSX 文件。

    读取 outputs/{task_id}/ 下的 CSV，调用 exporter.export_all 生成多格式。
    """
    import csv
    from pathlib import Path
    from agent.exporter import export_all

    task_id = state.get("task_id", "")
    uni = state.get("university_name", "unknown")

    output_dir = Path(__file__).parent.parent / "outputs" / task_id.replace("/", "_").replace("\\", "_")
    csv_files = list(output_dir.glob("*.csv")) if output_dir.exists() else []

    data: list[dict] = []
    for csv_file in csv_files:
        try:
            with open(csv_file, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    data.append({
                        "name": row.get("姓名", row.get("name", "")),
                        "email": row.get("邮箱", row.get("email", "")),
                        "department": row.get("学院", row.get("department", "")),
                        "title": row.get("职称", row.get("title", "")),
                        "url": row.get("主页链接", row.get("url", "")),
                    })
        except Exception as e:
            logger.warning(f"export_node: 读取 {csv_file.name} 失败: {e}")

    if not data:
        logger.info("export_node: 无数据可导出 → complete")
        return {"phase": "complete", "output_files": []}

    try:
        result = export_all(data, uni, task_id)
        files = list(result.values())
        logger.info(f"export_node: 导出完成，{len(files)} 个文件 → complete")
        return {"phase": "complete", "output_files": files}
    except Exception as e:
        logger.error(f"export_node: 导出失败: {e}")
        return {"phase": "complete", "output_files": [], "error": str(e)}


# ──────────────────────────────────────────────────────────────
# 路由函数（条件边）
# ──────────────────────────────────────────────────────────────


def route_after_plan(state: CrawlState) -> Literal["crawl", "complete"]:
    """plan 之后：
    - 无 error → crawl
    - 有 error（无法识别大学）→ complete
    """
    if state.get("error"):
        logger.info("route: plan → complete (error)")
        return "complete"
    logger.info("route: plan → crawl")
    return "crawl"


def route_after_crawl(state: CrawlState) -> Literal["verify", "complete"]:
    """crawl 之后：
    - 通过 post_crawl 正常完成 → verify
    - 有 error → complete
    """
    if state.get("error"):
        logger.info("route: crawl → complete (error)")
        return "complete"
    logger.info("route: crawl → verify")
    return "verify"


def route_after_verify(state: CrawlState) -> Literal["export", "plan", "complete"]:
    """verify 之后：
    - passed → export
    - failed + 未达上限 → plan（重试）
    - failed + 达上限 → complete
    """
    report = state.get("quality_report") or {}
    if report.get("passed"):
        logger.info("route: verify → export (passed)")
        return "export"
    retry = state.get("retry_count", 0)
    if retry < MAX_RETRIES:
        logger.info(f"route: verify → plan (retry {retry+1}/{MAX_RETRIES})")
        return "plan"
    logger.info("route: verify → complete (max retries)")
    return "complete"


# ──────────────────────────────────────────────────────────────
# 图构建
# ──────────────────────────────────────────────────────────────


def build_graph() -> StateGraph:
    """构建并编译 LangGraph 有向图。

    图结构:
        START → plan → crawl → verify → export → END
                    ↑                  │
                    └── retry ─────────┘
    """
    graph = StateGraph(CrawlState)

    # 添加节点
    graph.add_node("plan", plan_node)
    graph.add_node("crawl", crawl_post_node)
    graph.add_node("verify", verify_node)
    graph.add_node("export", export_node)

    # 起始边
    graph.add_edge(START, "plan")

    # 条件边: plan → crawl 或 complete
    graph.add_conditional_edges("plan", route_after_plan, {
        "crawl": "crawl",
        "complete": END,
    })

    # 条件边: crawl → verify 或 complete
    graph.add_conditional_edges("crawl", route_after_crawl, {
        "verify": "verify",
        "complete": END,
    })

    # 条件边: verify → export / plan / complete
    graph.add_conditional_edges("verify", route_after_verify, {
        "export": "export",
        "plan": "plan",
        "complete": END,
    })

    # export → END
    graph.add_edge("export", END)

    compiled = graph.compile()
    logger.info("LangGraph 有向图编译完成: plan→crawl→verify→export→complete")
    return compiled
