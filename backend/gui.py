"""UniEmail Agent 桌面端原生窗口外壳。

利用 pywebview 启动 Chromium WebView2 窗口，并在后台守护线程中运行 FastAPI/Uvicorn 后端。
"""

import sys
import os
import time
import socket
import threading
import logging
import urllib.request
import json
from pathlib import Path
import webview

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gui")


def find_free_port(start_port=8070):
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1
    raise RuntimeError("未找到可用的空闲端口！")


def _get_app_dir():
    """获取应用目录。frozen 模式下用 exe 所在目录，开发模式用 backend/。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _load_dotenv():
    """加载 .env 文件。"""
    if not getattr(sys, "frozen", False):
        return
    env_path = _get_app_dir() / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        # 尝试多种编码，防止中文 Windows 下 ANSI(GBK) 编码炸掉
        for encoding in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
            try:
                load_dotenv(dotenv_path=env_path, encoding=encoding)
                logger.info(f"已加载 .env (encoding={encoding})")
                return
            except (UnicodeDecodeError, LookupError):
                continue
        # 最后兜底：忽略编码错误
        try:
            load_dotenv(dotenv_path=env_path, encoding="utf-8")
        except Exception as e:
            logger.warning(f"加载 .env 失败: {e}")


def wait_for_backend(url: str, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, method="GET")
            resp = urllib.request.urlopen(req, timeout=2)
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                if data.get("status") == "ok":
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def run_uvicorn(port: int) -> bool:
    """在独立线程中启动 uvicorn，返回是否启动成功。"""
    result = {"ok": False, "error": None}

    def _run():
        try:
            _load_dotenv()
            import uvicorn
            from main import app
            logger.info(f"Uvicorn 启动: 127.0.0.1:{port}")
            result["ok"] = True  # import 成功
            config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
            uvicorn.Server(config).run()
        except Exception as e:
            import traceback
            result["error"] = f"{type(e).__name__}: {str(e)[:300]}\n{traceback.format_exc()[-300:]}"
            logger.error(f"启动失败: {result['error']}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=15)  # 等待 import 完成

    if not result["ok"]:
        err = result.get("error") or "后端服务未能完成初始化，请检查 .env 配置。"
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, err, "UniEmail Agent 启动失败", 0x10)
        return False
    return True


def main():
    port = find_free_port(8070)

    if not run_uvicorn(port):
        sys.exit(1)

    url = f"http://127.0.0.1:{port}"
    if not wait_for_backend(f"{url}/api/health", timeout=20):
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            f"后端服务未能就绪。\n端口: {port}\n请确认 .env 中的 DEEPSEEK_API_KEY 填写正确。",
            "UniEmail Agent 启动超时", 0x10)
        sys.exit(1)

    logger.info(f"WebView → {url}")

    window = webview.create_window(
        title="UniEmail Agent",
        url=url,
        width=1280, height=800,
        min_size=(960, 640),
        background_color="#202123",
    )

    webview.start(debug=False)
    logger.info("窗口已关闭，退出")
    sys.exit(0)


if __name__ == "__main__":
    main()
