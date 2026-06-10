"""桌面端自动化打包构建脚本。

自动化步骤：
1. 确保安装打包所需的 pyinstaller 和 pywebview 库
2. 运行 npm run build 编译前端静态页面
3. 将静态页面复制到 backend/static/
4. 调用 PyInstaller 编译 backend/gui.py
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

# 定义工作目录
ROOT_DIR = Path(__file__).parent.resolve()
FRONTEND_DIR = ROOT_DIR / "frontend"
BACKEND_DIR = ROOT_DIR / "backend"
STATIC_DIST_DIR = BACKEND_DIR / "static"

def run_command(cmd: str, cwd: Path):
    """运行终端命令，输出实时日志。"""
    print(f"\n>> 运行命令: {cmd} (在 {cwd.name}/ 目录)...")
    result = subprocess.run(cmd, shell=True, cwd=cwd)
    if result.returncode != 0:
        print(f"❌ 命令运行失败，退出码: {result.returncode}")
        sys.exit(result.returncode)
    print("✓ 运行成功")

def check_python_packages():
    """确保 pyinstaller 和 pywebview 在当前环境中已安装。"""
    print("\n>> 正在检查 Python 打包环境依赖...")
    required_packages = ["pyinstaller", "pywebview"]
    for pkg in required_packages:
        try:
            __import__(pkg if pkg != "pywebview" else "webview")
            print(f"✓ 依赖项 {pkg} 已安装")
        except ImportError:
            print(f"⚠️ 依赖项 {pkg} 未安装，正在通过 pip 安装...")
            # 使用当前 Python 解释器的 pip 进行安装，防止多环境污染
            run_command(f'"{sys.executable}" -m pip install {pkg}', ROOT_DIR)

def main():
    print("==================================================")
    print("      UniEmail Agent 桌面端打包构建管道启动")
    print("==================================================")

    # 1. 确保依赖已安装
    check_python_packages()

    # 2. 前端静态页面编译
    print("\n>> 开始编译前端静态页面...")
    run_command("npm run build", FRONTEND_DIR)

    # 3. 清理并准备 backend/static 目录
    print("\n>> 正在复制静态页面至后端目录...")
    if STATIC_DIST_DIR.exists():
        shutil.rmtree(STATIC_DIST_DIR)
    
    frontend_out = FRONTEND_DIR / "out"
    if not frontend_out.exists():
        print("❌ 未找到前端编译产物目录 frontend/out，请检查编译配置！")
        sys.exit(1)

    shutil.copytree(frontend_out, STATIC_DIST_DIR)
    print(f"✓ 已将前端资产成功复制到: {STATIC_DIST_DIR}")

    # 4. 准备后端默认数据与配置打包项
    # 确保 data 目录和默认的 university_urls.json 存在
    data_dir = BACKEND_DIR / "data"
    data_dir.mkdir(exist_ok=True)
    
    # 5. 调用 PyInstaller 启动编译
    print("\n>> 启动 PyInstaller 编译...")
    pyinstaller_cmd = (
        'pyinstaller --noconfirm --clean --onedir --noconsole '
        '--name "UniEmailAgentApp" '
        '--add-data "static;static" '
        '--add-data "data;data" '
        '--add-data "skills;skills" '
        '--add-data "outputs;outputs" '
        '--add-data ".env;." '
        'gui.py'
    )
    
    # 切换至 backend 目录下执行 PyInstaller，以保证相对导入正常解析
    run_command(pyinstaller_cmd, BACKEND_DIR)

    # 6. 将默认 of .env 文件复制到 UniEmailAgentApp.exe 同级目录，供用户修改配置
    dist_dir = BACKEND_DIR / "dist" / "UniEmailAgentApp"
    src_env = BACKEND_DIR / ".env"
    dest_env = dist_dir / ".env"
    if src_env.exists():
        try:
            shutil.copy2(src_env, dest_env)
            print("✓ 已将默认的 .env 配置文件复制到可执行程序同级目录下")
        except Exception as e:
            print(f"⚠️ 复制外部 .env 失败: {e}")

    print("\n==================================================")
    print("🎉 打包完成！")
    print(f"编译成果物路径: {dist_dir}")
    print("请在此目录下运行 UniEmailAgentApp.exe 以启动桌面应用。")
    print("==================================================")

if __name__ == "__main__":
    main()
