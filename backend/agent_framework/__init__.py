"""UniEmail Agent Framework — 自定义 AI Agent 工具系统。


- 在进程内的 AI Agent 推理循环（Tool-based）
- 统一的 LLM Provider 接口（DeepSeek/OpenAI/Anthropic）
- 可扩展的 Tool 系统（参考 Claude Code 的 Tool.ts 设计）
- Worker 子 Agent 并行机制（参考 Coordinator + AgentTool 模式）

## 架构

```
┌─────────────────────────────────────────────────┐
│ DirectorAgent（主循环）                          │
│  System Prompt → LLM → 工具调用 → 结果 → 继续    │
└──────────┬────────────────────────────────┬──────┘
           │ 工具调用                        │ 子任务
           ▼                                ▼
┌──────────────────┐              ┌──────────────────┐
│ ToolRegistry     │              │ WorkerAgent      │
│ ├ think          │              │ (并行子任务)      │
│ ├ web_fetch      │              └──────────────────┘
│ ├ web_search     │
│ ├ file_read      │              ┌──────────────────┐
│ ├ file_write     │              │ LLMProvider      │
│ ├ bash           │              │ ├ DeepSeek       │
│ ├ browser_*      │              │ ├ OpenAI         │
│ └ ...            │              │ └ Anthropic      │
└──────────────────┘              └──────────────────┘
```
"""

from .director import DirectorAgent
from .worker import WorkerAgent
from .provider import LLMProvider, create_provider
from .tool import Tool, ToolRegistry, ToolResult

__all__ = [
    "DirectorAgent",
    "WorkerAgent",
    "LLMProvider",
    "create_provider",
    "Tool",
    "ToolRegistry",
    "ToolResult",
]
