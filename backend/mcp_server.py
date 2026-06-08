""""UniEmail Agent MCP Server — 将爬虫能力封装为标准 MCP 协议。

通过标准 MCP 协议暴露 Tools / Resources / Prompts:
  - Tool: crawl_faculty_emails — 爬取指定大学学院的教师邮箱
  - Tool: query_crawl_result   — 查询已有爬取结果
  - Tool: export_crawl_data    — 导出为 CSV 或 XLSX
  - Resource: crawl://results/{task_id}      — 查看任务结果文件列表
  - Resource: crawl://outputs/{task_id}/{filename} — 读取具体输出文件
  - Prompt: crawl_prompt       — 生成爬取任务提示词

使用方式:
  from mcp_server import create_mcp_server
  mcp = create_mcp_server()           # 默认实例 (host=127.0.0.1, port=8000)
  mcp = create_mcp_server(port=8011)  # 自定义端口
"""

import os
import sys
import json
import uuid
import csv as csv_module
import logging
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp import Context as MCPContext
from mcp.server.fastmcp.prompts import Prompt
from mcp.server.fastmcp.resources import FunctionResource

# 确保 backend 目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.exporter import get_task_dir, export_csv, export_xlsx, _BASE_OUTPUT_DIR
from agent.history import history

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_server")

# —————————————————————————— 工具函数实现 ——————————————————————————


async def _crawl_faculty_emails(
    university: str,
    college: str = "",
    query: str = "",
    ctx: MCPContext | None = None,
) -> str:
    """爬取指定大学学院的教师邮箱。"""
    task_id = str(uuid.uuid4())
    message_parts = [f"抓取 {university}"]
    if college:
        message_parts.append(f" {college}")
    message_parts.append(" 教师邮箱")
    if query:
        message_parts.append(f"，附加条件：{query}")
    message = "".join(message_parts)

    if ctx:
        await ctx.info(f"创建任务 {task_id}，目标：{message}")

    # 自动选择 Agent：优先 ClaudeAgent，不可用时回退 PlaywrightAgent
    try:
        import shutil
        if shutil.which("claude"):
            from agent.claude_agent import ClaudeAgent
            agent = ClaudeAgent()
            agent_type = "claude"
        else:
            raise FileNotFoundError("claude CLI not found")
    except Exception:
        from agent.playwright_agent import PlaywrightAgent
        agent = PlaywrightAgent()
        agent_type = "playwright"

    logs: list[str] = []
    status = "completed"

    try:
        async for chunk in agent.execute(message, task_id):
            if chunk.get("type") == "log":
                logs.append(chunk.get("message", ""))
                if ctx:
                    await ctx.info(chunk["message"])
            elif chunk.get("type") == "download":
                logs.append(f"下载: {chunk.get('filename', '')}")
                if ctx:
                    await ctx.info(f"下载文件: {chunk.get('filename', '')}")
            elif chunk.get("type") == "done":
                logs.append(chunk.get("message", ""))
            elif chunk.get("type") == "error":
                logs.append(f"错误: {chunk.get('message', '')}")
                status = "failed"
                if ctx:
                    await ctx.error(chunk["message"])
    except Exception as e:
        status = "failed"
        logs.append(f"执行异常: {e}")
        if ctx:
            await ctx.error(str(e))

    task_dir = get_task_dir(task_id)
    output_files: list[str] = []
    if task_dir.exists():
        for f in sorted(task_dir.iterdir()):
            if f.is_file():
                output_files.append(f.name)

    result = {
        "task_id": task_id,
        "university": university,
        "college": college or "全部",
        "status": status,
        "agent": agent_type,
        "output_files": output_files,
        "output_dir": str(task_dir),
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


async def _query_crawl_result(task_id: str, keyword: str = "") -> str:
    """查询已有爬取结果。"""
    task = history.get(task_id)
    if not task:
        return json.dumps({"error": f"任务 {task_id} 不存在"}, ensure_ascii=False)

    task_dir = get_task_dir(task_id)
    output_files: list[dict[str, Any]] = []
    if task_dir.exists():
        for f in sorted(task_dir.iterdir()):
            if f.is_file():
                stat = f.stat()
                output_files.append({
                    "name": f.name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                })

    messages = task.get("messages", [])
    if keyword:
        kw = keyword.lower()
        messages = [
            m for m in messages
            if kw in str(m.get("content", "")).lower() or kw in str(m.get("message", "")).lower()
        ]

    result = {
        "task_id": task_id,
        "title": task.get("title", ""),
        "date": task.get("date", ""),
        "status": task.get("status", "unknown"),
        "output_files": output_files,
        "output_dir": str(task_dir) if task_dir.exists() else "",
        "message_count": len(task.get("messages", [])),
        "filtered_messages": [
            {"role": m.get("role", ""), "content": m.get("content", "") or m.get("message", "")[:200]}
            for m in messages[-20:]
        ],
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


async def _export_crawl_data(task_id: str, format: str = "csv") -> str:
    """将爬取结果导出为指定格式文件。"""
    fmt = format.lower().strip()
    if fmt not in ("csv", "xlsx"):
        return json.dumps({"error": f"不支持的格式: {format}，仅支持 csv 和 xlsx"}, ensure_ascii=False)

    task_dir = get_task_dir(task_id)
    if not task_dir.exists():
        return json.dumps({"error": f"任务 {task_id} 没有输出目录"}, ensure_ascii=False)

    data: list[dict] = []
    for f in sorted(task_dir.iterdir()):
        if f.suffix.lower() == ".json" and "email" in f.name.lower():
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                    if isinstance(loaded, list):
                        data = loaded
                        break
            except Exception:
                pass
        elif f.suffix.lower() == ".csv":
            try:
                with open(f, "r", encoding="utf-8-sig") as fh:
                    reader = csv_module.DictReader(fh)
                    for row in reader:
                        data.append({
                            "name": row.get("姓名", ""),
                            "email": row.get("邮箱", ""),
                            "department": row.get("学院", ""),
                            "title": row.get("职称", ""),
                            "url": row.get("主页链接", ""),
                        })
                    break
            except Exception:
                pass

    if not data:
        return json.dumps({"error": f"任务 {task_id} 的输出目录中没有找到数据文件"}, ensure_ascii=False)

    task = history.get(task_id)
    university = task.get("title", "unknown") if task else "unknown"

    try:
        if fmt == "csv":
            path = export_csv(data, university, task_id)
        else:
            path = export_xlsx(data, university, task_id)

        result = {
            "success": True,
            "format": fmt,
            "filepath": str(path),
            "filename": path.name,
            "record_count": len(data),
        }
    except Exception as e:
        result = {"success": False, "error": str(e)}

    return json.dumps(result, ensure_ascii=False, indent=2)


# —————————————————————————— Resource 函数 ——————————————————————————


async def _get_crawl_results(task_id: str) -> str:
    """获取指定任务的结果文件列表和摘要信息。"""
    task = history.get(task_id)
    if not task:
        return f"任务 {task_id} 不存在。"

    task_dir = get_task_dir(task_id)
    lines = [
        f"# 任务 {task_id}",
        f"- 标题: {task.get('title', '')}",
        f"- 日期: {task.get('date', '')}",
        f"- 状态: {task.get('status', 'unknown')}",
        f"- 输出目录: {task_dir}",
        "",
        "## 输出文件",
    ]

    if task_dir.exists():
        for f in sorted(task_dir.iterdir()):
            if f.is_file():
                size_kb = f.stat().st_size / 1024
                lines.append(f"- {f.name} ({size_kb:.1f} KB)")
    else:
        lines.append("- (无)")

    return "\n".join(lines)


async def _get_output_file(task_id: str, filename: str) -> str:
    """读取指定任务的输出文件内容。"""
    task_dir = get_task_dir(task_id)
    filepath = task_dir / filename

    try:
        filepath.resolve().relative_to(task_dir.resolve())
    except ValueError:
        return "错误：不允许访问该路径。"

    if not filepath.exists():
        return f"文件不存在: {filename}"

    if filepath.stat().st_size > 1 * 1024 * 1024:
        return "文件过大（>1MB），请通过 export_crawl_data 导出后下载。"

    try:
        return filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"无法以文本格式读取 {filename}（可能是二进制文件）。"
    except Exception as e:
        return f"读取失败: {e}"


# —————————————————————————— Prompt 函数 ——————————————————————————


async def _crawl_prompt(university: str, college: str = "") -> str:
    """生成爬取任务的提示词模板。"""
    if college:
        return f"""请帮我抓取 {university} 的 {college} 教师邮箱信息。

要求：
1. 访问 {university} 官网，找到 {college} 的教师名录页面
2. 进入每位教师的个人详情页，提取姓名和邮箱
3. 将结果导出为 CSV 和 XLSX 格式
4. 排除学院公共邮箱（如 office@、admin@ 等）
5. 确保数据清洗：去重、姓名验证、邮箱格式验证"""
    else:
        return f"""请帮我抓取 {university} 所有学院的教师邮箱信息。

要求：
1. 访问 {university} 官网，找到「师资队伍」或「教师名录」入口
2. 遍历各学院，进入每位教师的个人详情页提取姓名和邮箱
3. 将结果按学院分类，导出为 CSV 和 XLSX 格式
4. 排除学院公共邮箱（如 office@、admin@ 等）
5. 确保数据清洗：去重、姓名验证、邮箱格式验证"""


# —————————————————————————— 工厂函数 ——————————————————————————


def create_mcp_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    name: str = "UniEmail Agent",
) -> FastMCP:
    """创建 FastMCP 服务器实例，注册所有 Tools / Resources / Prompts。

    Args:
        host: SSE 模式监听地址（默认 127.0.0.1）
        port: SSE 模式监听端口（默认 8000）
        name: MCP Server 名称
    """
    mcp = FastMCP(
        name=name,
        instructions="高校教师邮箱爬取 Agent。支持爬取指定大学学院的教师邮箱、查询历史结果、导出 CSV/XLSX。",
        host=host,
        port=port,
    )

    # 注册 Tools
    mcp.add_tool(
        _crawl_faculty_emails,
        name="crawl_faculty_emails",
        title="爬取教师邮箱",
        description="爬取指定大学学院的教师邮箱。参数: university(大学全称), college(学院,可选), query(附加条件,可选)。",
    )
    mcp.add_tool(
        _query_crawl_result,
        name="query_crawl_result",
        title="查询爬取结果",
        description="查询已有爬取结果。参数: task_id(任务ID), keyword(关键词过滤,可选)。",
    )
    mcp.add_tool(
        _export_crawl_data,
        name="export_crawl_data",
        title="导出爬取数据",
        description="将爬取结果导出为 CSV 或 XLSX。参数: task_id(任务ID), format(csv|xlsx,默认csv)。",
    )

    # 注册 Resources (使用 FunctionResource)
    mcp.add_resource(FunctionResource(
        uri="crawl://results/{task_id}",
        name="任务结果概览",
        description="查看指定任务的输出文件列表和状态摘要。",
        fn=_get_crawl_results,
    ))
    mcp.add_resource(FunctionResource(
        uri="crawl://outputs/{task_id}/{filename}",
        name="输出文件内容",
        description="读取指定任务输出文件的内容（文本格式）。",
        fn=_get_output_file,
    ))

    # 注册 Prompts
    mcp.add_prompt(Prompt.from_function(
        _crawl_prompt,
        name="crawl_prompt",
        title="爬取任务提示词",
        description="生成爬取任务提示词。参数: university(大学名称), college(学院,可选)。",
    ))

    return mcp


# —————————————————————————— 默认实例 ——————————————————————————

mcp = create_mcp_server()
