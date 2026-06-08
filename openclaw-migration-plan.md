# UniEmailAgent 执行引擎迁移方案分析

> 目标：在腾讯云 Ubuntu 24.04 服务器上替代 Claude Code CLI，使用 OpenClaw + DeepSeek API 作为爬取执行引擎
> 日期：2026-06-08

---

## 背景：当前执行引擎架构

```
用户请求 → FastAPI WS → Agent.execute()
  ├─ 简单问答 → DeepSeek API 直调 (_respond_conversational)
  └─ 爬取任务 → 外部 CLI 子进程
       ├─ 本机 (Win/Mac): claude -p --output-format stream-json
       └─ 服务器 (Linux): openclaw agent --local --json (已修改的 _run_claude)
```

**关键问题**：
- Claude Code CLI 在 `root` 用户下无法使用 `--permission-mode bypassPermissions`（Anthropic 限制）
- `uniemail` 用户无 Claude Code OAuth 登录
- `openclaw agent --local` 的 agent 模式**仅有对话能力**，无法执行 Bash/Write 工具，不能生成爬虫脚本并执行
- 当前 `claude_agent.py` 的 `_run_claude()` 在 Linux 上已硬编码改为 `openclaw agent --local`，但后续代码仍按 Claude Code 的 `stream-json` 流式解析格式处理 OpenClaw 输出，**两者协议不兼容**

---

## 方案深度分析

---

### 方案 A：后端直接调 DeepSeek API（推荐 ✅）

**核心思路**：不再依赖任何外部 CLI，由后端 Python 进程直接调用 DeepSeek API 完成所有任务。简单问答、生成爬虫脚本、执行脚本、输出检测全由后端控制。

#### 技术细节

```
爬取任务流程：
1. 后端拼接完整 prompt（技能注入 + 数据规范 + 目标大学）
2. 调 DeepSeek API (chat.completions.create) 生成 Python 爬虫脚本
3. 将脚本写入临时文件 /tmp/crawl_{task_id}.py
4. 用 asyncio.create_subprocess_exec 执行 python3 /tmp/crawl_{task_id}.py
5. 实时捕获 stdout/stderr，流式推送到 WebSocket
6. 检测 outputs/{task_id}/ 目录下的新 CSV/XLSX 文件
7. 推送下载链接 + 质量门校验

简单问答流程：
- 直接调 DeepSeek API（已有代码 _respond_conversational，已验证能工作）
- DataMemory 检索已有数据进行回答
```

#### 优点

| 维度 | 评分 | 说明 |
|------|------|------|
| **可控性** | ⭐⭐⭐⭐⭐ | 完全可控，prompt 构建、超时、错误处理、重试策略全部由后端控制 |
| **稳定性** | ⭐⭐⭐⭐⭐ | 无外部 CLI 依赖，避免版本兼容性问题 |
| **延迟** | ⭐⭐⭐⭐ | 毫秒级 API 调用 + 流式输出，无需 CLI 冷启动（约 10s） |
| **安全性** | ⭐⭐⭐⭐⭐ | root 用户无需 su，无 OAuth 问题 |
| **资源占用** | ⭐⭐⭐⭐ | 单一 Python 进程，无需消耗 CLI 子进程内存 |
| **当前代码复用** | ⭐⭐⭐⭐ | `_respond_conversational`（简单问答）和 `main.py` WS handler（prompt 构建）代码可直接复用 |

#### 缺点

| 项目 | 说明 |
|------|------|
| LLM 调用开销 | 每次爬取可能多次调 DeepSeek API（脚本生成 + 可能的重试），增加 API 费用 |
| 脚本生成质量 | DeepSeek 生成的爬虫脚本可能有 bug，需要后端增加重试/修复逻辑 |
| 工具执行循环 | 需要后端实现完整的 Agent 循环（生成→执行→检查→修正），比 CLI 多约 200-300 行代码 |
| Playwright 管理 | 如果脚本直接使用 Playwright，需管理浏览器实例生命周期 |

#### 预计工作量

| 模块 | 工期 | 内容 |
|------|------|------|
| 爬取脚本生成与执行 | 3-4 小时 | 实现 `generate_and_execute_script(prompt) -> AsyncGenerator` |
| 输出文件检测 | 1 小时 | 复用 `_detect_downloads` 逻辑 |
| 错误重试 | 1 小时 | LLM 生成脚本失败时的自动重试 |
| 整合到 WS handler | 1 小时 | 将新执行器接入现有意图路由流程 |
| **总计** | **6-7 小时** | |

---

### 方案 B：让 OpenClaw 代理 Claude Code 的工具能力（不推荐 ❌）

**核心思路**：保持现有 `openclaw agent --local` 调用，改造项目以适应 OpenClaw 的对话式输出，不再依赖 Claude Code 的流式 JSON 协议。

#### 技术细节

```
openclaw agent --local -m "prompt" --json
→ 返回 {"payloads": [{"text": "..."}], "meta": {"finalAssistantVisibleText": "..."}}

改造后的流程：
1. 后端构建完整 prompt → 传给 openclaw agent
2. 解析 JSON 输出，提取 finalAssistantVisibleText
3. 在 OpenClaw 输出中搜索 [FILES] 块、文件路径、脚本代码
4. 如果 prompt 要求生成脚本，由 OpenClaw 输出脚本 → 后端执行
```

#### 缺点（致命）

| 问题 | 严重程度 | 说明 |
|------|----------|------|
| **OpenClaw agent 无工具能力** | 🔴 致命 | `openclaw agent --local` 是对话模式，**不会执行 Bash、Write、Read 等工具**。它只能生成文本回复，无法实际运行脚本或写 CSV 文件 |
| **JSON 输出格式不兼容** | 🔴 严重 | 当前 `_run_claude` 按 Claude Code 的 `stream-json` 协议解析（逐行 JSON，type=assistant/tool_use/tool_result），而 OpenClaw 输出单条 JSON 块，解析逻辑完全无法复用 |
| **代码执行需要额外一层** | 🟡 中等 | 即使 OpenClaw 生成脚本代码，仍需后端截取代码片段自己执行，本质上回到了方案 A 的脚本执行逻辑 |
| **无实时流式输出** | 🟡 中等 | OpenClaw agent 输出单次 JSON 而非流式，前端日志体验差（需要等待完整输出） |
| **资源浪费** | 🔴 中等 | 额外启动 CLI 子进程，增加了约 1.5 秒的 CLI 冷启动时间，且增加了进程管理复杂度 |

#### 能工作的场景

- **简单问答**：OpenClaw agent 可以正常回答，但后端已直接调 DeepSeek API 实现了秒级响应，性能更好
- **生成爬取报告**：可以生成 Markdown/JSON 报告文本，但无法写 CSV/XLSX（无 Write 工具）

#### 预计工作量

| 模块 | 工期 | 说明 |
|------|------|------|
| 修改 `OpenClawAgent.execute()` 解析逻辑 | 1 小时 | 适配 OpenClaw JSON 格式 |
| 实现代码截取与执行 | 3-4 小时 | 从文本中提取 Python 代码 → 执行 |
| 文件检测与推送 | 2 小时 | 检测 outputs/ 新文件 |
| 流式输出适配 | 2 小时 | 将一次 JSON 输出拆成多条推送 |
| **总计** | **8-9 小时** | 且最终效果不如方案 A |

---

### 方案 C：恢复 Claude Code + su 方案（不推荐 ❌）

**核心思路**：创建 `uniemail` 用户，配置 Claude Code OAuth 和 DeepSeek 兼容端点，用 `su - uniemail -c 'claude ...'` 执行。

#### 技术细节

```
# 1. 创建 uniemail 用户
useradd -m -s /bin/bash uniemail
# 2. su 到 uniemail，启动 Claude Code OAuth 登录
su - uniemail
claude
# 首次运行触发浏览器 OAuth → 需要在服务器上完成 OAuth（极困难）
# 3. 配置 DeepSeek 兼容端点
mkdir -p ~uniemail/.claude
cat > ~uniemail/.claude/settings.json << 'EOF'
{
  "model": "deepseek-chat",
  "apiKey": "sk-xxx",
  "baseUrl": "https://api.deepseek.com/v1"
}
EOF
# 4. 后端用 su 执行
su - uniemail -c 'claude -p --output-format stream-json'
```

#### 缺点（致命）

| 问题 | 严重程度 | 说明 |
|------|----------|------|
| **Claude Code OAuth 无法在服务器完成** | 🔴 致命 | Claude Code 首次使用需要浏览器 OAuth 登录，头服务器无图形界面，无法完成登录流程 |
| **DeepSeek API ≠ Claude Code 后端** | 🔴 严重 | Claude Code 的 tool-use 代理架构与 Anthropic API 深度绑定。DeepSeek API 的 `deepseek-chat` 模型输出格式与 Claude 不同，Claude Code 的 tool-use 模式可能需要 Anthropic 特定的响应格式 |
| **安全风险** | 🟡 严重 | `su - uniemail -c` 需要 sudo/root 权限，且 uniemail 用户的 shell 环境存在安全风险 |
| **超时问题** | 🟡 中等 | Claude Code 子进程在服务器上可能因为网络不稳定导致超时 |
| **维护成本** | 🔴 高 | Claude Code 更新频繁，可能需要反复处理版本兼容问题 |

#### 预计工作量

| 模块 | 工期 | 说明 |
|------|------|------|
| 用户创建与配置 | 1 小时 | useradd、.claude/settings.json 配置 |
| OAuth 登录 | **无法完成** | 无图形界面的服务器无法完成 Claude Code OAuth 验证 |
| 后端适配 | 2 小时 | 修改 `_run_claude()` 恢复 su 命令 |
| **总计** | **无法完成** | OAuth 问题是硬障碍 |

---

## 最佳方案选择：方案 A 🏆

### 选择理由

1. **技术可行性** ✅：DeepSeek API 已配置且稳定工作，`_respond_conversational` 已验证 DeepSeek API 直调路径
2. **架构简洁** ✅：去除外部 CLI 依赖，后端单进程闭环，消除进程管理、信号处理、管道缓冲区等复杂问题
3. **现有代码可复用** ✅：
   - `main.py` 的 prompt 构建逻辑（技能注入、范围约束、合并规则）可 100% 复用
   - `playwright_agent.py` 的 PlaywrightAgent 可被脚本直接导入使用，或由后端启动 Playwright 浏览器
   - `exporter.py` 的 CSV/XLSX 导出逻辑可直接调用
4. **成本可控** ✅：DeepSeek API 价格低（deepseek-chat 约 ¥0.5/百万 token），脚本生成一次约 0.5 元
5. **稳定性** ✅：去除 CLI 后减少进程通信的故障点，DeepSeek API 的流式输出已在前端验证可用

### 实施路线图

```
Phase 1 (2h): 核心执行器
  ├─ 实现 ScriptExecutor 类
  │   ├─ generate_script(prompt) → DeepSeek API 生成 Python 爬虫代码
  │   ├─ execute_script(script_path) → subprocess 执行
  │   ├─ stream_output() → 实时捕获 stdout/stderr 推送 WS
  │   └─ detect_output_files() → 检测 outputs/ 新文件
  └─ 单元测试：mock DeepSeek API 测试脚本生成与执行

Phase 2 (2h): 整合到 main.py WS handler
  ├─ 替换 agent.execute() 调用路径
  ├─ DeepSeek API 调用失败时的重试逻辑（降级到 PlaywrightAgent）
  └─ 流式输出适配（逐行推送日志）

Phase 3 (2h): 遗留代码清理
  ├─ 删除 claude_agent.py 中 Claude Code 流式解析逻辑（约 400 行）
  ├─ 简化 OpenClawAgent 为只输出（或删除）
  ├─ 更新 main.py 的 agent 选择策略
  └─ 清理 agent.evaluator.py 中与 Claude Code 相关的追踪代码

Phase 4 (1h): 上线验证
  ├─ 在服务器上运行简单爬取任务
  ├─ 验证增量爬取
  ├─ 验证质量门校验
  └─ 验证数据导出功能
```

### 风险评估

| 风险 | 概率 | 缓解措施 |
|------|------|----------|
| DeepSeek 生成脚本质量不稳定 | 中等 | 增加重试机制（最多 3 次），每次给 LLM 提示上次的错误信息 |
| 长时间爬取 Token 消耗高 | 低 | 设置 max_tokens 上限，脚本生成控制在 2000 tokens 以内 |
| DeepSeek API 不可用 | 低 | 降级到 PlaywrightAgent（内置爬虫，不依赖 LLM） |
| 安全协议变更 | 低 | API 调用代码集中在单个模块，便于更新 |

---

## 总结

| 方案 | 推荐 | 主要理由 |
|------|------|----------|
| **A: 后端直调 DeepSeek API** | ✅ **最佳方案** | 可控、稳定、成本低、现有代码可复用 |
| B: OpenClaw 代理 Claude Code | ❌ 不推荐 | OpenClaw agent 无工具执行能力，无法替代 Claude Code 的核心价值 |
| C: Claude Code + su | ❌ 不可行 | OAuth 登录无法在无图形界面服务器完成，Claude Code 的 tool-use 与 Anthropic 后端深度绑定 |
