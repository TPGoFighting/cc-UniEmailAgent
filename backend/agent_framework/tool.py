"""工具基类和注册系统 — 参考 Claude Code 的 `Tool.ts` 设计。

每个 Tool 包含：
- name: 工具名称（LLM 通过它调用）
- description: 工具描述（LLM 通过它理解用途）
- input_schema: JSON Schema 格式入参定义
- call(): 执行逻辑
- is_readonly: 是否只读（影响并行调度）
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator


@dataclass
class ToolResult:
    """工具执行结果。"""

    data: str  # 文本结果（LLM 能直接看到）
    files_created: list[str] = field(default_factory=list)  # 创建的文件路径列表
    metadata: dict[str, Any] = field(default_factory=dict)  # 额外元数据


class Tool(ABC):
    """工具抽象基类。"""

    # === 子类必须定义的属性 ===
    name: str = ""
    description: str = ""
    input_schema: dict[str, Any] = {}  # JSON Schema

    # === 可选配置 ===
    is_readonly: bool = False  # 只读工具可并行执行
    is_destructive: bool = False  # 破坏性操作需要确认
    is_enabled: bool = True  # 是否可用

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """子类必须定义 name 和 description。"""
        super().__init_subclass__(**kwargs)
        if not cls.name:
            raise TypeError(f"{cls.__name__} 必须定义 name 属性")
        if not cls.description:
            raise TypeError(f"{cls.__name__} 必须定义 description 属性")
        if not cls.input_schema:
            raise TypeError(f"{cls.__name__} 必须定义 input_schema 属性")

    @abstractmethod
    async def call(self, input_data: dict[str, Any]) -> ToolResult:
        """执行工具逻辑。input_data 经 input_schema 校验后传入。"""
        ...

    def validate(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """校验输入参数（简单实现，后续可升级为 jsonschema 库）。"""
        # 防御：如果传进来的是 JSON 字符串，解析为字典
        if isinstance(input_data, str):
            try:
                input_data = json.loads(input_data)
            except json.JSONDecodeError:
                input_data = {}
        if not isinstance(input_data, dict):
            input_data = {}
        validated: dict[str, Any] = {}
        props = self.input_schema.get("properties", {})
        required = self.input_schema.get("required", [])

        for key in required:
            if key not in input_data or input_data[key] is None:
                raise ValueError(f"缺少必需参数: {key}")

        for key, schema in props.items():
            if key in input_data and input_data[key] is not None:
                val = input_data[key]
                # 类型检查
                expected_type = schema.get("type")
                if expected_type == "string" and not isinstance(val, str):
                    val = str(val)
                elif expected_type == "integer" and not isinstance(val, int):
                    val = int(val)
                elif expected_type == "number" and not isinstance(val, (int, float)):
                    val = float(val)
                elif expected_type == "array" and not isinstance(val, list):
                    if isinstance(val, str):
                        val = [v.strip() for v in val.split(",")]
                    else:
                        val = [val]
                elif expected_type == "boolean" and not isinstance(val, bool):
                    val = str(val).lower() in ("true", "1", "yes")
                validated[key] = val
            elif key in input_data:
                validated[key] = input_data[key]

        return validated

    def to_openai_tool(self) -> dict[str, Any]:
        """转换为 OpenAI/DeepSeek 函数调用格式。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def to_anthropic_tool(self) -> dict[str, Any]:
        """转换为 Anthropic Claude 工具格式。"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    """工具注册中心 — 参考 `tools.ts` 的 assembleToolPool 模式。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册一个工具实例。"""
        if tool.name in self._tools:
            raise KeyError(f"工具 '{tool.name}' 已注册")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """注销工具。"""
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """按名称获取工具。"""
        return self._tools.get(name)

    def get_all(self) -> list[Tool]:
        """获取所有已启用的工具。"""
        return [t for t in self._tools.values() if t.is_enabled]

    def get_names(self) -> list[str]:
        """获取所有工具名称。"""
        return [t.name for t in self.get_all()]

    def to_openai_tools(self) -> list[dict[str, Any]]:
        """批量转换为 OpenAI 格式。"""
        return [t.to_openai_tool() for t in self.get_all()]

    def to_anthropic_tools(self) -> list[dict[str, Any]]:
        """批量转换为 Anthropic 格式。"""
        return [t.to_anthropic_tool() for t in self.get_all()]

    def to_json_schemas(self) -> dict[str, dict[str, Any]]:
        """转为 {名称: schema} 字典。"""
        return {t.name: t.input_schema for t in self.get_all()}
