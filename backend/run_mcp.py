"""UniEmail Agent MCP Server 启动入口。

支持两种传输协议：
  - stdio（默认）：python run_mcp.py
  - SSE：       python run_mcp.py --sse --port 8011

用法：
  python run_mcp.py                # stdio 模式，由 MCP Client 通过子进程调用
  python run_mcp.py --sse          # SSE 模式，默认端口 8011
  python run_mcp.py --sse --port 8022  # SSE 模式，自定义端口
  python run_mcp.py --help         # 显示帮助
"""

import argparse
import sys

from mcp_server import create_mcp_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python run_mcp.py",
        description="UniEmail Agent MCP Server — 高校教师邮箱爬取 MCP 协议服务",
    )
    parser.add_argument(
        "--sse",
        action="store_true",
        default=False,
        help="使用 SSE（Server-Sent Events）传输模式（默认：stdio）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8011,
        help="SSE 模式监听端口（默认：8011，仅 --sse 时有效）",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="SSE 模式监听地址（默认：127.0.0.1）",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.sse:
        mcp = create_mcp_server(host=args.host, port=args.port)
        print(f"🟢 UniEmail Agent MCP Server 启动 (SSE 模式)", file=sys.stderr)
        print(f"   监听: http://{args.host}:{args.port}", file=sys.stderr)
        print(f"   SSE 端点: http://{args.host}:{args.port}/sse", file=sys.stderr)
        print(f"   消息端点: http://{args.host}:{args.port}/messages/", file=sys.stderr)
        mcp.run(transport="sse")
    else:
        mcp = create_mcp_server()
        print("🟢 UniEmail Agent MCP Server 启动 (stdio 模式)", file=sys.stderr)
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
