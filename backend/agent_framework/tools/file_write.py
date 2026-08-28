"""文件写入工具 — 保存爬取数据到文件。"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ..tool import Tool, ToolResult


class FileWriteTool(Tool):
    """写入文件（CSV、JSON、TXT 等）。"""

    name = "file_write"
    description = """将数据写入文件。支持 CSV、JSON、TXT、MD 格式。
CSV 格式请传入列名和行数据。注意：输出文件会自动保存在任务专属目录下。
"""
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "保存路径（相对于 outputs/ 目录的路径，如 'task_id/nju_cs.csv'）",
            },
            "content": {
                "type": "string",
                "description": "文件内容（文本格式）",
            },
            "format": {
                "type": "string",
                "enum": ["text", "csv", "json"],
                "description": "文件格式（默认 auto 根据后缀推断）",
                "default": "auto",
            },
            "csv_columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "CSV 列名（format=csv 时使用）",
            },
            "csv_rows": {
                "type": "array",
                "items": {"type": "object"},
                "description": "CSV 数据行（format=csv 时使用）",
            },
        },
        "required": ["file_path"],
    }
    is_destructive = False

    def __init__(self, base_output_dir: str | None = None):
        super().__init__()
        from agent.paths import _BASE_OUTPUT_DIR
        self._base = Path(base_output_dir) if base_output_dir else _BASE_OUTPUT_DIR

    async def call(self, input_data: dict[str, Any]) -> ToolResult:
        path = Path(input_data["file_path"])

        # 如果是相对路径，放在 outputs/ 下
        if not path.is_absolute():
            path = self._base / path

        # 确保目录存在
        path.parent.mkdir(parents=True, exist_ok=True)

        fmt = input_data.get("format", "auto")
        if fmt == "auto":
            fmt = path.suffix.lower().lstrip(".")

        if fmt == "csv" or (fmt == "auto" and path.suffix.lower() == ".csv"):
            return self._write_csv(path, input_data)
        elif fmt == "json" or path.suffix.lower() == ".json":
            return self._write_json(path, input_data)
        else:
            return self._write_text(path, input_data)

    def _write_csv(self, path: Path, data: dict[str, Any]) -> ToolResult:
        columns = data.get("csv_columns", [])
        rows = data.get("csv_rows", [])

        if not columns and rows:
            columns = list(rows[0].keys())

        if not columns:
            return ToolResult(data="❌ CSV 写入失败: 未指定列名")

        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in columns})

        return ToolResult(
            data=f"✅ 已保存 CSV: {path.name}（{len(rows)} 行，{len(columns)} 列）",
            files_created=[str(path)],
            metadata={"rows": len(rows), "columns": columns, "path": str(path)},
        )

    def _write_json(self, path: Path, data: dict[str, Any]) -> ToolResult:
        content = data.get("content", "")
        if content:
            try:
                obj = json.loads(content)
            except json.JSONDecodeError:
                obj = {"text": content}
        else:
            obj = {k: v for k, v in data.items() if k not in ("file_path", "format")}

        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        return ToolResult(
            data=f"✅ 已保存 JSON: {path.name}",
            files_created=[str(path)],
        )

    def _write_text(self, path: Path, data: dict[str, Any]) -> ToolResult:
        content = data.get("content", "")
        path.write_text(content, encoding="utf-8")
        return ToolResult(
            data=f"✅ 已保存: {path.name}（{len(content)} 字符）",
            files_created=[str(path)],
        )
