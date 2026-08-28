"""Agent Framework 单元测试。"""

import sys
import json
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from agent_framework.tool import Tool, ToolRegistry, ToolResult


# ═══════════════════════════════════════════════════════
# Tool 基类测试
# ═══════════════════════════════════════════════════════

def test_tool_registry():
    """测试工具的注册和获取。"""
    reg = ToolRegistry()

    class TestTool(Tool):
        name = "test"
        description = "测试工具"
        input_schema = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}

        async def call(self, input_data):
            return ToolResult(data=f"hello {input_data['x']}")

    reg.register(TestTool())
    assert "test" in reg.get_names()

    t = reg.get("test")
    assert t is not None
    assert t.name == "test"

    # 重复注册会报错
    with pytest.raises(KeyError):
        reg.register(TestTool())

    # 注销
    reg.unregister("test")
    assert reg.get("test") is None


def test_tool_validation():
    """测试工具参数校验。"""

    class GreetTool(Tool):
        name = "greet"
        description = "打招呼"
        input_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
        }

        async def call(self, input_data):
            return ToolResult(data=f"Hello {input_data['name']}")

    tool = GreetTool()

    # 有效参数
    validated = tool.validate({"name": "Alice", "age": 25})
    assert validated["name"] == "Alice"
    assert validated["age"] == 25

    # 缺失必需参数
    with pytest.raises(ValueError, match="缺少必需参数"):
        tool.validate({})

    # 类型转换
    validated = tool.validate({"name": "Bob", "age": "30"})
    assert validated["age"] == 30


@pytest.mark.asyncio
async def test_tool_execution():
    """测试工具执行。"""

    class EchoTool(Tool):
        name = "echo"
        description = "回声"
        input_schema = {
            "type": "object",
            "properties": {"msg": {"type": "string"}},
            "required": ["msg"],
        }
        is_readonly = True

        async def call(self, input_data):
            return ToolResult(data=f"echo: {input_data['msg']}")

    tool = EchoTool()
    result = await tool.call({"msg": "hello"})
    assert result.data == "echo: hello"
    assert tool.is_readonly is True

    # OpenAI 格式转换
    ot = tool.to_openai_tool()
    assert ot["function"]["name"] == "echo"
    assert ot["type"] == "function"


# ═══════════════════════════════════════════════════════
# 工具实现测试
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_think_tool():
    """测试思考工具。"""
    from agent_framework.tools.think import ThinkTool

    tool = ThinkTool()
    result = await tool.call({"thought": "这是一个测试"})
    assert "这是一个测试" in result.data


@pytest.mark.asyncio
async def test_web_fetch_tool():
    """测试网页抓取工具。"""
    from agent_framework.tools.web_fetch import WebFetchTool

    tool = WebFetchTool()
    result = await tool.call({"url": "https://example.com", "max_length": 500})
    assert "Example" in result.data or "example" in result.data


# ═══════════════════════════════════════════════════════
# Provider 测试
# ═══════════════════════════════════════════════════════

def test_create_provider_no_key():
    """无 API Key 时能创建 Provider。"""
    import os
    # 临时清除 key
    old_keys = {
        k: os.environ.pop(k, None)
        for k in ["DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
    }
    try:
        from agent_framework.provider import create_provider
        provider = create_provider()
        assert provider is not None
        assert provider.config.api_key == "no-key"
    finally:
        for k, v in old_keys.items():
            if v:
                os.environ[k] = v


# ═══════════════════════════════════════════════════════
# Context 测试
# ═══════════════════════════════════════════════════════

def test_estimate_tokens():
    from agent_framework.context import estimate_tokens, trim_messages

    # 中英混合
    tokens = estimate_tokens("你好 world")
    assert tokens > 0

    # 消息裁剪
    msgs = [{"role": "system", "content": "x" * 10000}] + [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ] * 100
    trimmed = trim_messages(msgs, max_tokens=1000)
    assert len(trimmed) <= len(msgs)


# ═══════════════════════════════════════════════════════
# DispatchWorkersTool 测试
# ═══════════════════════════════════════════════════════

def test_dispatch_tool_registration():
    """测试 dispatch_workers 工具的注册和元数据。"""
    from agent_framework.tools.dispatch import DispatchWorkersTool

    tool = DispatchWorkersTool(task_id="test-task")
    assert tool.name == "dispatch_workers"
    assert "并行派发" in tool.description
    assert "tasks" in tool.input_schema["properties"]
    assert "university" in tool.input_schema["properties"]
    assert "tasks" in tool.input_schema["required"]


@pytest.mark.asyncio
async def test_dispatch_tool_validation():
    """测试参数校验。"""
    from agent_framework.tools.dispatch import DispatchWorkersTool

    tool = DispatchWorkersTool(task_id="test-task")

    # 缺少必需参数
    with pytest.raises(ValueError, match="缺少必需参数"):
        tool.validate({})

    # 有效参数
    validated = tool.validate({
        "tasks": [{"name": "计算机学院", "url": "https://cs.nju.edu.cn/teachers"}],
        "university": "南京大学",
        "max_workers": 2,
    })
    assert len(validated["tasks"]) == 1
    assert validated["university"] == "南京大学"
    assert validated["max_workers"] == 2


@pytest.mark.asyncio
async def test_dispatch_tool_empty_tasks():
    """空任务列表应返回错误。"""
    from agent_framework.tools.dispatch import DispatchWorkersTool

    tool = DispatchWorkersTool(task_id="test-task")
    result = await tool.call({
        "tasks": [],
        "university": "南京大学",
    })
    assert "任务列表为空" in result.data


def test_dispatch_tool_in_registry():
    """验证 dispatch_workers 出现在全局工具注册中心。"""
    from agent_framework.tools import register_all_tools
    from agent_framework.tool import ToolRegistry

    registry = ToolRegistry()
    register_all_tools(registry, task_id="test-task")

    tool = registry.get("dispatch_workers")
    assert tool is not None
    assert tool.name == "dispatch_workers"
    assert "dispatch_workers" in registry.get_names()

    # 确认 OpenAI 格式转换正确
    openai_tools = registry.to_openai_tools()
    names = [t["function"]["name"] for t in openai_tools]
    assert "dispatch_workers" in names
