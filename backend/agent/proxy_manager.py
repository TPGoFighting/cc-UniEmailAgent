"""代理管理器 — Bright Data 住宅代理集成，突破 412/403 封锁。

提供两种模式：
- DirectProxy：直连，默认方案，不做任何代理更改
- BrightDataProxy：Bright Data 住宅代理，支持 zone 切换

工厂函数 get_proxy_manager() 根据 BRIGHTDATA_TOKEN 环境变量自动选择。
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Bright Data 代理服务器地址
BRIGHTDATA_SERVER = "http://brd.superproxy.io:22225"

# 封锁状态码集合
BLOCKED_STATUS_CODES = frozenset({403, 412, 429, 503})


class BaseProxyManager:
    """代理管理器基类，定义代理检测和配置接口。"""

    def matches(self, status_code: int) -> bool:
        """检测给定 HTTP 状态码是否表示被封锁，需要代理介入。"""
        raise NotImplementedError

    def get_proxy_config(self) -> Optional[dict]:
        """返回 Playwright browser.new_context() 可用的 proxy 参数字典。
        无代理时返回 None。
        """
        raise NotImplementedError

    def rotate_zone(self) -> None:
        """切换到下一个代理区域/策略。"""
        raise NotImplementedError

    @property
    def name(self) -> str:
        """当前代理方案名称，用于日志输出。"""
        raise NotImplementedError


class DirectProxy(BaseProxyManager):
    """直连模式 — 不使用任何代理，从不触发封锁检测。

    该模式用于未配置 BRIGHTDATA_TOKEN 时的默认行为，
    确保系统在无代理环境下完整可运行。
    """

    def matches(self, status_code: int) -> bool:
        """直连模式不检测封锁。"""
        return False

    def get_proxy_config(self) -> Optional[dict]:
        """直连模式不返回代理配置。"""
        return None

    def rotate_zone(self) -> None:
        """直连模式无区域可切换。"""
        pass

    @property
    def name(self) -> str:
        return "direct"


class BrightDataProxy(BaseProxyManager):
    """Bright Data 住宅代理 — 通过 zone 轮换突破反爬封锁。

    使用 Bright Data 的 superproxy 服务：
    - 默认使用 'unblock' zone（自动解锁）
    - 备选 'residential' zone（住宅 IP 池）
    - 检测到 403/412/429/503 时自动切换 zone 重试

    环境变量：
    - BRIGHTDATA_TOKEN: Bright Data 认证 token（密码）
    - BRIGHTDATA_CUSTOMER_ID: Bright Data 客户 ID（用户名前缀）
    """

    ZONES = ("unblock", "residential")

    def __init__(self, token: str, customer_id: str = ""):
        """初始化 Bright Data 代理。

        Args:
            token: Bright Data 认证 token
            customer_id: Bright Data 客户 ID（如 c-12345）
        """
        self._token = token
        self._customer_id = customer_id
        self._zone_idx = 0
        self._blocked_codes = BLOCKED_STATUS_CODES

    @property
    def current_zone(self) -> str:
        """当前使用的代理 zone 名称。"""
        return self.ZONES[self._zone_idx]

    @property
    def name(self) -> str:
        return f"brightdata({self.current_zone})"

    def matches(self, status_code: int) -> bool:
        """检测 HTTP 状态码是否表示被目标服务器封锁。

        返回 True 表示应该切换代理区域并重试。
        """
        return status_code in self._blocked_codes

    def rotate_zone(self) -> None:
        """轮换到下一个代理 zone。

        在 unblock 和 residential 之间交替，
        用于在检测到封锁后切换 IP 策略重试。
        """
        old_zone = self.current_zone
        self._zone_idx = (self._zone_idx + 1) % len(self.ZONES)
        logger.info(f"Bright Data zone 切换: {old_zone} → {self.current_zone}")

    def get_proxy_config(self) -> dict:
        """生成 Playwright browser.new_context() 的 proxy 参数。

        Returns:
            dict: {'server': str, 'username': str, 'password': str}
        """
        username = f"brd-customer-{self._customer_id}-zone-{self.current_zone}"
        return {
            "server": BRIGHTDATA_SERVER,
            "username": username,
            "password": self._token,
        }


def get_proxy_manager() -> BaseProxyManager:
    """工厂函数：根据环境变量自动选择代理方案。

    读取 BRIGHTDATA_TOKEN 环境变量：
    - 有值 → 返回 BrightDataProxy 实例
    - 无值 → 返回 DirectProxy 实例（完整可空跑）

    同时读取 BRIGHTDATA_CUSTOMER_ID 用于构造 Bright Data 用户名。
    """
    token = os.getenv("BRIGHTDATA_TOKEN", "").strip()
    if token:
        customer_id = os.getenv("BRIGHTDATA_CUSTOMER_ID", "").strip()
        if not customer_id:
            logger.warning(
                "BRIGHTDATA_TOKEN 已设置但 BRIGHTDATA_CUSTOMER_ID 未设置，"
                "代理可能无法正常工作。请设置 BRIGHTDATA_CUSTOMER_ID 环境变量。"
            )
        logger.info(f"启用 Bright Data 代理，初始 zone: unblock")
        return BrightDataProxy(token, customer_id)

    logger.debug("未检测到 BRIGHTDATA_TOKEN，使用直连模式")
    return DirectProxy()
