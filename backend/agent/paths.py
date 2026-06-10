"""中央路径持久化管理模块。

自动检测是否运行在 PyInstaller 打包环境，并映射读写目录至 LocalAppData 下，
以避开 Windows 系统目录写权限限制。
"""

import os
import sys
import shutil
from pathlib import Path

def get_bundle_dir() -> Path:
    """获取打包解压后的只读资源目录（_MEIPASS）。
    如果在开发环境中，返回 backend 根目录。
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    # 开发环境：指向 backend/
    return Path(__file__).parent.parent.resolve()

def get_runtime_base_dir() -> Path:
    """获取持久化可写数据的根目录。
    打包环境下为 %LOCALAPPDATA%/UniEmailAgent，开发环境下为 backend 目录。
    """
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("LOCALAPPDATA")
        if appdata:
            p = Path(appdata) / "UniEmailAgent"
            p.mkdir(parents=True, exist_ok=True)
            return p
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.resolve()

# ── 持久化子目录定义 ──
DATA_DIR = get_runtime_base_dir() / "data"
_BASE_OUTPUT_DIR = get_runtime_base_dir() / "outputs"
SKILLS_DIR = get_runtime_base_dir() / "skills"

def copy_recursive_if_not_exists(src: Path, dest: Path):
    """递归拷贝 src 目录下的所有文件和子目录到 dest，但仅当目标文件/目录不存在时。"""
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        dest_item = dest / item.name
        if item.is_file():
            if not dest_item.exists():
                try:
                    shutil.copy2(item, dest_item)
                except Exception:
                    pass
        elif item.is_dir() and item.name not in ["__pycache__", ".pytest_cache"]:
            copy_recursive_if_not_exists(item, dest_item)

def initialize_directories():
    """初始化运行时目录并拷贝只读默认资源。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _BASE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    # 拷贝 data/ 目录下的所有只读默认资源（包含高校数据库、预设记忆等）
    src_data_dir = get_bundle_dir() / "data"
    if src_data_dir.exists():
        for item in src_data_dir.iterdir():
            if item.is_file():
                dest_file = DATA_DIR / item.name
                # 高校数据库和域名映射表为只读系统资产，应强制更新至最新版本；其他历史文件等仅在不存在时才拷贝
                if not dest_file.exists() or item.name in ["universities_catalog.json", "university_urls.json"]:
                    try:
                        shutil.copy2(item, dest_file)
                    except Exception:
                        pass
            elif item.is_dir() and item.name not in ["__pycache__", ".pytest_cache"]:
                dest_subdir = DATA_DIR / item.name
                if not dest_subdir.exists():
                    try:
                        shutil.copytree(item, dest_subdir)
                    except Exception:
                        pass

    # 拷贝 outputs/ 目录下的所有爬取数据
    src_outputs_dir = get_bundle_dir() / "outputs"
    if src_outputs_dir.exists() and src_outputs_dir.resolve() != _BASE_OUTPUT_DIR.resolve():
        try:
            copy_recursive_if_not_exists(src_outputs_dir, _BASE_OUTPUT_DIR)
        except Exception:
            pass

    # 拷贝 skills/ 目录下的所有生成技能
    src_skills_dir = get_bundle_dir() / "skills"
    if src_skills_dir.exists() and src_skills_dir.resolve() != SKILLS_DIR.resolve():
        try:
            copy_recursive_if_not_exists(src_skills_dir, SKILLS_DIR)
        except Exception:
            pass

# 初始化
initialize_directories()

def fix_windows_path():
    """将常见的 Windows 全局包安装路径（如 winget、npm 等）注入到进程 PATH 中，
    防止操作系统启动新进程时因未加载环境变量导致 shutil.which 找不到 executable。
    """
    if sys.platform != "win32":
        return
    paths_to_add = [
        Path(os.environ.get("APPDATA", "")) / "npm",
        Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links",
        Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin",
    ]
    current_path = os.environ.get("PATH", "")
    current_path_list = [p.strip().rstrip("\\/") for p in current_path.split(";") if p.strip()]
    
    added = False
    for p in paths_to_add:
        if p.exists():
            p_str = str(p.resolve())
            if p_str not in current_path_list:
                current_path_list.append(p_str)
                added = True
                
    if added:
        os.environ["PATH"] = ";".join(current_path_list)

fix_windows_path()
