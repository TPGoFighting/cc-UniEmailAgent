# Hermes 替换 Claude Code 迁移计划

## 目标
服务器上用 `hermes` CLI 替代 `claude` CLI 作为 UniEmailAgent 的 Agent 执行引擎。

## 架构对比

### 本机（Claude Code）
```
Backend → agent.execute()
  → ClaudeAgent._run_claude()
    → claude -p --print --output-format stream-json
      --permission-mode bypassPermissions
      --allowedTools ["Read","Edit","Write","Bash"]
```

### 服务器（Hermes）
```
Backend → agent.execute()
  → HermesAgent._run_hermes()
    → hermes chat -q "prompt" --yolo
      -m deepseek/deepseek-v4-flash
```

## 关键差异

| 项目 | Claude Code | Hermes |
|------|------------|--------|
| CLI 命令 | `claude -p "prompt"` | `hermes chat -q "prompt"` |
| 输出格式 | `stream-json`（逐行 JSON） | TUI 文本（需适配） |
| 权限绕过 | `--permission-mode bypassPermissions` | `--yolo` |
| 工具白名单 | `--allowedTools` | 通过 `--toolsets` |
| 模型 | claude-sonnet-4 | `deepseek-v4-flash` |
| 输出捕获 | stdout 逐行 JSON | stdout 文本，可用 `--json` 或 `--output-format json` |

## 实施步骤

### Step 1: 配置 Hermes DeepSeek provider（我来做）
- 运行 `hermes model` 交互式选择 DeepSeek 作为 provider
- 配置 deepseek-v4-flash 为默认模型
- 验证 `hermes chat -q "test" --yolo` 正常工作

### Step 2: 创建 HermesAgent 类（Claude Code 实现）
- 新建 `backend/agent/hermes_agent.py`
- 参考 `claude_agent.py` 的架构，但改用 `hermes` CLI
- 支持：非交互模式、stdout 捕获、工具调用解析、文件检测
- 超时：600s，步数限制：10000

### Step 3: 更新 main.py 路由（我来做）
- Agent 选择策略：Hermes > GraphAgent > OpenClaw > Claude

### Step 4: 前端适配（如有需要）
- 流式输出适配 Hermes 的输出格式

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/agent/hermes_agent.py` | 新建 | HermesAgent 类，~150 行 |
| `backend/main.py` | 修改 | agent 路由增加 Hermes 优先 |
| `backend/agent/openclaw_agent.py` | 删除或降级 | 不再需要 |

## 工作量估算
- Step 1: 15 分钟（Hermes 交互式配置）
- Step 2: 2-3 小时（Claude Code 实现）
- Step 3: 15 分钟
- **总计: ~3 小时**
