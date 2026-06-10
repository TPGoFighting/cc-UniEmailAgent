"""中央配置管理模块。

管理服务模式（官方云端服务或用户自备 API Key）的切换与持久化存储。
"""

import json
import os
import logging
from pathlib import Path
from agent.paths import get_runtime_base_dir

logger = logging.getLogger(__name__)

CONFIG_FILE = get_runtime_base_dir() / "config.json"

_DEFAULT_CONFIG = {
    "service_mode": "custom",  # 'cloud' (官方云服务) 或 'custom' (个人 API Key)
    "service_token": "",       # 官方服务激活码 / 订阅 Token
    "deepseek_api_key": "",    # 个人 DeepSeek API Key
    "balance_yuan": 5.00       # 官方云服务账户余额 (元)，默认赠送 5.00 元体验金
}

def load_config() -> dict:
    """从 config.json 加载配置，如果不存在则从环境变量初始化。"""
    if not CONFIG_FILE.exists():
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        config = _DEFAULT_CONFIG.copy()
        config["deepseek_api_key"] = api_key
        save_config(config)
        return config
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            config = _DEFAULT_CONFIG.copy()
            config.update(data)
            return config
    except Exception as e:
        logger.warning(f"加载配置文件失败，返回默认配置: {e}")
        return _DEFAULT_CONFIG.copy()

def save_config(config: dict) -> None:
    """保存配置到 config.json。"""
    try:
        data_to_save = {k: config.get(k, _DEFAULT_CONFIG[k]) for k in _DEFAULT_CONFIG}
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存配置文件失败: {e}")

def get_effective_llm_settings() -> tuple[str, str]:
    """获取实际生效的大模型 API Key 和 Base URL。
    返回 (api_key, base_url)
    """
    config = load_config()
    if config["service_mode"] == "cloud":
        # 官方云端服务：使用内置中转 API 和激活码
        api_key = config["service_token"] or "free_trial_token"
        base_url = os.environ.get("UNIEMAIL_CLOUD_BASE_URL", "https://api.uniemailagent.com/v1")
        return api_key, base_url
    else:
        # 用户自备 Key：优先使用界面配置，为空时使用环境变量
        api_key = config["deepseek_api_key"] or os.environ.get("DEEPSEEK_API_KEY", "")
        base_url = os.environ.get("DEEPSEEK_API_BASE") or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1"
        return api_key, base_url


def sync_llm_settings_to_environ() -> None:
    """同步实际生效的大模型 API settings 到 os.environ，供子进程和当前进程调用。

    关键设计：
    - OpenAI 兼容变量 → 给 Python openai SDK（意图识别、问答、数据分析）
    - Anthropic 兼容变量 → 给 Claude Code CLI 子进程
    - DeepSeek 有两个 endpoint：
      * https://api.deepseek.com/v1 — OpenAI 格式（Python openai SDK）
      * https://api.deepseek.com/anthropic — Anthropic 格式（Claude Code CLI）
    - 不再清空 ANTHROPIC_API_KEY！之前设成 "" 导致 Claude Code CLI 静默退出无输出
    """
    try:
        api_key, base_url = get_effective_llm_settings()
        if api_key:
            # === OpenAI 兼容（Python openai SDK：意图识别、问答、数据分析）===
            os.environ["DEEPSEEK_API_KEY"] = api_key
            os.environ["DEEPSEEK_API_BASE"] = base_url
            os.environ["OPENAI_API_KEY"] = api_key
            os.environ["OPENAI_BASE_URL"] = base_url

            # === Anthropic 兼容（Claude Code CLI 子进程）===
            # 如果已存在 ANTHROPIC_BASE_URL（如用户 settings.json 配置的），尊重它
            # 否则：DeepSeek 用 Anthropic 兼容端点，其他 provider 复用 base_url
            anthropic_base = os.environ.get("ANTHROPIC_BASE_URL")
            if not anthropic_base:
                if "deepseek" in (base_url or "").lower():
                    anthropic_base = "https://api.deepseek.com/anthropic"
                else:
                    anthropic_base = base_url

            os.environ["ANTHROPIC_BASE_URL"] = anthropic_base
            os.environ["ANTHROPIC_AUTH_TOKEN"] = api_key

            # ★★★ 关键修复：之前设为 "" 导致 Claude Code CLI 静默失败无输出 ★★★
            # Claude Code CLI 子进程读 ANTHROPIC_API_KEY 做认证，空字符串 = 无认证
            os.environ["ANTHROPIC_API_KEY"] = api_key

            # 告诉 Claude Code CLI 用 DeepSeek 的哪个模型
            if "deepseek" in anthropic_base.lower():
                os.environ.setdefault("ANTHROPIC_MODEL", "deepseek-chat")
                os.environ.setdefault("ANTHROPIC_DEFAULT_SONNET_MODEL", "deepseek-chat")
                os.environ.setdefault("ANTHROPIC_DEFAULT_HAIKU_MODEL", "deepseek-chat")
                os.environ.setdefault("ANTHROPIC_DEFAULT_OPUS_MODEL", "deepseek-chat")
                os.environ.setdefault("ANTHROPIC_REASONING_MODEL", "deepseek-reasoner")

            # ★ CLAUDE_CODE_SIMPLE=1 强制 Claude Code CLI 只用环境变量 ANTHROPIC_API_KEY
            #   不走 settings.json / OAuth / keychain，避免全新安装的机器因缺少配置而静默失败
            os.environ["CLAUDE_CODE_SIMPLE"] = "1"

            logger.info("已成功同步 UI 设置中的 API Key 到当前进程及子进程的环境变量")
    except Exception as e:
        logger.warning(f"同步大模型设置到环境变量失败: {e}")

