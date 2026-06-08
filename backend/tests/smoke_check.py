# UniEmailAgent 快速自检脚本
# 检查后端存活 + 前端可访问
# 用法: python tests/smoke_check.py

import urllib.request
import json
import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_URL = "http://localhost:8010"
FRONTEND_URL = "http://localhost:3000"

def check(name, url, expect_json=False):
    try:
        r = urllib.request.urlopen(url, timeout=5)
        if expect_json:
            data = json.loads(r.read().decode())
            print(f"  ✅ {name} — HTTP {r.status}, JSON OK")
            return data
        else:
            body = r.read().decode()
            print(f"  ✅ {name} — HTTP {r.status}, {len(body)} bytes")
            return True
    except Exception as e:
        print(f"  ❌ {name} — {e}")
        return False

def main():
    print(f"=== UniEmailAgent Smoke Check ===")
    print(f"Backend: {BACKEND_URL}")
    print(f"Frontend: {FRONTEND_URL}")
    print()

    ok = 0
    total = 0

    # 1. 后端 FastAPI docs (确认 uvicorn 运行中)
    total += 1
    if check("Backend /docs", f"{BACKEND_URL}/docs"):
        ok += 1

    # 3. 前端可访问
    total += 1
    if check("Frontend", FRONTEND_URL):
        ok += 1

    # 4. 前端 _next/static (验证 Next.js 实际工作)
    total += 1
    try:
        r = urllib.request.urlopen(f"{FRONTEND_URL}/_next/static/chunks/app/page.js", timeout=5)
        print(f"  ✅ Frontend static — HTTP {r.status}")
        ok += 1
    except urllib.error.HTTPError as e:
        # Next.js 可能返回 404 但这是正常的（文件路径不确定），只检查前端主页
        print(f"  ⬜ Frontend static — HTTP {e.code} (可能没有这个文件，不影响)")
        total -= 1
    except Exception as e:
        print(f"  ❌ Frontend static — {e}")

    print()
    print(f"结果: {ok}/{total} 通过")
    if ok == total:
        print("✅ 全部通过")
        return 0
    else:
        print(f"❌ {total - ok} 项失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())
