# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

UniEmail Agent — 用户输入自然语言任务（如"抓取南京大学计算机学院教师邮箱"），AI Agent 自动操作浏览器、提取教师邮箱、导出 CSV/XLSX/HTML/PDF/DOCX/MD 六种格式。

## 启动命令

```bash
# 后端 (FastAPI, port 8000)
cd backend && python -m uvicorn main:app --port 8000 --reload

# 前端 (Next.js 16, Turbopack, port 3000)
cd frontend && npm run dev

# 安装后端依赖
cd backend && python -m pip install -r requirements.txt
```

TypeScript 检查（无输出=通过）：`cd frontend && npx tsc --noEmit`

## 架构

```
frontend (Next.js 16 + shadcn/ui v4 "base-nova" + TailwindCSS 4)
    │
    ├─ POST /api/chat              → 创建任务，返回 task_id
    ├─ GET  /api/history           → 获取历史任务列表
    ├─ GET  /api/history/{id}      → 获取任务消息（支持 ?limit=N&offset=M 分页）
    ├─ GET  /api/download/{file}   → 下载根 outputs/ 文件（兼容旧链接）
    ├─ GET  /api/download/{t}/{f}  → 下载任务专属 outputs/{task_id}/ 文件
    ├─ GET  /api/skills            → 列出全局 skills
    └─ WebSocket /ws/{task_id}     → 实时流式推送 Agent 日志
              │
backend (FastAPI + WebSocket)
    │
    ├─ main.py                   服务入口 + API 路由 + 历史持久化 + skills 生成
    ├─ agent/
    │   ├─ claude_agent.py       ★ 主 Agent：子进程调用 `claude -p --output-format stream-json`
    │   ├─ playwright_agent.py   ★ 回退 Agent：Playwright 直控浏览器 + regex 提取邮箱
    │   ├─ exporter.py           文件导出模块（6 种格式：CSV/XLSX/MD/HTML/PDF/DOCX）
    │   ├─ cleaner.py            数据清洗模块（6 步清洗管道）
    │   └─ history.py            对话历史持久化（JSON 文件存储 + 原子写入）
    ├─ data/                     历史对话 JSON 文件
    ├─ outputs/                  输出文件根目录（每任务独立子目录 outputs/{task_id}/）
    └─ skills/                   全局技能知识库（任务完成后自动生成）
```

### 任务隔离工作空间

每个任务使用 `outputs/{task_id}/` 独立子目录，任务完成后生成 skill 到 `skills/` 全局目录。关键函数：
- `exporter.get_task_dir(task_id)` — 返回任务专属输出目录
- `exporter.cleanup_task_dir(task_id)` — 删除任务输出目录
- `main._generate_skills(task_id, task_data)` — 从完成任务提取可复用知识

### 对话历史持久化

- 存储位置：`backend/data/index.json`（索引）+ `backend/data/{task_id}.json`（完整消息）
- 用户消息和所有 WebSocket 日志在流式传输时实时写入
- 任务完成/失败时更新状态
- **原子写入**：`_atomic_write()` → temp file + `os.replace()`，防止写入中断导致文件损坏
- **分页**：`GET /api/history/{task_id}?limit=N&offset=M` 支持按消息数量分页加载
- **恢复**：WebSocket 重连时从 history 恢复任务消息（不再依赖内存 tasks 字典）
- 任务完成后自动生成 skill 到 `backend/skills/` 目录

### Agent 限制

| 参数 | 值 |
|------|----|
| MAX_STEPS | 2000 |
| TIMEOUT_SECONDS | 3600 (1小时) |
| max-budget-usd | 20.0 |

### Agent 双轨制

`ClaudeAgent` 是主 Agent。如果 `claude` CLI 不可用或执行失败，自动回退到 `PlaywrightAgent`（不依赖任何外部 API key，自包含运行）。

Claude Code 使用 DeepSeek `deepseek-v4-pro` 模型（通过 `claude --model deepseek-v4-pro` 指定）。

### WebSocket 消息类型

| type | 说明 | 额外字段 |
|------|------|---------|
| `log` | 普通日志 | `message`, `timestamp` |
| `download` | 文件下载链接 | `message`, `filename`, `url` |
| `error` | 错误信息 | `message` |
| `done` | 任务结束 | `message` |

下载 URL 格式：`/api/download/{task_id}/{filename}`（新版）或 `/api/download/{filename}`（兼容旧版）。

## 关键实现细节

### 子进程调用 claude CLI

`claude_agent.py` 使用 `asyncio.create_subprocess_exec` 调用 `claude -p --output-format stream-json --verbose --permission-mode bypassPermissions`。stdout 逐行解析 JSON，提取 assistant message 中的 `text` 和 `tool_use` 块，作为 log 推送。

`CRAWL_STRATEGY_PROMPT` 自动注入爬取任务，其中 `{{TASK_OUTPUT_DIR}}` 占位符被替换为 `outputs/{task_id}/` 提示。

### 大学 URL 映射与推断

`playwright_agent.py` 包含 35 所高校的硬编码 URL 映射表。对于未收录高校：
1. 正则提取大学名称 + `_infer_university_url()` 拼音缩写推断
2. 仍无法匹配时返回搜索引擎建议（不再直接失败）

### 前端布局约束

flex 全视口布局必须使用 `h-full` 链 + `overflow-hidden` + `min-h-0` 模式：
- `body/html` 设置 `overflow-hidden`
- flex 容器使用 `h-full overflow-hidden`
- 滚动区域使用 `ScrollArea` 组件 + `min-h-0`

### shadcn/ui 版本

使用 shadcn/ui v4 "base-nova" style（基于 `@base-ui/react`，不是 Radix）。安装组件用 `npx shadcn@latest add -d <name>`，默认输出到 `@/components/ui`。

### 环境变量

| 变量 | 位置 | 默认值 | 说明 |
|------|------|--------|------|
| `NEXT_PUBLIC_BACKEND_URL` | `frontend/.env.local` | `http://localhost:8000` | 前端 API 地址 |
| `CORS_ORIGINS` | 后端环境 | `http://localhost:3000,http://127.0.0.1:3000` | 允许的跨域源（逗号分隔） |

## 设计系统

遵循 DESIGN.md（OpenAI/ChatGPT 风格），核心原则：95% 中性色 + 5% 绿色强调。

| 变量 | 值 |
|------|----|
| `--primary` / accent | `#10A37F` |
| `--background` (light) | `#FFFFFF` |
| `--background` (dark) | `#202123` |
| `--muted-foreground` | `#6E6E80` / `#9A9AA5` |
| `--border` | `rgba(0,0,0,0.06)` / `rgba(255,255,255,0.08)` |
| `--radius` | `0.75rem` |
| 缓动函数 | `cubic-bezier(0.22, 1, 0.36, 1)` |
| 动画时长 | 400ms (ambient), 250ms (standard) |

消息气泡：用户 `rounded-br-md bg-primary`，Agent `rounded-tl-md bg-muted/50`，日志 `font-mono animate-fade-in`。

深色模式通过 `next-themes` 的 `class` 策略驱动，`.dark` 类名切换 CSS 变量。

## 邮箱提取与反爬

- 正则：`[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`
- 反爬恢复：`[at]` → `@`, `(at)` → `@`, `#@` → `@`, `[@]` → `@`
- 数据清洗管道：格式规范化 → 姓名验证 → 邮箱格式验证 → 排除公共邮箱 → 去重 → 职称清洗

## 项目阶段

| Phase | 状态 | 内容 |
|-------|------|------|
| Phase 1 | ✅ | Chat UI (Next.js + shadcn/ui) |
| Phase 2 | ✅ | Fake Agent Runtime (FastAPI + WebSocket) |
| Phase 3 | ✅ | Claude Code Agent 接入 + Playwright 回退 |
| Phase 4 | ✅ | 多格式导出 + 下载端点 |
| Phase 5 | ✅ | 任务隔离 + 原子写入 + 分页 + URL 推断 + skills 系统 |
| Phase 6 | 🔲 | 增强高校抓取能力（PDF/OCR/详情页深层爬取） |

## 安全注意

- 下载端点包含路径遍历防护（拒绝 `..`、`/`、`\`，`_safe_resolve()` 验证）
- `BACKEND_URL` 通过 `NEXT_PUBLIC_BACKEND_URL` 环境变量配置（`frontend/.env.local`）
- CORS 通过 `CORS_ORIGINS` 环境变量配置（逗号分隔）
- 历史任务列表由后端 API 动态加载
- 任务 ID 用于子目录名时经过 `replace("/", "_")` 等安全处理