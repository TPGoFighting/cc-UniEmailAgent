"""记忆召回工具 — 让 DirectorAgent 在推理过程中查询历史爬取经验。

双向记忆策略：
1. 文件技能库（skills/crawl_knowledge.md）— 结构化、可编辑的显式知识
2. Mem0 向量库（Qdrant）— 语义搜索的隐式记忆

两种来源都通过本工具暴露给 DirectorAgent。
"""

from __future__ import annotations

import logging
from typing import Any

from ..tool import Tool, ToolResult

logger = logging.getLogger(__name__)


class RecallMemoryTool(Tool):
    """查询历史爬取经验，获取特定大学的爬取技巧和注意事项。"""

    name = "recall_memory"
    description = """查询过往爬取任务的经验记忆，获取特定大学的爬取技巧和注意事项。

当你开始爬取某个大学的教师邮箱时，可以先调用此工具获取历史经验，包括：
- 该校官网的师资页面 URL 模式
- 邮箱提取的有效选择器 / DOM 结构特点
- 已知的反爬措施和应对方法
- 之前踩过的坑和解决方案
- 之前完成过的学院列表和覆盖率

注意：本工具只返回已有记忆，如果无相关记忆则返回空字符串。"""

    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "查询内容，如「南京大学 邮箱爬取经验」「计算机学院 页面结构」",
            },
            "university": {
                "type": "string",
                "description": "大学全称（可选），限定搜索范围为特定大学",
            },
        },
        "required": ["query"],
    }
    is_readonly = True

    async def call(self, input_data: dict[str, Any]) -> ToolResult:
        query = input_data.get("query", "")
        university = input_data.get("university", "")

        if not query:
            return ToolResult(data="")

        parts: list[str] = []

        # 1. 尝试 Mem0 向量库（语义搜索，更灵活）
        try:
            from agent.memory import CrawlMemory
            memory = CrawlMemory.get_instance()
            if memory.is_ready():
                mem0_result = memory.search_relevant(query, university, limit=5)
                if mem0_result:
                    parts.append(mem0_result)
        except Exception as e:
            logger.debug(f"RecallMemoryTool: Mem0 查询失败（可忽略）: {e}")

        # 2. 尝试文件技能库（结构化知识）
        try:
            from agent.skill_manager import load_skills_prompt
            skill_text = load_skills_prompt(university)
            if skill_text:
                # 如果太长，按大学名截取相关部分
                parts.append(skill_text)
        except Exception as e:
            logger.debug(f"RecallMemoryTool: 技能库加载失败（可忽略）: {e}")

        if not parts:
            return ToolResult(data="")

        # 合并，去重
        combined = "\n\n---\n\n".join(parts)

        # 控制总长度（防止撑爆上下文）
        if len(combined) > 4000:
            combined = combined[:4000] + "\n\n...(以下内容已截断)"

        return ToolResult(data=f"## 🧠 历史记忆\n\n{combined}\n")
