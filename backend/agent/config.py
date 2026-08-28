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
    data_to_save = {k: config.get(k, _DEFAULT_CONFIG[k]) for k in _DEFAULT_CONFIG}
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = CONFIG_FILE.with_suffix(CONFIG_FILE.suffix + ".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_file, CONFIG_FILE)
    except Exception as e:
        logger.error(f"保存配置文件失败: {e}")
        raise

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
    """同步实际生效的大模型 API settings 到 os.environ，供当前进程和子进程调用。

    DirectorAgent 使用 OpenAI 兼容 API（DeepSeek），只设置必要环境变量。
    Claude Code CLI 已彻底移除，不再设置 Anthropic 相关变量。
    """
    try:
        api_key, base_url = get_effective_llm_settings()
        if api_key:
            os.environ["DEEPSEEK_API_KEY"] = api_key
            os.environ["DEEPSEEK_API_BASE"] = base_url
            os.environ["OPENAI_API_KEY"] = api_key
            os.environ["OPENAI_BASE_URL"] = base_url

            logger.info("已成功同步 API Key 到当前进程及子进程的环境变量")
    except Exception as e:
        logger.warning(f"同步大模型设置到环境变量失败: {e}")
