"""文件读取工具 — 读取已生成的数据文件。"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ..tool import Tool, ToolResult


class FileReadTool(Tool):
    """读取文件内容（CSV、JSON、TXT 等）。"""

    name = "file_read"
    description = """读取指定文件的内容。支持 CSV、JSON、TXT、MD 等格式。
CSV 文件会自动转为表格格式显示。
适用于查看爬取结果、配置文件、日志等。
"""
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件路径（绝对路径或相对项目根目录的路径）",
            },
            "max_rows": {
                "type": "integer",
                "description": "CSV 最多读取行数（默认 50）",
                "default": 50,
            },
            "encoding": {
                "type": "string",
                "description": "文件编码（默认 utf-8）",
                "default": "utf-8",
            },
        },
        "required": ["file_path"],
    }
    is_readonly = True

    async def call(self, input_data: dict[str, Any]) -> ToolResult:
        path = Path(input_data["file_path"])
        max_rows = input_data.get("max_rows", 50)
        encoding = input_data.get("encoding", "utf-8")

        if not path.exists():
            return ToolResult(data=f"❌ 文件不存在: {path}")

        if not path.is_file():
            return ToolResult(data=f"❌ 不是文件: {path}")

        try:
            suffix = path.suffix.lower()

            if suffix == ".csv":
                return self._read_csv(path, max_rows, encoding)
            elif suffix == ".json":
                return self._read_json(path, encoding)
            elif suffix in (".txt", ".md", ".log"):
                return self._read_text(path, encoding)
            else:
                return self._read_text(path, encoding)

        except Exception as e:
            return ToolResult(data=f"❌ 读取失败: {e}")

    def _read_csv(self, path: Path, max_rows: int, encoding: str) -> ToolResult:
        with open(path, "r", encoding=encoding) as f:
            reader = csv.DictReader(f)
            rows = []
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break
                rows.append(dict(row))

        if not rows:
            return ToolResult(data=f"📄 {path.name}: 空文件")

        headers = list(rows[0].keys())
        # 构建 Markdown 表格
        lines = [f"📄 **{path.name}**（共 {len(rows)} 行）\n"]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for row in rows:
            vals = [str(row.get(h, "")).replace("\n", " ")[:50] for h in headers]
            lines.append("| " + " | ".join(vals) + " |")

        return ToolResult(
            data="\n".join(lines),
            metadata={"rows": len(rows), "columns": headers},
        )

    def _read_json(self, path: Path, encoding: str) -> ToolResult:
        data = json.loads(path.read_text(encoding=encoding))
        formatted = json.dumps(data, ensure_ascii=False, indent=2)
        if len(formatted) > 5000:
            formatted = formatted[:5000] + f"\n\n...（截断至 5000 字符）"
        return ToolResult(data=f"📄 **{path.name}**\n\n```json\n{formatted}\n```")

    def _read_text(self, path: Path, encoding: str) -> ToolResult:
        text = path.read_text(encoding=encoding)
        size = len(text)
        if size > 5000:
            text = text[:5000] + f"\n\n...（截断至 5000 字符，原文 {size} 字符）"
        return ToolResult(data=f"📄 **{path.name}**（{size} 字符）\n\n{text}")
