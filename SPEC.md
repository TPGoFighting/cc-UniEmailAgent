# SPEC.md — ClaudeCode Chat UI（飞书 Agent 风格）

## 1. 项目目标

开发一个类似“飞书 AI Agent”的 Web 应用。

用户通过聊天框输入任务：

```text id="m4r8xa"
帮我抓取南京大学计算机学院教师邮箱
```

系统自动：

1. 调用 ClaudeCode Agent
2. 操作浏览器
3. 实时返回执行日志
4. 最终生成 CSV/XLSX 文件
5. 提供下载链接

核心目标：

```text id="q2y7tn"
让用户感觉 AI 正在替自己上网干活。
```

本项目重点：

- Agent 工作流体验
- 类 ChatGPT UI
- 实时日志流
- 浏览器操作感

而不是：

```text id="v5k1pm"
企业级数据治理平台
```

---

# 2. MVP 范围

第一版（MVP）必须只包含：

✅ Chat UI  
✅ WebSocket 日志流  
✅ ClaudeCode 接入  
✅ Playwright 浏览器控制  
✅ CSV/XLSX 导出  
✅ 文件下载

禁止：

❌ 微服务  
❌ Docker  
❌ Redis  
❌ PostgreSQL  
❌ 用户系统  
❌ 权限系统  
❌ 复杂调度  
❌ Kubernetes  
❌ Celery  

保持极简。

---

# 3. 技术栈

## Frontend

- Next.js 15
- TypeScript
- TailwindCSS
- shadcn/ui

---

## Backend

- FastAPI
- Python 3.12+

---

## Agent

- OpenClaw

---

## Browser

- Playwright

---

## Export

- pandas
- openpyxl

---

# 4. UI 设计要求

整体风格：

```text id="a8p2ws"
类似 ChatGPT / 飞书 AI Agent
```

---

## 页面布局

```text id="r1n6ky"
┌────────────────────────────┐
│ 左侧：历史任务列表          │
├────────────────────────────┤
│                            │
│ 右侧：聊天区域              │
│                            │
│ 用户输入任务                │
│ AI 实时输出日志             │
│                            │
│ [下载 CSV]                 │
│                            │
└────────────────────────────┘
```

---

## UI 功能

### 必须实现

✅ 深色模式  
✅ markdown 渲染  
✅ 自动滚动  
✅ 响应式布局  
✅ 流式日志显示  
✅ loading 动画  

---

## Agent 日志样式

示例：

```text id="y9m4te"
[12:01]
正在打开南京大学官网...

[12:02]
进入计算机学院页面...

[12:03]
发现教师列表...

[12:04]
正在导出 CSV...
```

日志必须：

```text id="z0t7pl"
逐条流式显示
```

不能一次性返回。

---

# 5. 后端架构

整体结构：

```text id="d5v3rx"
Frontend
    ↓
FastAPI
    ↓
OpenClaw Runtime
    ↓
Playwright Browser
```

---

# 6. 后端接口

---

## POST /api/chat

用户发送任务。

请求：

```json id="f8k1jq"
{
  "message": "帮我抓取南京大学教师邮箱"
}
```

返回：

```json id="q7c9vh"
{
  "task_id": "xxx"
}
```

---

## WebSocket /ws/:task_id

实时推送 Agent 日志。

示例：

```json id="x4n2ua"
{
  "type": "log",
  "message": "正在打开网页..."
}
```

---

## GET /api/download/:filename

下载 CSV/XLSX 文件。

---

# 7. 开发阶段（严格按顺序）

---

# Phase 1 — Chat UI

目标：

```text id="m7v5kd"
先完成 ChatGPT 风格聊天界面
```

要求：

- mock 数据
- 不接后端
- UI 先跑起来

---

## Claude Code 任务

```text id="b3k8wy"
实现 ChatGPT 风格聊天 UI。

技术：
- Next.js 15
- TailwindCSS
- shadcn/ui

要求：
- 左侧历史任务栏
- 右侧聊天区
- markdown 渲染
- 深色模式
- 自动滚动
- 响应式布局

先使用 mock 数据。
不要连接后端。
```

---

# Phase 2 — Fake Agent Runtime

目标：

```text id="v1q9sx"
让 AI “看起来正在工作”
```

后端先不要接 ClaudeCode。

只返回 fake logs。

---

## Fake Logs 示例

```python id="n6r4pz"
yield "打开南京大学官网..."
yield "进入计算机学院..."
yield "发现教师列表..."
yield "导出 CSV..."
```

---

## Claude Code 任务

```text id="t8y3mj"
实现 Fake Agent Runtime。

要求：

1. FastAPI 后端
2. websocket 流式推送日志
3. 每秒推送一条日志
4. 前端实时显示
```

---

# Phase 3 — 接入 ClaudeCode

目标：

```text id="u2k7ra"
将 Fake Agent 替换为真实 Agent
```

---

## 架构

```text id="k4m1xn"
Chat UI
 ↓
FastAPI
 ↓
ClaudeCode
 ↓
Playwright
```

---

## Claude Code 任务

```text id="c9w5ql"
将 Fake Agent 替换为 ClaudeCode。

要求：

1. 用户输入任务
2. ClaudeCode 自动执行浏览器任务
3. 实时返回 Agent 日志
4. 前端流式显示
```

---

## 必须增加限制

```python id="r7x2nv"
MAX_STEPS = 30
MAX_RETRIES = 3
TIMEOUT_SECONDS = 300
```

防止：

- 无限循环
- Token 爆炸
- 浏览器卡死

---

# Phase 4 — 文件导出

目标：

```text id="e6j8tp"
真正交付结果文件
```

---

## Agent 输出格式

```python id="m0q4ys"
[
  {
    "name": "张三",
    "email": "zhangsan@nju.edu.cn"
  }
]
```

---

## Claude Code 任务

```text id="w3p9ku"
实现 CSV/XLSX 导出功能。

要求：

1. 使用 pandas dataframe
2. 自动导出 csv
3. 自动导出 xlsx
4. 保存到 outputs 目录
5. 返回下载链接
6. 前端显示下载按钮
```

---

# Phase 5 — 真正高校抓取能力

目标：

```text id="j5f1zx"
让 ClaudeCode 真正抓取高校数据
```

---

## 必须支持

### 1️⃣ 教师列表页

自动识别：

- 教师卡片
- 姓名
- 邮箱
- 职称

---

### 2️⃣ 教师详情页

自动进入详情页继续提取。

---

### 3️⃣ PDF

自动下载 PDF 并解析。

---

### 4️⃣ OCR

自动识别图片邮箱。

---

### 5️⃣ 邮箱恢复

处理：

```text id="g2r8nm"
[at]
(at)
#@
反转字符串
```

---

## Claude Code 任务

```text id="p4y6lc"
增强 ClaudeCode 高校抓取能力。

要求：

1. 自动识别教师列表
2. 自动进入详情页
3. 自动处理 PDF
4. 自动 OCR 图片邮箱
5. 自动恢复混淆邮箱
6. 自动校验邮箱格式
```

---

# 8. 项目目录结构

```text id="z1x4qw"
project/
├── frontend/
│   ├── app/
│   ├── components/
│   └── lib/
│
├── backend/
│   ├── main.py
│   ├── agent/
│   │   ├── runtime.py
│   │   ├── exporter.py
│   │   └── extractor.py
│   │
│   ├── outputs/
│   └── utils/
│
└── README.md
```

---

# 9. 最重要的开发原则

---

## 原则 1

```text id="u9c5dv"
先跑起来。
```

不要一开始追求完美架构。

---

## 原则 2

```text id="h7m3rz"
先做“Agent 工作感”
```

而不是：

```text id="f1k8tp"
先做复杂自治系统
```

---

## 原则 3

```text id="n2x6qy"
先 fake。
再真实。
```

---

## 原则 4

```text id="s8v4mw"
不要过度工程化。
```

---

# 11. 日志按钮规则

## 调试用途

日志按钮（“开发调试：显示 Agent 原始日志”）是**开发专用功能**，不属于产品功能。

## 行为规范

| 环境 | 日志按钮 | 日志内容 |
|------|----------|----------|
| 开发 (`NEXT_PUBLIC_DEBUG=true`) | 显示按钮 | 打开后显示全部 Agent 原始日志（`role: "log"` 消息的全量原始内容） |
| 生产（默认） | **不渲染** | **不显示** |

## 实现规则

1. 日志按钮用 `process.env.NEXT_PUBLIC_DEBUG === 'true'` 条件渲染。生产构建中默认为 `false`，按钮不出现。
2. 日志消息（`role: "log"`）在生产构建中始终被过滤掉，不进入聊天显示列表。
3. 日志内容不做截断。打开日志时 `message.content` 全量渲染，使用等宽字体 + `break-all` 确保长文本完整显示。
4. 后端发送的所有 `type: "log"` 消息以 `role: "log"` 独立存储，**不拼接进 agent 消息**，由前端 `showDebug` 统一控制可见性。

---

# 12. 最终目标

最终产品应该像：

```text id="y6j1kn"
“用户正在和一个会上网干活的 AI 对话”
```

而不是：

```text id="r3w7px"
传统后台管理系统
```
