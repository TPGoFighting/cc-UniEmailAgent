# UniEmailAgent 用户体验提升方案

## 1. 现状分析

### 1.1 当前问题

| 问题 | 表现 | 根因 |
|------|------|------|
| **技术细节泄漏** | "📋 结果: Exit code 1"、"File created successfully at: ..."、"Hermes Orchestrator 决策..." | `_user_facing_message()` 用脆弱的前缀匹配过滤，遗漏大量模式 |
| **进度消息过于笼统** | "正在分析页面结构"、"执行爬取任务中" | `_progress_pump_llm()` 每 30s 生成一句模糊描述，与真实进展脱节 |
| **无实时数据反馈** | 用户看不到 "已找到 XX 位老师、已提取 YY 个邮箱" | Agent 日志里实际有这些信息，但被当 raw log 处理，未结构化提取 |
| **无可视化进度** | 纯文本聊天流，无步骤指示、无进度条 | 前端仅 Text → ChatArea 渲染，无专用视图组件 |
| **错误信息不友好** | "Exit code 1, SyntaxError: invalid syntax"、"InputValidationError" | 原生错误直接传给前端，无用户友好翻译层 |

### 1.2 现有架构回顾

**后端 WebSocket 消息类型（main.py L1730-1813）：**

| type | 用途 | 当前前端处理 |
|------|------|-------------|
| `log` | Agent 技术日志（工具调用、文件创建、命令结果） | role="log" → chat-area.tsx 隐藏 |
| `text` | Agent 自然语言回复（流式 token） | 实时渲染 |
| `progress` | LLM 每 30s 生成的笼统进度描述 | 显示在聊天区 |
| `done` | 任务完成 | 显示摘要文本 |
| `error` | 错误消息 | 显示原始错误 |
| `download` | 结果文件下载链接 | 显示下载按钮 |
| `file` | 中间脚本创建通知 | 不推送到 WS |

**现有过滤机制 `_user_facing_message()`（main.py L1246-1358）：**
- 用大量 `if msg.startswith(...)` 逐条过滤 → 维护成本高、遗漏多
- 无结构化提取能力（例如 "✅ XX学院：提取到N位教师邮箱" 已包含有用数据但未被解析）

**进度生成 `_progress_pump_llm()`（main.py L1409-1438）：**
- 每 30s 收集最近 20 条日志，调用 LLM 生成一句中文描述
- 回退到本地关键词匹配（效果差、粒度粗）

---

## 2. 设计方案

### 2.1 新增消息类型

在现有 7 种消息类型基础上新增 3 种：

```python
# type="stage"    — 阶段变更通知（结构化）
# type="stats"    — 实时统计（已发现教师数、已提取邮箱数、已处理学院数）
# type="error_user" — 用户友好的错误提示（隐藏技术细节）
```

**各消息格式定义：**

```json
// stage — 阶段变更
{
  "type": "stage",
  "stage": "explore|scrape|verify|export|done",
  "stage_name": "探索学院页面",
  "progress_pct": 15,
  "timestamp": "14:23:05"
}

// stats — 实时统计
{
  "type": "stats",
  "teachers_found": 128,
  "emails_extracted": 96,
  "departments_done": 3,
  "departments_total": 8,
  "timestamp": "14:23:05"
}

// error_user — 用户友好错误
{
  "type": "error_user",
  "message": "访问 XX 学院页面时遇到网络问题，已自动跳过",
  "raw": "HTTP 403 Forbidden from https://...",  // 仅用于日志，不发前端
  "severity": "warning|error",
  "timestamp": "14:23:05"
}
```

### 2.2 新增前端组件

建议创建以下组件（若前端为独立项目，这些组件放在 `frontend/components/` 下）：

```
frontend/components/
├── chat-area.tsx                 # 已有 — 消息列表
├── crawl-progress-panel.tsx      # 新增 — 进度面板（替代纯文本进度）
├── live-stats-counter.tsx        # 新增 — 实时数字统计
├── stage-stepper.tsx             # 新增 — 步骤指示器
├── result-summary-card.tsx       # 新增 — 结构化结果摘要
├── error-alert.tsx               # 新增 — 友好错误提示
└── university-workspace.tsx      # 已有 — 改造后整合上述组件
```

#### 2.2.1 `stage-stepper.tsx` — 步骤指示器

```
┌─────────────────────────────────────┐
│  📋 爬取进度                        │
│                                     │
│  ● ● ● ● ○  4/5 步                 │
│                                     │
│  ✅ 1. 识别目标大学                   │
│  ✅ 2. 探索学院列表                   │
│  🔵 3. 提取教师邮箱 ← 当前步骤       │
│  ⬜ 4. 整理数据                      │
│  ⬜ 5. 生成结果文件                   │
│                                     │
│  ████████░░░░░░░  65%               │
│  已处理 5/8 个学院                    │
└─────────────────────────────────────┘
```

- 5 大阶段固定：识别 → 探索 → 提取 → 整理 → 生成
- 每个阶段可包含子步骤（如提取阶段显示 "正在访问 XX 学院教师列表"）
- 进度条百分比来自 stage 消息的 `progress_pct` 字段

#### 2.2.2 `live-stats-counter.tsx` — 实时数字统计

```
┌─────────────────────────────────────┐
│  📊 实时数据                        │
│                                     │
│    👨‍🏫 教师        📧 邮箱       🏫 学院  │
│     128 位         96 个       3/8    │
│                                      │
│    ┌─────── 最近发现 ───────┐          │
│    │  张伟  →  zhang@xx.edu │          │
│    │  李娜  →  lina@xx.edu  │          │
│    │  王强  →  wang@xx.edu  │          │
│    └────────────────────────┘          │
└─────────────────────────────────────┘
```

- 直接绑定 `type=stats` 消息
- "最近发现" 列表显示最新 3~5 条已提取记录
- 数字渐变动画加分

#### 2.2.3 `crawl-progress-panel.tsx` — 整合面板

合并 stepper + stats + 当前状态文本，替代原有的纯文本进度行：

```
┌─────────────────────────────────────┐
│  📋 南京林业大学 · 爬取进度         │
│                                     │
│  ● ● ● ● ○  4/5                     │
│  ████████████░░  75%                │
│                                     │
│  👨‍🏫 128位教师   📧 96个邮箱   🏫 3/8学院│
│                                     │
│  💬 当前操作：正在访问计算机学院     │
│      教师个人主页...                 │
└─────────────────────────────────────┘
```

#### 2.2.4 `result-summary-card.tsx` — 结构化结果摘要

代替现有的纯文本 "🎉 爬取完成！共N位教师"：

```
┌─────────────────────────────────────┐
│  ✅ 爬取完成！                       │
│                                     │
│  南京林业大学                        │
│  ├─ 教师总数：128 位                 │
│  ├─ 有效邮箱：96 个                 │
│  ├─ 覆盖学院：8/8 个                │
│  └─ 用时：3 分 28 秒                │
│                                     │
│  📊 学院分布                         │
│  计算机学院    ████████████  32 位   │
│  林学院        ████████      22 位   │
│  经管学院      ██████        16 位   │
│  ...                                │
│                                     │
│  📥 下载结果：                       │
│  [📄 CSV] [📊 Excel] [📑 HTML]      │
└─────────────────────────────────────┘
```

#### 2.2.5 `error-alert.tsx` — 友好错误提示

```
┌─ ⚠️  部分学院暂未获取到数据 ──────────┐
│                                       │
│  以下页面暂时无法访问，已自动跳过：      │
│  · 材料科学与工程学院 — 页面返回 404   │
│  · 外国语学院 — 页面加载超时           │
│                                       │
│  ✅ 已成功获取其他 6 个学院的数据       │
│                                       │
│  [重试这些学院]                        │
└───────────────────────────────────────┘
```

- severity=warning 显示黄色，severity=error 显示红色
- 不展示技术细节（HTTP 状态码、SyntaxError 等）
- 提供 "重试" 按钮（选项）

### 2.3 后端修改方案

#### 2.3.1 改造 `_user_facing_message()`（main.py L1246-1358）

**当前问题：** 纯前缀匹配，覆盖不全，维护困难。

**改造方案：** 分两阶段执行：

**阶段 A — 正则结构化解析（优先）：** 尝试从日志中提取结构化数据

```python
def _parse_structured_log(raw_msg: str) -> dict | None:
    """尝试从日志中提取结构化数据，返回 stage/stats 消息。
    
    返回 None 表示无法解析，走传统过滤逻辑。
    """
    # 1. 阶段导航消息 → "📌 第N阶段: ..."
    m = re.match(r'📌 第(\d+)阶段.*?[:：](.*)', raw_msg)
    if m:
        stage_map = {'1': 'explore', '2': 'scrape', '3': 'verify'}
        return {'type': 'stage', 'stage': stage_map.get(m.group(1), 'unknown'),
                'stage_name': m.group(2).strip(), 'progress_pct': int(m.group(1)) * 20}
    
    # 2. 学院完成消息 → "✅ XX学院：提取到N位教师邮箱"
    m = re.search(r'✅\s*(.+?)[：:]\s*提取到\s*(\d+)\s*位', raw_msg)
    if m:
        return {'type': 'stats', 'teachers_found': int(m.group(2)),
                'department': m.group(1).strip()}
    
    # 3. 汇总消息 → "🎉 爬取完成！共N位教师"
    m = re.search(r'🎉.*?共\s*(\d+)\s*位教师', raw_msg)
    if m:
        return {'type': 'stats', 'teachers_found': int(m.group(1)),
                'is_final': True}
    
    return None
```

**阶段 B — 智能过滤（兜底）：** 用关键词/正则代替前缀匹配

```python
TECHNICAL_PATTERNS = [
    r'^🔧\s*调用工具',
    r'^\s{4}参数:',
    r'^\s{4}{',
    r'^📋\s*结果:',
    r'^🧠\s*Hermes\s*Orchestrator:',
    r'^🔄\s*决策循环',
    r'^🎯\s*决策:',
    r'Claude Code',
    r'^claude',
    r'Hermes.*[Oo]rchestrator',
    r'^正在调用',
    r'^参数:',
    r'JSON.*(?:parse|格式|打印|输出)',
    r'执行策略|策略执行',
    r'检索状态',
    r'timeout.*(?:block|command)',
    r'^block=|^command=',
    r'Command running',
    r'tool_use_error',
    r'InputValidationError',
    r'<retrieval_status>',
    r'达到最大步数限制',
    r'File created successfully',
    r'Exit code \d+',
    r'SyntaxError',
    r'Traceback \(most recent call last\)',
    r'playwright_agent\.py',
    r'hermes_agent\.py',
]
```

#### 2.3.2 改造 `_progress_pump_llm()` — 让进度描述与实际进展绑定

**当前问题：** `_progress_pump_llm()` 完全依赖 LLM 猜测进度，与真实数据脱节。

**改造方案：** 在 Agent 执行过程中，由 main.py 的 WS handler 主动推统计信息，LLM 进度描述只作为辅助。

```python
# 新增：从 log_collector 中提取统计信息的函数
def _extract_stats_from_logs(logs: list[str]) -> dict:
    """从日志中提取实时统计信息。"""
    stats = {"teachers_found": 0, "emails_extracted": 0, "departments_done": 0}
    for log in logs:
        m = re.search(r'✅\s*.+?[：:]\s*提取到\s*(\d+)\s*位', log)
        if m:
            stats["teachers_found"] += int(m.group(1))
            stats["departments_done"] += 1
        m = re.search(r'共.*?(\d+)\s*个邮箱', log)
        if m:
            stats["emails_extracted"] = int(m.group(1))
    return stats

# 在 WS handler 循环中（main.py L1730 附近），每处理 5 条 log 推一次 stats
_stats_counter = 0
_logs_since_last_stats = 0
# ...在 for log in agent.execute(...) 循环内：
if msg_type == "log":
    _logs_since_last_stats += 1
    if _logs_since_last_stats >= 5:
        stats = _extract_stats_from_logs(log_collector)
        if stats["teachers_found"] > 0 or stats["departments_done"] > 0:
            await ws.send_text(json.dumps({
                "type": "stats",
                "teachers_found": stats["teachers_found"],
                "emails_extracted": stats["emails_extracted"],
                "departments_done": stats["departments_done"],
                "departments_total": _guess_total_depts(task_id),
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            }, ensure_ascii=False))
        _logs_since_last_stats = 0
```

#### 2.3.3 错误翻译层

在 `error` 消息发送前增加翻译处理：

```python
_USER_FRIENDLY_ERRORS = [
    (r'HTTP \d{3}.*Forbidden.*', '该页面暂时无法访问（权限限制），已自动跳过'),
    (r'HTTP \d{3}.*Not Found', '该页面不存在（404），已自动跳过'),
    (r'timeout', '页面加载超时，已自动跳过'),
    (r'SyntaxError', '数据处理遇到小问题，已自动修复并继续'),
    (r'Exit code \d+', '脚本执行遇到临时问题，已自动跳过'),
    (r'Traceback', '系统运行遇到一个小故障，已自动恢复'),
    (r'ConnectionError|Connection refused', '网络连接暂时不稳定，已自动跳过'),
    (r'Cannot find.*page', '未找到该页面，可能是链接已失效'),
]

def _translate_error(raw_error: str) -> str:
    for pattern, friendly in _USER_FRIENDLY_ERRORS:
        if re.search(pattern, raw_error, re.IGNORECASE):
            return friendly
    return '系统遇到了一个意外问题，已自动继续执行后续任务'
```

#### 2.3.4 完成时推送结构化摘要

在 `_final_summary()` 之后、`type=done` 发送之前，增加结构化数据推送：

```python
# 在 main.py L1876 附近
summary_data = {
    "type": "summary",
    "university": intent_result.university_name,
    "total_teachers": _extract_final_teacher_count(last_agent_line, downloads),
    "total_emails": _extract_final_email_count(task_id),
    "departments_covered": _count_departments(task_id),
    "total_departments": _guess_total_depts(task_id),
    "duration": _compute_duration(task_id),
    "files": [d.get("filename", "") for d in downloads],
    "timestamp": ts,
}
await ws.send_text(json.dumps(summary_data, ensure_ascii=False))
await ws.send_text(json.dumps({"type": "done", "message": summary, "timestamp": ts}, ensure_ascii=False))
```

### 2.4 Agent Prompt 补充指令

需要修改 agent prompt（main.py 中的 skill_injection 或 claude_agent.py 中的 CRAWL_STRATEGY_PROMPT），添加以下指令：

```markdown
## 📊 用户可读输出指令（重要）

你的输出将直接展示给终端用户，请严格遵守：

1. **输出格式要求**
   - 每完成一个学院/系的邮箱提取，以 `✅ XX学院：提取到N位教师邮箱` 开头输出一行
   - 当整体爬取完成时，以 `🎉 全部爬取完成！共N位教师，覆盖M个学院` 结尾
   - 遇到进度变更时（如从"探索学院"进入"提取邮箱"），以 `📌 第N阶段：阶段名称` 开头输出

2. **禁止输出的内容**
   - ❌ 不要输出技术工具名（"Claude Code"、"Hermes"、"Playwright"）
   - ❌ 不要输出文件路径（"/outputs/xxx/..."、"C:\\Users\\..."）
   - ❌ 不要输出文件创建消息（"File created successfully at..."）
   - ❌ 不要输出脚本代码、JSON 片段、命令参数
   - ❌ 不要输出 Exit code、Traceback、SyntaxError 等错误代码

3. **错误处理**
   - 遇到某个学院数据无法获取时，用中文自然语言描述问题，不要堆技术细节
   - 正确：✅ "材料学院页面暂时无法访问，已自动跳过"
   - 错误：❌ "HTTP 404 from https://... | Exit code 1"

4. **自然语言要求**
   - 使用纯中文自然语言回复用户
   - 每个输出步骤前加 emoji 前缀（✅ ❌ 🎉 📌 ⚠️）
   - 每段输出控制在一行内，不超过 80 字
```

### 2.5 前端消息路由改造

在 `chat-area.tsx`（或前端 WS 消息处理器），增加新消息类型的路由：

```typescript
interface WSMessage {
  type: 'log' | 'text' | 'progress' | 'done' | 'error' | 'download'
        | 'stage' | 'stats' | 'error_user' | 'summary';
  message?: string;
  // ...其他字段
}

function handleWSMessage(msg: WSMessage) {
  switch (msg.type) {
    case 'log':
      // 继续隐藏
      break;
    case 'stage':
      // 更新 stage-stepper 组件状态
      stageStepperRef.current.updateStage(msg);
      break;
    case 'stats':
      // 更新 live-stats-counter
      statsCounterRef.current.updateStats(msg);
      break;
    case 'text':
      // 显示在聊天区（已有）
      appendMessage(msg);
      break;
    case 'error_user':
      // 显示友好错误提示
      errorAlertRef.current.show(msg);
      break;
    case 'error':
      // 原始错误 — 还是隐藏，走 error_user 的友好版本
      break;
    case 'summary':
      // 更新 result-summary-card
      summaryCardRef.current.show(msg);
      break;
    case 'done':
      // 显示最终摘要（可能已被 summary 覆盖）
      break;
    case 'download':
      // 显示下载按钮（已有）
      appendDownload(msg);
      break;
    default:
      break;
  }
}
```

---

## 3. 渐进式实施步骤

### Phase 1 — 后端消息结构化（1~2 天）

**目标：** 让后端能结构化提取 stats/stage/error_user 消息，前端不改也能在 chat 中看到改进

```
步骤：
1.1 改造 _user_facing_message() → 添加正则结构化解析（_parse_structured_log）
1.2 替换前缀匹配为 TECHINICAL_PATTERNS 正则列表
1.3 添加 _extract_stats_from_logs() 函数
1.4 在 WS handler 循环中，每 N 条 log 推送一次 type=stats
1.5 添加 _translate_error() 函数，在 type=error 发送前拦截翻译
1.6 添加完成时 type=summary 结构化数据推送
```

**验证：** 在不改前端的情况下，用户在聊天区应能看到：
- 不再出现 Exit code、SyntaxError 等技术文本
- 实时看到 "已发现 XX 位教师" 的统计更新
- 错误提示变为自然语言

### Phase 2 — 前端进度面板（2~3 天）

**目标：** 创建新组件，替换纯文本进度展示

```
步骤：
2.1 创建 stage-stepper.tsx（步骤指示器 + 进度条）
2.2 创建 live-stats-counter.tsx（实时数字统计）
2.3 创建 crawl-progress-panel.tsx（合并面板）
2.4 创建 result-summary-card.tsx（结构化结果）
2.5 创建 error-alert.tsx（友好错误）
2.6 在 university-workspace.tsx 中集成新组件
2.7 添加 WS 消息路由处理
```

**验证：** 用户看到带进度条、数字、步骤指示的完整进度面板

### Phase 3 — Agent Prompt 优化（0.5 天）

**目标：** 从源头减少技术日志产生

```
步骤：
3.1 将 2.4 节 Prompt 指令注入到 skill_injection（main.py L1698）
3.2 同时注入 claude_agent.py 中 CRAWL_STRATEGY_PROMPT
3.3 确保 Claude Code / Hermes Agent 输出的 text 消息符合用户友好格式
```

**验证：** Agent 输出的 text 消息不再包含技术工具名、文件路径、命令参数

### Phase 4 — 打磨与收尾（1 天）

```
步骤：
4.1 处理边界情况（任务中断重连时恢复进度面板状态）
4.2 性能优化（stats 推送频率控制，避免 WS 拥塞）
4.3 降级方案（后端无 stats/stage 推送时，前端回退纯文本模式）
4.4 单元测试
4.5 用户验收测试
```

---

## 4. 关键技术决策

### 4.1 为什么 stats 不在 Agent 内生成，而由后端从日志提取？

- **解耦**：Agent 不需要知道前端展示需求
- **灵活性**：即使 Agent 输出的格式有细微变化，后端解析可以独立适配
- **低侵入**：不改动 Agent 核心逻辑，只在 WS handler 中添加提取逻辑

### 4.2 为什么保留 `_progress_pump_llm()` 但不依赖它？

- LLM 生成的进度描述质量不稳定、延迟高（30s）
- 改为 stats 结构化数据 + stage 导航为主，LLM 描述为辅
- 仅在无 stats/stage 推送时回退 LLM 描述，保证降级体验

### 4.3 错误为什么要分 error 和 error_user 两种类型？

- `error` 保留给后端日志记录（需要 debug 时查看原始错误）
- `error_user` 只推送给前端展示（经过翻译、脱敏）
- 前端只处理 `error_user`，忽略 `error`

---

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| Agent 日志格式变化导致正则解析失效 | 所有正则解析加 try/except，失败时回退旧逻辑 |
| stats 推送频率过高导致 WS 拥塞 | 限制每 5 条 log 最多推 1 次，且至少间隔 2s |
| 前端新组件导致页面性能下降 | 组件按需渲染（WebSocket 消息驱动），非轮询 |
| 旧前端（无新组件）不兼容新消息类型 | 所有新消息类型推送到 WS 但不破坏旧消息格式，旧前端忽略未知 type |
| 正则过滤遗漏技术日志 | 新增 _PARSE_FAILED_LOG 记录未匹配日志，供定期 review 补充规则 |
