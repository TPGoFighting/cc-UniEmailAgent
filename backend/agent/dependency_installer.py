import os
import sys
import shutil
import subprocess
import threading
import logging
from pathlib import Path
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class DependencyInstaller:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super(DependencyInstaller, cls).__new__(cls, *args, **kwargs)
                cls._instance._init_installer()
            return cls._instance

    def _init_installer(self):
        self.status = {
            "node": "pending",
            "claude_code": "pending",
            "hermes": "pending",
            "playwright": "pending",
            "is_running": False,
            "current_action": "",
            "logs": []
        }
        self.lock = threading.Lock()

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.status)

    def log(self, message: str):
        logger.info(f"[DepInstaller] {message}")
        with self.lock:
            self.status["logs"].append(message)
            if len(self.status["logs"]) > 200:
                self.status["logs"].pop(0)

    def check_installed(self) -> Dict[str, bool]:
        """进行环境快速检查"""
        # 在检查前先 fix 一下 PATH
        try:
            from agent.paths import fix_windows_path
            fix_windows_path()
        except Exception:
            pass

        def _safe_which(name: str) -> bool:
            try:
                return bool(shutil.which(name))
            except OSError as exc:
                logger.warning(f"[DepInstaller] PATH 检测 {name} 失败: {exc}")
                return False

        node_ok = _safe_which("node")
        try:
            from agent.claude_agent import _resolve_claude_executable
            claude_ok = bool(_resolve_claude_executable())
        except Exception as exc:
            logger.warning(f"[DepInstaller] Claude Code CLI 检测失败: {exc}")
            claude_ok = False
        hermes_ok = _safe_which("hermes")
        
        playwright_ok = False
        try:
            localappdata = os.environ.get("LOCALAPPDATA", "")
            if localappdata:
                pw_dir = Path(localappdata) / "ms-playwright"
                if pw_dir.exists() and any(pw_dir.glob("chromium-*")):
                    playwright_ok = True
        except Exception:
            pass

        return {
            "node": node_ok,
            "claude_code": claude_ok,
            "hermes": hermes_ok,
            "playwright": playwright_ok
        }

    def start_install(self):
        """异步启动安装流程"""
        with self.lock:
            if self.status["is_running"]:
                self.log("安装任务已在运行中，跳过重复启动。")
                return
            self.status["is_running"] = True
            self.status["logs"] = []

        thread = threading.Thread(target=self._run_install_sync, name="DependencyInstallerThread")
        thread.daemon = True
        thread.start()

    def _run_install_sync(self):
        self.log("====== 开始环境依赖自动检查与配置 ======")
        try:
            # 1. 快速检查已安装状态
            installed = self.check_installed()
            
            with self.lock:
                for k, v in installed.items():
                    self.status[k] = "installed" if v else "pending"

            # 2. 安装 Node.js
            if not installed["node"]:
                self.log("检测到未安装 Node.js，正在尝试通过 Winget 自动安装...")
                with self.lock:
                    self.status["node"] = "installing"
                    self.status["current_action"] = "正在安装 Node.js..."
                
                # 尝试使用 winget 安装 Node.js
                cmd = ["winget", "install", "OpenJS.NodeJS", "--silent", "--accept-source-agreements", "--accept-package-agreements"]
                self.log(f"运行命令: {' '.join(cmd)}")
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                    if proc.returncode == 0:
                        self.log("Node.js 安装成功！")
                        with self.lock:
                            self.status["node"] = "installed"
                        # 尝试更新当前进程 PATH 变量以立即识别 node
                        from agent.paths import fix_windows_path
                        fix_windows_path()
                        installed["node"] = True
                    else:
                        self.log(f"Node.js 安装失败。退出码: {proc.returncode}。错误: {proc.stderr}")
                        with self.lock:
                            self.status["node"] = "failed"
                except Exception as e:
                    self.log(f"Node.js 安装过程出错: {e}")
                    with self.lock:
                        self.status["node"] = "failed"
            else:
                self.log("Node.js 已就绪，跳过安装。")
                with self.lock:
                    self.status["node"] = "skipped"

            # 3. 安装 Claude Code CLI
            # 如果 node 就绪，但 claude 没就绪，执行 npm install
            if installed["node"]:
                if not installed["claude_code"]:
                    self.log("检测到未安装 Claude Code CLI，正在通过 NPM 自动安装...")
                    with self.lock:
                        self.status["claude_code"] = "installing"
                        self.status["current_action"] = "正在安装 Claude Code CLI..."
                    
                    cmd = ["npm", "install", "-g", "@anthropic-ai/claude-code", "--yes"]
                    self.log(f"运行命令: {' '.join(cmd)}")
                    try:
                        # 运行 npm 安装，使用 shell=True 确保 windows npm 识别正常
                        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
                        if proc.returncode == 0:
                            self.log("Claude Code CLI 安装成功！")
                            with self.lock:
                                self.status["claude_code"] = "installed"
                            # 更新当前 PATH
                            from agent.paths import fix_windows_path
                            fix_windows_path()
                        else:
                            self.log(f"Claude Code CLI 安装失败。退出码: {proc.returncode}。错误: {proc.stderr}")
                            with self.lock:
                                self.status["claude_code"] = "failed"
                    except Exception as e:
                        self.log(f"Claude Code CLI 安装过程异常: {e}")
                        with self.lock:
                            self.status["claude_code"] = "failed"
                else:
                    self.log("Claude Code CLI 已就绪，跳过安装。")
                    with self.lock:
                        self.status["claude_code"] = "skipped"
            else:
                self.log("未检测到 Node.js，无法配置 Claude Code CLI。")
                with self.lock:
                    self.status["claude_code"] = "failed"

            # 4. 安装 Hermes CLI
            if not installed["hermes"]:
                self.log("检测到未安装 Hermes CLI，正在通过 pip 自动配置...")
                with self.lock:
                    self.status["hermes"] = "installing"
                    self.status["current_action"] = "正在配置 Hermes Orchestrator..."
                
                cmd = [sys.executable, "-m", "pip", "install", "hermes-agent"]
                self.log(f"运行命令: {' '.join(cmd)}")
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                    if proc.returncode == 0:
                        self.log("Hermes CLI 依赖配置成功！")
                        with self.lock:
                            self.status["hermes"] = "installed"
                    else:
                        self.log(f"Hermes CLI 配置失败。退出码: {proc.returncode}。错误: {proc.stderr}")
                        with self.lock:
                            self.status["hermes"] = "failed"
                except Exception as e:
                    self.log(f"Hermes CLI 配置过程异常: {e}")
                    with self.lock:
                        self.status["hermes"] = "failed"
            else:
                self.log("Hermes CLI 已就绪，跳过配置。")
                with self.lock:
                    self.status["hermes"] = "skipped"

            # 5. 安装 Playwright Chromium
            if not installed["playwright"]:
                self.log("检测到未安装 Playwright Chromium，正在进行自动拉取安装...")
                with self.lock:
                    self.status["playwright"] = "installing"
                    self.status["current_action"] = "正在配置 Playwright Chromium 浏览器内核..."
                
                cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
                self.log(f"运行命令: {' '.join(cmd)}")
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                    if proc.returncode == 0:
                        self.log("Playwright Chromium 浏览器内核配置成功！")
                        with self.lock:
                            self.status["playwright"] = "installed"
                    else:
                        # 尝试后备运行 playwright CLI 直接调用
                        self.log("尝试通过全局/环境命令行安装 Playwright Chromium 后备方案...")
                        cmd_fallback = ["playwright", "install", "chromium"]
                        proc_fb = subprocess.run(cmd_fallback, shell=True, capture_output=True, text=True, timeout=300)
                        if proc_fb.returncode == 0:
                            self.log("Playwright Chromium 后备方案配置成功！")
                            with self.lock:
                                self.status["playwright"] = "installed"
                        else:
                            self.log(f"Playwright Chromium 配置失败。退出码: {proc_fb.returncode}。错误: {proc_fb.stderr}")
                            with self.lock:
                                self.status["playwright"] = "failed"
                except Exception as e:
                    self.log(f"Playwright Chromium 配置过程异常: {e}")
                    with self.lock:
                        self.status["playwright"] = "failed"
            else:
                self.log("Playwright Chromium 浏览器已就绪，跳过安装。")
                with self.lock:
                    self.status["playwright"] = "skipped"

            self.log("====== 环境依赖自动配置全部结束 ======")
        except Exception as e:
            self.log(f"自动安装检测过程发生严重异常: {e}")
        finally:
            with self.lock:
                self.status["is_running"] = False
                self.status["current_action"] = ""
