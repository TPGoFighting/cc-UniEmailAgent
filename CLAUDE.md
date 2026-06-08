# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

UniEmail Agent — 用户输入自然语言任务（如「抓取南京大学计算机学院教师邮箱」），AI Agent 自动操作浏览器、提取教师邮箱、导出 CSV/XLSX/HTML/PDF/DOCX/MD 六种格式。支持智能意图路由（全新爬取/增量补充/简单问答）、后置反思与技能自动沉淀、SMTP 批量发送邮件。

## 启动与测试命令

```bash
# 后端 (FastAPI, port 8070)
cd backend && python -m uvicorn main:app --port 8070 --reload

# 前端 (Next.js 16, Turbopack, port 3000)
cd frontend && npm run dev

# 安装后端依赖
cd backend && python -m pip install -r requirements.txt

# 运行测试
cd backend && python -m pytest tests/ -v
cd backend && python -m pytest tests/test_feature_contracts.py -v  # 单文件

# TypeScript 检查
cd frontend && npx tsc --noEmit
```

## 后端架构

```
backend/
├── main.py                     ★ 服务入口 + API 路由 + 历史持久化 + 技能生成 + 质量门 + 进度泵
├── constants.py                共享常量和工具函数（邮箱正则、大学名正则等）
│
├── agent/
│   ├── claude_agent.py         ★ 主 Agent：子进程调用 claude CLI（stream-json 模式）
│   ├── hermes_agent.py         ★ 动态编排引擎（Hermes CLI 决策循环，claude 执行）
│   ├── graph_agent.py          ★ LangGraph 状态机模式（环境变量 GRAPH_AGENT_ENABLED=true 启用）
│   ├── playwright_agent.py     ★ 回退 Agent：Playwright 直控浏览器 + regex 提取邮箱
│   ├── intent_router.py        ★ 三路意图分类（simple_query / new_crawl / incremental）
│   ├── exporter.py             六格式导出模块（CSV/XLSX/MD/HTML/PDF/DOCX）
│   ├── cleaner.py              六步清洗管道（姓名验证/邮箱格式/去重/职称清洗/公共邮箱过滤/域名白名单）
│   ├── skill_manager.py        ★ 技能库双向流转（前置读取注入 + 后置反思去重写入）
│   ├── memory.py               ★ Mem0 持久记忆系统（Qdrant 向量库，环境变量 MEM0_ENABLED 控制）
│   ├── history.py              对话历史持久化（JSON 文件 + 原子写入 + 分页）
│   ├── guardrails.py           输入输出安全检测
│   ├── evaluator.py            ★ IntellAgent 自动质量评估（邮箱覆盖率/学院覆盖率评分）
│   ├── tracing.py              LangSmith 全链路追踪
│   ├── mailer.py               SMTP 邮件发送模块（预览/发送/导出发送记录）
│   ├── universities.py         高校目录索引 + 表格数据 CRUD（985/211 分类）
│   ├── proxy_manager.py        代理管理器（区域切换/封锁检测）
│   └── crawler_cache.py        爬虫缓存模块
│
├── data/                       持久化数据
│   ├── index.json              历史任务索引
│   ├── {task_id}.json          各任务对话历史
│   ├── university_urls.json    高校名称→URL 映射表（35+ 所高校）
│   ├── universities_catalog.json 教育部高校目录缓存（985/211/普通）
│   └── mem0_qdrant/            Mem0 Qdrant 本地向量数据库
│
├── outputs/                    输出文件根目录
│   └── {task_id}/              每任务独立子目录（CSV/XLSX/MD/HTML/PDF/DOCX）
│
├── skills/                     ★ 全局技能知识库（自动沉淀）
│   ├── crawl_knowledge.md      汇总式经验（含所有高校爬取技巧/URL 模式/踩坑记录）
│   ├── global_crawling_rules.md 实时更新的策略发现
│   └── {大学名}_{task_id}.json  任务专属元数据
│
├── tests/
│   └── test_feature_contracts.py  功能契约测试
│
└── patches/
    └── UX-design.md            UX 设计改进补丁
```

### Agent 选择策略（三选一，自动判断优先级）

1. **GraphAgent** — `GRAPH_AGENT_ENABLED=true` 时启用，LangGraph 状态机
2. **HermesOrchestrator** — 检测到 `hermes` CLI 时启用，动态编排（每次决策循环调用 hermes CLI，执行用 ClaudeAgent）
3. **ClaudeAgent** — 兜底方案，`claude -p --output-format stream-json --verbose --permission-mode bypassPermissions`

### 意图路由（三路分类）

`intent_router.py` 使用 DeepSeek/OpenAI API 或本地关键词兜底，将用户输入分为三类：

| 意图 | 含义 | 行为 |
|------|------|------|
| `simple_query` | 数据查询/统计 | 读已有文件 + LLM 分析回答，不触发爬虫 |
| `new_crawl` | 全新爬取 | 清理 output 目录，注入完整爬取策略 prompt |
| `incremental` | 增量补充 | 保留已有数据，注入增量上下文，识别缺口补充 |

### 消息过滤系统（Phase 1）

`main.py` 包含两层过滤引擎，控制哪些 Agent 输出展示给用户：

- **结构化解析**：`_parse_structured_log()` — 从日志中提取 `stage`（阶段导航）和 `stats`（学院完成进度）
- **技术消息隐藏**：`TECHNICAL_PATTERNS` 正则表（~30 条）过滤工具调用、JSON、Traceback、Hermes 决策等
- **错误友好翻译**：`_translate_error()` — HTTP 403→「页面暂时无法访问」，timeout→「页面加载超时」
- **进度泵**：`_progress_pump_llm()` — 每 30 秒用 LLM 生成一句进度描述推送到前端

### 质量门 + 自动评估

Agent 完成后自动执行两阶段质量检查：

1. **`_validate_crawl_output()`** — 清理导航词冒充姓名、过滤非目标学院数据、修复邮箱格式、去重（自动写回 CSV）
2. **`IntellAgent 评估`** — `evaluator.py` 计算邮箱覆盖率/学院覆盖率/质量评分，生成质量报告 JSON

### 邮件发送模块

通过 SMTP 直接发送邮件，支持：
- `build_preview()` — 模板预览（限制条数，替换 `{{name}}`、`{{email}}` 等变量）
- `create_send_job()` — 异步发送任务（支持高量确认）
- `detect_smtp_provider()` — 自动识别邮箱的 SMTP 服务器
- `verify_smtp_config()` — 测试 SMTP 连接

### 技能系统（双向流转）

**前置读取**：`skill_manager.load_skills_prompt(uni_name)` — 按大学名匹配 Section，只注入相关部分

**后置反思**：任务完成后 `_post_task_reflection()` — 从消息中提取 `[REFLECTION]...[/REFLECTION]` 标签，或调用 LLM 分析日志 → 去重（相似度阈值 0.55）→ 写入 `crawl_knowledge.md`

**Mem0 双写**：同时写入 Qdrant 向量库（`MEM0_ENABLED=true` 时），支持语义搜索历史经验

## 前端架构

```
frontend/
├── app/
│   ├── page.tsx                主页面（Sheet 侧边栏 + ChatArea + ErrorBoundary）
│   ├── globals.css             全局样式（OpenAI 风格 95%中性+5%绿）
│   └── layout.tsx              根布局（ThemeProvider + Onboarding）
│
├── components/
│   ├── ui/                     shadcn/ui v4 "base-nova" 组件（基于 @base-ui/react）
│   │   ├── button.tsx, input.tsx, scroll-area.tsx, sheet.tsx, separator.tsx
│   │   ├── dropdown-menu.tsx, tooltip.tsx, dialog.tsx
│   └── 业务组件
│       ├── chat-area.tsx       主聊天区域（消息列表 + 输入 + 状态）
│       ├── chat-input.tsx      输入框（自动缩放 + 快捷键 + 状态指示器）
│       ├── chat-message.tsx    单条消息气泡（用户/Agent/日志/下载/评估）
│       ├── sidebar.tsx         侧边栏（任务列表 + 搜索 + 筛选）
│       ├── sidebar-task-item.tsx 任务项（标题/状态/时间/pin/操作菜单）
│       ├── university-workspace.tsx 高校数据工作台（表格/图表/过滤）
│       ├── mail-workspace.tsx  邮件发送工作台
│       ├── crawl-progress.tsx  爬取进度展示
│       ├── crawl-progress-panel.tsx 进度面板（实时 Stats + 阶段导航）
│       ├── task-result-panel.tsx 任务结果面板
│       ├── completion-card.tsx 任务完成卡片
│       ├── result-summary-card.tsx 结果汇总卡片
│       ├── stage-stepper.tsx   阶段步进器
│       ├── status-ticker.tsx   状态轮播
│       ├── live-stats-counter.tsx 实时统计计数器
│       ├── agent-activity-card.tsx Agent 活动卡片
│       ├── empty-state.tsx     空状态（引导创建第一个任务）
│       ├── connection-banner.tsx 连接状态横幅
│       ├── error-alert.tsx     错误提示
│       ├── confirm-dialog.tsx  确认对话框
│       ├── edit-message-dialog.tsx 编辑消息对话框
│       ├── message-actions.tsx 消息操作菜单
│       ├── typing-indicator.tsx 打字指示器
│       ├── search-bar.tsx      搜索条
│       ├── shiki-highlight.tsx 代码高亮
│       ├── onboarding-tour.tsx 新手引导
│       ├── undo-toast.tsx      Toast 撤销操作
│       ├── theme-provider.tsx  主题提供者
│       └── theme-toggle.tsx    主题切换
│
├── hooks/
│   ├── queries/                 React Query hooks
│   │   ├── use-history.ts      任务列表查询
│   │   ├── use-task-messages.ts 任务消息查询（分页）
│   │   └── use-task-mutations.ts 任务 CRUD 变更
│   ├── use-agent-chat.ts       Agent 对话状态机
│   ├── use-task-stream.ts      WebSocket 流式消息处理
│   ├── use-auto-resize.ts      自动缩放
│   ├── use-auto-scroll.ts      自动滚动
│   └── use-notification.ts     通知管理
│
├── stores/                      Zustand 状态管理
│   ├── chat-store.ts           对话状态（消息/连接/输入）
│   ├── task-store.ts           任务列表状态
│   └── ui-store.ts             UI 状态（侧边栏/主题/面板/引导）
│
├── services/
│   ├── api.ts                  REST API 封装（fetch + error handling）
│   ├── websocket.ts            WebSocket 管理（自动重连/心跳/消息路由）
│   └── classify.ts             意图分类（后端 API 包装）
│
└── lib/
    ├── types.ts                全局 TypeScript 类型定义
    ├── utils.ts                工具函数
    └── mock-data.ts            开发用模拟数据
```

### 前端状态流

```
用户输入 → useAgentChat (状态机)
  → POST /api/chat (获取 task_id)
  → WebSocket /ws/{task_id} (消息推送)
  → websocket.ts (自动重连/心跳/消息路由)
  → chat-store (实时更新消息列表)
  → task-store (更新侧边栏任务状态)
  → 组件渲染 (chat-message / crawl-progress / stage-stepper)
```

## API 路由全景

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/chat` | 创建任务（返回 task_id） |
| POST | `/api/classify` | 三路意图分类 |
| GET | `/api/history` | 任务列表（支持搜索） |
| GET | `/api/history/{id}?limit=N&offset=M` | 任务消息（分页） |
| PATCH | `/api/history/{id}/rename` | 重命名任务 |
| PATCH | `/api/history/{id}/pin` | 置顶/取消置顶 |
| DELETE | `/api/history/{id}` | 删除任务+清理输出 |
| WS | `/ws/{task_id}` | 实时流式推送 |
| POST | `/api/agent/terminate` | 强制终止 Agent |
| GET | `/api/agent/active` | 查看活跃任务 |
| GET | `/api/download/{file}` | 下载（旧版兼容） |
| GET | `/api/download/{t}/{f}` | 下载（任务隔离） |
| GET | `/api/skills` | 全局技能列表 |
| GET | `/api/universities` | 高校目录（按省份/层次/搜索过滤） |
| GET | `/api/universities/{name}/records` | 高校产出记录 |
| GET | `/api/universities/{name}/table` | 高校表格数据（分页/搜索/过滤） |
| POST | `/api/universities/{name}/files` | 上传文件 |
| DELETE | `/api/universities/{name}/files` | 删除文件 |
| PATCH | `/api/universities/{name}/files` | 重命名文件 |
| POST | `/api/universities/{name}/table/rows` | 添加行 |
| PUT | `/api/universities/{name}/table/rows/{idx}` | 更新行 |
| DELETE | `/api/universities/{name}/table/rows/{idx}` | 删除行 |
| POST | `/api/universities/{name}/clean` | 一键清洗表格 |
| POST | `/api/universities/{name}/export` | 导出表格为指定格式 |
| POST | `/api/smtp/detect` | 检测 SMTP 服务器 |
| POST | `/api/smtp/verify` | 验证 SMTP 配置 |
| POST | `/api/mail/preview` | 邮件模板预览 |
| POST | `/api/mail/send` | 发送邮件 |
| GET | `/api/mail/jobs/{id}` | 发送任务状态 |
| GET | `/api/mail/jobs/{id}/export` | 导出发送记录 |

## WebSocket 消息类型

| type | 来源 | 说明 |
|------|------|------|
| `log` | Agent 思考/日志 | 前端默认折叠在日志面板（经 Phase1 过滤） |
| `text` | Agent 最终输出 | 显示为 Agent 消息气泡 |
| `download` | 文件生成 | 含 `filename` 和 `url`，前端展示下载按钮 |
| `error` / `error_user` | 异常 | `error_user` 是经友好翻译的版本 |
| `done` | 任务结束 | 含摘要文本 |
| `progress` | 进度泵 | 每 30 秒 LLM 生成的笼统进度描述 |
| `stats` | 实时统计 | `teachers_found`、`emails_extracted`、`departments_done` |
| `stage` | 阶段导航 | 阶段名和进度百分比 |
| `summary` | 完成汇总 | `university`、`total_teachers`、`total_emails`、`duration` |
| `trace` | LangSmith | `run_id` 和 `trace_url` |
| `eval` | 质量评估 | `quality_score`、`passed`、`warnings`、`email_rate` |
| `file` | 脚本文件 | 只写历史不推送到前端 |
| `text` | 简单问答 | 非爬取任务的 LLM 流式回答 |

## 关键实现细节

### 爬取流程（完整 Pipeline）

```
用户输入 → IntentRouter（三路分类）
  ↓ NEW_CRAWL / INCREMENTAL
技能注入（load_skills_prompt → crawl_knowledge.md + global_crawling_rules.md + Mem0）
  ↓
数据规范注入 + 任务隔离红线 + 用户可读输出指令 + 合并规则
  ↓
Claude Code CLI 子进程（claude -p --output-format stream-json）
  ↓ 或 Hermes 动态编排 + Claude 执行 / Playwright 回退
流式输出解析（stream-json → text/tool_use/result）
  ↓
质量门（脏数据清洗/学院范围校验/去重）
  ↓
IntellAgent 自动评估（邮箱覆盖率/质量评分）
  ↓
技能反思沉淀（[REFLECTION] 标签 / LLM 分析 → 去重 → 写入 crawl_knowledge.md）
  ↓
Mem0 双写（异步同步到 Qdrant 向量库）
```

### 子进程调用 claude CLI

`claude_agent.py` 在 Windows 上使用线程 + `subprocess.Popen` + `asyncio.Queue` 桥接（因为 Windows SelectorEventLoop 不支持 `create_subprocess_exec`）。参数：
- `--print --output-format stream-json --verbose --no-session-persistence`
- `--permission-mode bypassPermissions --allowedTools ["Read","Edit","Write","Bash","Glob","Grep","WebSearch","WebFetch"]`
- `--max-budget-usd 20.0`

stdout 逐行解析 JSON，提取 `assistant` 消息的 text 和 tool_use 块。结果中 `[FILES]...[/FILES]` 声明块被解析为下载文件。

### 任务隔离工作空间

每个任务使用 `outputs/{task_id}/` 独立子目录，task_id 经过 `replace("/", "_")` 等安全处理。下载端点包含路径遍历防护（`_safe_resolve()` 验证路径在允许范围内）。

### 对话历史持久化

- `data/index.json`（索引）+ `data/{task_id}.json`（完整消息）
- 原子写入：temp file + `os.replace()`
- 分页加载：`?limit=N&offset=M`
- WebSocket 重连时从 history 恢复

### 大学 URL 映射

- `data/university_urls.json` 包含 35+ 所高校的硬编码映射
- `playwright_agent.py` 的 `_infer_university_url()` 通过缩写映射（njust→南京理工、nuaa→南航等）推断
- 意图路由的 `_extract_university()` 从消息中正则提取大学全名

### 高校数据管理

`universities.py` 支持完整的文件/表格 CRUD 操作：
- 985/211 分类（来自教育部官方数据）
- 表格数据的分页/搜索/过滤/排序
- 一键清洗去重
- 多格式导出（CSV/XLSX/MD/HTML/PDF/DOCX）

### 环境变量

| 变量 | 位置 | 默认值 | 说明 |
|------|------|--------|------|
| `NEXT_PUBLIC_BACKEND_URL` | `frontend/.env.local` | `http://localhost:8000` | 前端 API 地址 |
| `CORS_ORIGINS` | 后端环境 | `http://localhost:3000,http://127.0.0.1:3000` | 允许的跨域源 |
| `DEEPSEEK_API_KEY` | `backend/.env` | — | 意图分类/简单问答/反思总结 |
| `OPENAI_API_KEY` | `backend/.env` | — | DeepSeek 回退 |
| `ANTHROPIC_API_KEY` | `backend/.env` | — | OpenAI 回退 |
| `MEM0_ENABLED` | 后端环境 | `false` | 是否启用 Mem0 持久记忆 |
| `GRAPH_AGENT_ENABLED` | 后端环境 | `false` | 是否启用 LangGraph 模式 |
| `LANGSMITH_API_KEY` | 后端环境 | — | LangSmith 追踪 |
| `SMTP_*` | 后端环境 | — | SMTP 邮件配置 |

### 安全注意

- 下载端点防路径遍历：拒绝 `..`、`/`、`\`，用 `_safe_resolve()` 验证
- CORS 通过 `CORS_ORIGINS` 逗号分隔配置
- 输入输出安全检测：`guardrails.py` 拦截恶意内容
- 邮箱公式注入防护：CSV 导出时以 `= + - @` 开头的字段加单引号前缀

### 设计系统

遵循 OpenAI/ChatGPT 风格，核心原则：95% 中性色 + 5% 绿色强调（`#10A37F`）。
- 深色模式通过 `next-themes` 的 `class` 策略驱动
- shadcn/ui v4 "base-nova" style（基于 `@base-ui/react`，不是 Radix）
- 安装组件：`npx shadcn@latest add -d <name>`
- 缓动函数：`cubic-bezier(0.22, 1, 0.36, 1)`

## 项目阶段

| Phase | 状态 | 内容 |
|-------|------|------|
| Phase 1 | ✅ | Chat UI (Next.js + shadcn/ui) |
| Phase 2 | ✅ | Fake Agent Runtime (FastAPI + WebSocket) |
| Phase 3 | ✅ | Claude Code Agent + Playwright 回退 |
| Phase 4 | ✅ | 多格式导出 + 下载端点 |
| Phase 5 | ✅ | 任务隔离 + 原子写入 + 分页 + URL 推断 + 技能系统 |
| Phase 6 | ✅ | 意图路由 + 技能双向流转 + 任务隔离架构 |
| Phase 7 | ✅ | 高校库表格 + Agent 错误处理增强 + WS 消息流优化 |
| Phase 8 | ✅ | 简单对话实时显示 + API Key 提前加载 |
| Phase 9 | ✅ | Hermes 编排引擎 + Mem0 持久记忆 + 质量门 |
| Phase 10 | 🔲 | 增强高校抓取能力（PDF/OCR/详情页深层爬取） |
