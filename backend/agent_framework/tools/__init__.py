"""工具实现包。"""

from .think import ThinkTool
from .web_fetch import WebFetchTool
from .web_search import WebSearchTool
from .file_read import FileReadTool
from .file_write import FileWriteTool
from .browser import BrowserNavigateTool, BrowserExtractTool, BrowserScreenshotTool
from .bash import BashTool
from .dispatch import DispatchWorkersTool
from .recall_memory import RecallMemoryTool

__all__ = [
    "ThinkTool",
    "WebFetchTool",
    "WebSearchTool",
    "FileReadTool",
    "FileWriteTool",
    "BrowserNavigateTool",
    "BrowserExtractTool",
    "BrowserScreenshotTool",
    "BashTool",
    "DispatchWorkersTool",
    "RecallMemoryTool",
]


def register_all_tools(registry, task_id=""):
    """注册所有可用工具到注册中心。"""
    from ..tool import ToolRegistry
    if not isinstance(registry, ToolRegistry):
        raise TypeError("需要 ToolRegistry 实例")

    registry.register(ThinkTool())
    registry.register(WebFetchTool())
    registry.register(WebSearchTool())
    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    registry.register(BashTool())

    # 浏览器工具需要 Playwright，可选注册
    try:
        registry.register(BrowserNavigateTool())
        registry.register(BrowserExtractTool())
        registry.register(BrowserScreenshotTool())
        logger = __import__("logging").getLogger(__name__)
        logger.info("浏览器工具已注册（Playwright 就绪）")
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.warning(f"浏览器工具注册失败（Playwright 可能未安装）: {e}")

    # 并行派发工具（依赖 task_id 创建 Worker）
    registry.register(DispatchWorkersTool(task_id=task_id))

    # 记忆召回工具（只读，依赖 agent.memory / agent.skill_manager）
    try:
        registry.register(RecallMemoryTool())
        logger.info("记忆召回工具已注册")
    except Exception as e:
        logger.warning(f"记忆召回工具注册失败: {e}")
