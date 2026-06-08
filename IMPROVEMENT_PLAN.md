# UniEmailAgent 8 项改进详细实施计划

> 日期: 2026-06-04
> 基于 NirDiamant/agents-towards-production (20.6k ⭐) 的 28 个生产级教程对照分析

---

## 总体依赖关系

```
P0 ────────────────────────────────────
  1. LangSmith Tracing (独立)
  2. IntellAgent 评估 (独立)
P1 ────────────────────────────────────
  3. LlamaFirewall Guardrails (依赖 tracing 上下文)
  4. LangGraph 状态机 (替换 hermes_agent.py 状态管理)
P2 ────────────────────────────────────
  5. Mem0 持久记忆 (弱依赖 1, 可独立)
  6. MCP 协议封装 (独立模块)
  7. Docker Compose (独立, 最后做)
  8. Bright Data 反爬 (依赖 4 的 crawl_node)
```

**总估算工时: 12-18 人天 | 实际完成: ~1 天 (Claude Code 自动化)**

---

## 1. 🔷 LangSmith Tracing (P0)

**目标:** 替换 `_append_agent_log()` 纯文本日志，用 LangSmith SDK 实现全链路追踪。

### 当前状态
- `claude_agent.py` — `_append_agent_log()` 以纯文本追加写入 `{task_dir}/agent_output.log`
- `hermes_agent.py` — 多个 yield 点散布 log，无结构化 tracking
- WebSocket handler (`main.py`) — 逐条 `_append_agent_log()` 调用
- 无任何 trace ID / span ID 关联机制

### 子任务

| # | 任务 | 文件 | 耗时 | 依赖 |
|---|------|------|------|------|
| 1.1 | 安装 langsmith SDK + .env 配置 | `requirements.txt`, `.env` | 5min | — |
| 1.2 | 创建 `agent/tracing.py` — Client 单例 + 项目配置 | `backend/agent/tracing.py` (新) | 15min | 1.1 |
| 1.3 | main.py `_append_agent_log()` 注入 tracing span | `backend/main.py` | 15min | 1.2 |
| 1.4 | hermes_agent.py 决策循环包裹 trace 上下文 | `backend/hermes_agent.py` | 20min | 1.2 |
| 1.5 | claude_agent.py 三阶段 span (start→parse→end) | `backend/claude_agent.py` | 20min | 1.2 |
| 1.6 | 双写兼容 (LangSmith + 旧 log 同时写入) | — | 5min | 1.3-1.5 |

### 退出标准
- [x] 无 LANGCHAIN_API_KEY 时所有调用静默退化
- [x] 旧日志写入完全保留
- [x] WS 消息结构不变
- [x] import 通过: 6/6 函数

---

## 2. 🔷 IntellAgent 自动评估 (P0)

**目标:** 结构化测试用例自动验证爬取质量。

### 当前状态
- `main.py` — 已有 `_validate_crawl_output()` 做脏数据过滤+邮箱格式校验+去重
- 缺乏结构化测试用例定义和自动化评估框架

### 子任务

| # | 任务 | 文件 | 耗时 | 依赖 |
|---|------|------|------|------|
| 2.1 | 创建 `tests/test_crawl_quality.py` — pytest 框架 | `backend/tests/` (新) | 15min | — |
| 2.2 | 定义质量评分指标体系 (邮箱率≥70%, 脏数据≤5%) | `agent/evaluator.py` (新) | 20min | — |
| 2.3 | 学院全覆盖检测 | `agent/evaluator.py` | 15min | 2.2 |
| 2.4 | 邮箱格式正确率 + 域名有效性 | `agent/evaluator.py` | 15min | 2.2 |
| 2.5 | 持久化评估报告 `{task_dir}/quality_report.json` | `agent/evaluator.py` | 10min | 2.3,2.4 |
| 2.6 | 集成到 WS 生命周期 (done 前插入) | `main.py` | 15min | 2.5 |
| 2.7 | 3 个 fixture CSV (完美/中等/差) | `tests/fixtures/` (新) | 10min | — |

### 退出标准
- [x] 25/25 pytest 全通过
- [x] 每次爬取生成 `quality_report.json`
- [x] 完美数据 → score≥90
- [x] 无邮箱 → passed=False, warnings

---

## 3. 🔷 LlamaFirewall Guardrails (P1)

**目标:** HermesOrchestrator 入口 + Agent 输出加安全过滤层。

### 当前状态
- `intent_router.py` — 有意图分类但无安全过滤
- `playwright_agent.py` — 直接接收用户 prompt 控制浏览器
- 无 prompt injection 检测或敏感信息过滤

### 子任务

| # | 任务 | 文件 | 耗时 | 依赖 |
|---|------|------|------|------|
| 3.1 | 创建 `agent/guardrails.py` — 防火墙接口抽象 | `backend/agent/guardrails.py` (新) | 10min | — |
| 3.2 | 输入 guard: prompt injection 检测 | `agent/guardrails.py` | 20min | 3.1 |
| 3.3 | 输出 guard: 手机号/身份证号检测 | `agent/guardrails.py` | 15min | 3.1 |
| 3.4 | main.py prompt 构造前插入输入 guard | `main.py` | 10min | 3.2 |
| 3.5 | claude_agent.py 输出 yield 前插入输出 guard | `claude_agent.py` | 15min | 3.3 |

### 退出标准
- [x] `check_input("ignore all previous instructions")` → blocked=True
- [x] `sanitize_output("联系: 13800138000")` → "联系: [PHONE]"
- [x] 邮箱 `teacher@nju.edu.cn` 不被脱敏
- [x] 环境变量 GUARD_MODE=log_only|enforce

---

## 4. 🔷 LangGraph 状态机 (P1)

**目标:** 将 `plan→crawl→verify→complete` 硬编码重写为 LangGraph 有向图。

### 当前状态
- `hermes_agent.py` — 主循环用 `while` + `decision["phase"]` 做状态切换
- 状态跳转逻辑分散在 `_decide_next()` 和 `execute()` 之间
- 无状态持久化，任务中断后无法恢复

### 子任务

| # | 任务 | 文件 | 耗时 | 依赖 |
|---|------|------|------|------|
| 4.1 | 安装 langgraph + langchain-core | `requirements.txt` | 5min | — |
| 4.2 | 定义 State Schema + 4 个节点函数 | `agent/graph_builder.py` (新) | 30min | 4.1 |
| 4.3 | plan_node: 接收 intent → 输出策略 | `agent/graph_builder.py` | 20min | 4.2 |
| 4.4 | crawl_node: 调用 ClaudeAgent/PlaywrightAgent | `agent/graph_builder.py` | 25min | 4.2 |
| 4.5 | verify_node: 调用 evaluator 质量门 | `agent/graph_builder.py` | 15min | 4.2 |
| 4.6 | 条件边: plan→crawl, crawl→verify, verify→export/retry | `agent/graph_builder.py` | 15min | 4.5 |
| 4.7 | `agent/graph_agent.py` 对外接口 (兼容 HermesOrchestrator) | `agent/graph_agent.py` (新) | 20min | 4.3-4.6 |
| 4.8 | main.py 配置开关 GRAPH_AGENT_ENABLED | `main.py` | 10min | 4.7 |

### 退出标准
- [x] Graph 编译通过，4 nodes (plan/crawl/verify/export)
- [x] hermes_agent.py 零侵入 (0 langgraph 引用)
- [x] `GRAPH_AGENT_ENABLED=true` 启用, 默认 false

---

## 5. 🔷 Mem0 持久记忆 (P2)

**目标:** 自动从爬取历史中学习模式，替代手写 crawl_knowledge.md。

### 当前状态
- `skill_manager.py` — reflect_and_save() 写入 crawl_knowledge.md
- `main.py` — `_update_global_skills()` 解析历史消息
- skills/ 目录存 JSON 格式经验

### 子任务

| # | 任务 | 文件 | 耗时 | 依赖 |
|---|------|------|------|------|
| 5.1 | 安装 mem0ai | `requirements.txt` | 5min | — |
| 5.2 | `agent/memory.py` — CrawlMemory 类 | `backend/agent/memory.py` (新) | 20min | 5.1 |
| 5.3 | `add_crawl_experience()` — 存入经验 | `agent/memory.py` | 15min | 5.2 |
| 5.4 | `search_relevant()` — 语义检索 top-5 | `agent/memory.py` | 15min | 5.2 |
| 5.5 | main.py prompt 构建阶段用 Mem0 替换 skills 注入 | `main.py` | 20min | 5.4 |
| 5.6 | 反思阶段用 Mem0 替换 reflect_and_save | `main.py` | 15min | 5.3 |

### 退出标准
- [x] mem0ai 2.0.4 安装
- [x] import OK
- [x] MEM0_ENABLED=false 默认不启用 (双写兼容)

---

## 6. 🔷 MCP 协议封装 (P2)

**目标:** 将爬虫能力封装为标准 MCP Server。

### 当前状态
- `playwright_agent.py` — 核心爬虫逻辑
- `claude_agent.py` — 执行器
- 无标准 MCP 接口

### 子任务

| # | 任务 | 文件 | 耗时 | 依赖 |
|---|------|------|------|------|
| 6.1 | 安装 MCP SDK | `requirements.txt` | 5min | — |
| 6.2 | Tool: `crawl_faculty_emails` | `mcp_server.py` (新) | 20min | 6.1 |
| 6.3 | Tool: `query_crawl_result` | `mcp_server.py` | 15min | 6.2 |
| 6.4 | Tool: `export_crawl_data` | `mcp_server.py` | 10min | 6.2 |
| 6.5 | Resource: `crawl://{task_id}` | `mcp_server.py` | 10min | 6.2 |
| 6.6 | Prompt: `crawl_prompt` | `mcp_server.py` | 10min | 6.2 |
| 6.7 | `run_mcp.py` 双模式启动入口 | `backend/run_mcp.py` (新) | 10min | 6.2-6.6 |

### 退出标准
- [x] MCP SDK 1.27.0 安装
- [x] 3 Tools + 2 Resources + 1 Prompt
- [x] `python run_mcp.py --sse --port 8011` 可启动

---

## 7. 🔷 Docker Compose (P2)

**目标:** Backend + Frontend 容器化，一键启动。

### 子任务

| # | 任务 | 文件 | 耗时 |
|---|------|------|------|
| 7.1 | `backend/Dockerfile` — Python 3.11 + Playwright | `backend/Dockerfile` (新) | 20min |
| 7.2 | `frontend/Dockerfile` — Node 22 | `frontend/Dockerfile` (新) | 15min |
| 7.3 | `docker-compose.yml` — 双服务编排 | `docker-compose.yml` (新) | 20min |
| 7.4 | `.dockerignore` | `.dockerignore` (新) | 5min |

### 退出标准
- [x] `docker compose config` 验证通过
- [x] backend:8010 + frontend:3000
- [x] outputs/data/skills 卷挂载

---

## 8. 🔷 Bright Data 反爬 (P2)

**目标:** 住宅代理突破 412/403 封锁。

### 当前状态
- `playwright_agent.py` — 有 UA 伪装但使用 Datacenter IP
- 遇到 412/403/429 直接跳过学院

### 子任务

| # | 任务 | 文件 | 耗时 | 依赖 |
|---|------|------|------|------|
| 8.1 | `agent/proxy_manager.py` — 代理管理器 | `backend/agent/proxy_manager.py` (新) | 15min | — |
| 8.2 | Playwright browser context proxy 注入 | `playwright_agent.py` | 15min | 8.1 |
| 8.3 | 403/412 自动切换代理 zone | `proxy_manager.py` | 20min | 8.1 |
| 8.4 | BRIGHTDATA_TOKEN 环境变量 + DirectProxy fallback | `.env` | 10min | 8.1 |

### 退出标准
- [x] 无 BRIGHTDATA_TOKEN → DirectProxy (可完整空跑)
- [x] 有 token → BrightDataProxy (unblock/residential 切换)
- [x] playwright_agent.py 16 处代理集成点

---

## 执行顺序 (实际执行)

```
Phase 1: ①+②+⑤+⑧ (并行批次)
  ① LangSmith Tracing ✓
  ② IntellAgent ✓
  ⑤ Mem0 ✓
  ⑧ Bright Data ✓

Phase 2: ③ → ④ (P1 顺序)
  ③ LlamaFirewall Guardrails ✓
  ④ LangGraph 状态机 ✓

Phase 3: ⑥ → ⑦ (P2 剩余)
  ⑥ MCP 协议封装 ✓
  ⑦ Docker Compose ✓
```

**执行引擎:** Claude Code (deepseek-v4-pro)
**验收:** Hermes Agent (逐项代码级别验证)
**总成本:** ~$15 API
