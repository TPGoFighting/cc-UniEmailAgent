"""思考工具 — 让 LLM 在调用工具前进行深度推理。

参考 Claude Code 的 Thinking/推理模式，以及 Anthropic 的 extended thinking。
这个工具允许模型「停下来想一想」，整理思路再做下一步决策。
"""

from __future__ import annotations

from typing import Any

from ..tool import Tool, ToolResult


class ThinkTool(Tool):
    """深度推理工具 — 在调用其他工具前进行结构化思考。

    使用场景：
    - 分析复杂问题，拆解步骤
    - 评估多个方案，选择最优路径
    - 反思上一步结果，调整策略
    """

    name = "think"
    description = """进行深度思考和推理。在调用其他工具之前使用，帮助你分析问题、规划步骤、总结发现。
使用场景：
1. 面对复杂任务时：拆解成子步骤，规划执行顺序
2. 获得数据后：分析结果，提取洞察，决定下一步
3. 遇到问题时：诊断原因，评估备选方案
4. 总结时：整合发现，形成完整结论
"""
    input_schema = {
        "type": "object",
        "properties": {
            "thought": {
                "type": "string",
                "description": "你的思考内容。可以是问题分析、计划步骤、结果反思、方案对比等。",
            },
            "next_steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "思考后决定的下一步行动列表（可选）。",
            },
        },
        "required": ["thought"],
    }
    is_readonly = True

    async def call(self, input_data: dict[str, Any]) -> ToolResult:
        thought = input_data.get("thought", "")
        next_steps = input_data.get("next_steps", [])

        parts = [f"💭 {thought}"]
        if next_steps:
            parts.append("\n📋 下一步计划：")
            for i, step in enumerate(next_steps, 1):
                parts.append(f"  {i}. {step}")

        return ToolResult(data="\n".join(parts))
