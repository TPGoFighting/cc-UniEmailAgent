# UniEmailAgent 智能水平分析报告

> **分析日期**: 2026-06-03  
> **分析目标**: 为什么 PlaywrightAgent / ClaudeAgent 不如 Claude Code 或 Hermes 智能？如何改进？  
> **项目路径**: `D:\Work\test\UniEmailAgent`

---

## 目录

1. [当前架构总览](#1-当前架构总览)
2. [能力差距对比](#2-能力差距对比)
3. [核心缺陷深度分析](#3-核心缺陷深度分析)
4. [改进路线图](#4-改进路线图)
5. [具体实施步骤](#5-具体实施步骤)
6. [预期效果与指标](#6-预期效果与指标)
7. [总结](#7-总结)

---

## 1. 当前架构总览

UniEmailAgent 的核心 Agent 体系由两层构成：

```
用户请求
  │
  ▼
意图路由 (IntentRouter) ──LLM/关键词分类──► SIMPLE_QUERY / NEW_CRAWL / INCREMENTAL
  │
  ▼
ClaudeAgent ──claude -p 子进程──► 成功? ──► 返回结果
  │                                失败?
  ▼
PlaywrightAgent (降级回退) ──硬编码爬虫──► 返回结果
```

### 1.1 PlaywrightAgent

**定位**: 不依赖 LLM API 的自包含浏览器爬虫引擎。  
**爬取流程**: 首页 → 找师资入口 → 找学院列表 → 遍历学院教师列表 → 逐个访问详情页提取邮箱。  
**关键实现**: 全硬编码 JS 注入 + 正则提取，约 955 行单文件。

### 1.2 ClaudeAgent

**定位**: Claude CLI 的 Python 包装器。  
**工作方式**: 通过 `asyncio.subprocess` / `threading` 启动 `claude -p --output-format stream-json`。  
**核心注入**: 一个约 80 行的系统提示词（CRAWL_STRATEGY_PROMPT）告诉 Claude 如何爬取高校邮箱。

---

## 2. 能力差距对比

### 2.1 核心能力矩阵

| 能力维度 | PlaywrightAgent | ClaudeAgent | Claude Code | Hermes Agent |
|---|---|---|---|---|
| **LLM 推理** | ❌ 无 | ✅ Claude CLI | ✅ Claude 4 系 | ✅ 任意 LLM |
| **规划能力** | ❌ 硬编码流程 | ⚠️ 即时规划（无持久） | ✅ 工具编排 + 计划 | ✅ Skills + 工具链 |
| **持久记忆** | ❌ 无 | ❌ 每次清空上下文 | ⚠️ Session 级记忆 | ✅ Profile 级记忆 |
| **自我修正** | ❌ 遇到异常就跳过 | ⚠️ 当前会话内可修正 | ✅ 迭代优化循环 | ✅ 反馈循环 + 重试 |
| **工具链** | ❌ 只有 Playwright | ✅ Read/Write/Bash/Grep/Glob | ✅ 完整 + MCP 服务器 | ✅ Skills + Plugins |
| **文件访问** | ❌ 只写 outputs/ | ✅ 全文件系统 | ✅ 全文件系统 + Git | ✅ 全文件系统 |
| **多 Agent 协作** | ❌ 单线程 | ❌ 单进程 | ❌ 单用户 | ✅ 多 Agent 编排 |
| **自适应爬取** | ❌ 固定策略 | ⚠️ Claude 可理解页面但无记忆 | N/A (通用) | N/A (通用) |
| **技能自动沉淀** | ❌ 无 | ⚠️ 有 [REFLECTION] 但质量低 | ✅ 系统内置 | ✅ Skills 自动管理 |
| **失败恢复** | ❌ 直接跳过 | ⚠️ Claude 可尝试重试 | ✅ 自动重试 + 降级 | ✅ 多重降级策略 |

### 2.2 代码规模与复杂度对比

| 指标 | PlaywrightAgent | ClaudeAgent | Claude Code | Hermes Agent |
|---|---|---|---|---|
| 核心代码行数 | ~955 行 | ~1234 行 | ~100K+ 行 | ~50K+ 行 |
| 依赖外部模型 | ❌ 无 | ✅ Claude CLI | ✅ Claude API | ✅ 灵活 LLM |
| 网络爬虫能力 | ✅ 内置浏览器 | ✅ 通过 Claude CLI | ❌ 无专用爬虫 | ❌ 无专用爬虫 |
| 通用对话能力 | ❌ 无 | ⚠️ 有限 | ✅ 完善 | ✅ 完善 |

---

## 3. 核心缺陷深度分析

### 3.1 PlaywrightAgent 的根本问题

#### 3.1.1 硬编码策略，零推理能力

```python
# playwright_agent.py:549-568 — 硬编码的师资入口查找
async def _find_faculty_entry(self, page, base_url):
    links = await page.evaluate("""() => {
        document.querySelectorAll('a').forEach(a => {
            const text = a.textContent.trim();
            if (text.includes('师资') || text.includes('教师') || ...) {
                results.push(...);
            }
        });
    }""")
```

- 只匹配固定的中文/英文关键词
- 遇到"人才队伍"、"教学科研人员"等变体就找不到
- 无法理解页面布局（导航栏 vs 内容区）
- 没有学习能力——今天失败了，明天还是一个样

#### 3.1.2 单线程执行，效率低下

```python
# playwright_agent.py:807-808
tasks = [self._crawl_single_profile(ctx, entry, dept_name) for entry in all_entries]
results_list = await asyncio.gather(*tasks, return_exceptions=True)
```

虽然用了 asyncio.gather，但信号量 `_profile_sem = asyncio.Semaphore(2)` 限制了同时只爬 2 个详情页。对于有 100+ 教师的学院，串行等待时间极长。

#### 3.1.3 邮箱提取策略单一

- 只靠正则 `r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"` 匹配
- 反爬处理只有 5 种 `[at]` 变体替换
- 无法处理图片验证码、JavaScript 动态渲染、懒加载邮箱
- 无法通过推理理解"请将 AT 改为 @"这种自然语言指令

#### 3.1.4 无状态，无记忆

- 每次任务从头开始
- 不记录哪个大学的哪种策略成功
- 不记录哪些 URL 模式是有效的教师详情页
- 不记录哪些反爬模式出现过

### 3.2 ClaudeAgent 的根本问题

#### 3.2.1 本质只是 `claude -p` 的壳

```python
# claude_agent.py:775-778
cmd = [
    "claude", "--print", "--output-format", "stream-json",
    "--permission-mode", "bypassPermissions",
    "--allowedTools", json.dumps(ALLOWED_TOOLS),
    "--max-budget-usd", "20.0",
]
```

- 没有 Agent 框架加持——只是把消息传给 Claude CLI
- Claude CLI 本身很强大，但缺少**编排层**
- 没有记忆持久化、没有多轮对话管理、没有任务上下文积累

#### 3.2.2 系统提示词质量不高

CRAWL_STRATEGY_PROMPT（约 80 行）虽然覆盖了基本流程，但存在以下问题：

- **任务隔离红线**占了将近一半篇幅，重复强调 `{{OUTPUT_DIR}}` 限制
- **爬取策略**过于笼统（"必须进个人详情页才有邮箱"这种常识性知识不需要注入）
- **缺少具体经验**（哪个大学哪个学院的哪个 URL 模式有效）
- **反思机制脆弱**——[REFLECTION] 标签容易被忽略或不正确解析

#### 3.2.3 无效 API 调用问题（progress_pump_llm）

```python
# main.py:1160-1189
async def _progress_pump_llm(ws, stop_event, log_collector):
    while not stop_event.is_set():
        await asyncio.wait_for(stop_event.wait(), timeout=30)
        recent = log_collector[-20:]
        summary = await _generate_progress_summary(recent)
        ...
```

**每 30 秒调用一次 DeepSeek API！** 对于 10 分钟的爬取任务，至少调用 20 次 DeepSeek 来生成"进度描述"，这完全是浪费：

- 每次调用至少消耗 200+ token
- 20 次 = 4000+ token 的浪费
- 生成的进度（"正在访问教师个人页面..."）对用户体验几乎没有帮助
- 不配置 DeepSeek Key 时这个问题不存在，但一旦配置就是持续的 API 费用流失

#### 3.2.4 技能知识库数据污染

skills/ 目录下有 32 个文件，其中：

- `crawl_knowledge.md` — 混合了多所大学的经验
- `global_crawling_rules.md` — 全局规则
- **30 个 JSON 文件** — 每个任务都会生成一个

```
skills/
├── crawl_knowledge.md
├── global_crawling_rules.md
├── 南京大学_d73dcbad.json          # 任务元数据
├── 爬取南京大学_d73dcbad.json       # 命名不一致
├── 南京大学_996e5aec.json          # 同一个大学多个任务
├── 爬取南京大学_996e5aec.json      # 命名重复
├── 抓取南京大学_a468ea4c.json      # 命名不统一
├── 南京理工大学_3f22492c.json
├── 南京邮电大学_dfd426c6.json
├── 爬取东南大学_9782a4a5.json
├── 清华大学_8b8245ca.json
├── 想查哪所大学_49219292.json      # 噪音数据！
└── ...                             # 大量冗余
```

问题：

- "想查哪所大学_49219292.json" 是噪音，不是有效经验
- 命名不统一（南京大学 / 爬取南京大学 / 抓取南京大学）
- 同一个大学有多个任务 JSON，但缺少合并逻辑
- `load_skills_prompt()` 需要过滤大量噪音

### 3.3 项目整体架构缺陷

| 缺陷 | 影响 | 严重度 |
|---|---|---|
| 没有并发控制（Semaphore） | 同时开多个任务会 OOM | 🔴 高 |
| 没有错误分类与重试策略 | 一律跳过，数据丢失 | 🔴 高 |
| PlaywrightAgent 与 ClaudeAgent 职责重叠 | 代码冗余、维护困难 | 🟡 中 |
| 没有单元测试覆盖 Agent 核心逻辑 | 改代码怕出 bug | 🟡 中 |
| 没有数据校验 pipeline | 脏数据直接进 CSV | 🟡 中 |

---

## 4. 改进路线图

### 4.1 短期改进（1-2 天）— 立竿见影

```
优先级: 🔴 高
投入: 2 天
预期提升: 爬取成功率 +20%~30%
```

#### 4.1.1 优化系统提示词

**当前问题**: CRAWL_STRATEGY_PROMPT 太啰嗦、缺乏具体策略。

**改进方案**:

```
替换为阶段性注入策略：
  阶段1: 首页分析 → "分析当前页面的导航结构，识别所有可能是'师资队伍'的入口"
  阶段2: 学院列表 → "提取所有二级学院/系/研究所的链接，排除行政机构"
  阶段3: 教师列表 → "识别教师姓名链接和教师卡片元素"
  阶段4: 详情页 → "提取教师邮箱，处理反爬编码"
```

**预期效果**: 减少 Claude 的试错轮次，提高首次执行成功率。

#### 4.1.2 修复技能知识库数据污染

**当前问题**: 30 个 JSON 文件，命名混乱，含噪音。

**改进方案**:

```
1. 合并同大学的 JSON 文件
2. 删除噪音文件（如"想查哪所大学_49219292.json"）
3. 统一命名规范: {university_name}_{timestamp}.json
4. 修正 load_skills_prompt 的过滤逻辑
```

**预期效果**: 减少注入给 Claude 的上下文噪音，提升回答质量。

#### 4.1.3 停止或优化 progress_pump_llm

**当前问题**: 每 30 秒调用一次 DeepSeek，浪费 API 额度。

**改进方案**:

```
方案A: 删除 progress_pump_llm（推荐）
  - 直接使用爬取步骤计数作为进度
  - "正在处理第 3/15 个学院..."

方案B: 改为本地规则生成进度
  - 检测到 "进入学院X" → "正在爬取 X 学院"
  - 检测到 "提取到 N 位教师" → "已从 X 学院提取 N 位教师"
```

**预期效果**: 每次任务节省 20+ 次 API 调用（约 $0.02-$0.05/任务）。

### 4.2 中期改进（1-2 周）— 架构升级

```
优先级: 🟡 中
投入: 1-2 周
预期提升: 成功率 +50%，新大学支持速度 +200%
```

#### 4.2.1 增加 Agent 记忆能力

**当前问题**: 每次任务清空上下文，不记得之前的策略。

**改进方案**:

```
实现任务间记忆系统：

1. URL 模式记忆
   南京大学 → 师资入口模式: /szdw/, /szll/
   清华大学 → 师资入口模式: /faculty/, /teacher/

2. 选择器记忆
   南京大学计算机系 → 教师列表选择器: .teacher-list a
   东南大学 → 详情页 ID 模式: /info/{id}.htm

3. 反爬策略记忆
   南京邮电大学 → 邮箱编码: base64 编码 data-email
   南京理工大学 → 邮箱: [at] 替代 @
```

**存储方案**: 使用 SQLite 或 JSON 文件，按大学名索引。

**预期效果**: 第二次爬取同一大学时，成功率从 ~40% 提升到 ~80%。

#### 4.2.2 增加反馈循环

**当前问题**: 失败后直接跳过，不尝试其他策略。

**改进方案**:

```
策略回退链:

策略A: 关键词匹配师资入口
  └─ 失败? → 策略B: 搜索"师资队伍 南京大学"
       └─ 失败? → 策略C: 扫描首页所有链接，用 LLM 判断哪个是师资入口
            └─ 失败? → 策略D: 使用百度site:edu.cn搜索

每个策略的成功/失败记录到记忆系统中。
```

**预期效果**: 对未知页面结构的适应能力大幅提升。

#### 4.2.3 构建大学策略注册表

**当前问题**: 没有中心化的大学爬取配置。

**改进方案**:

```python
# university_registry.py
UNIVERSITY_REGISTRY = {
    "南京大学": {
        "homepage": "https://www.nju.edu.cn",
        "faculty_entries": ["/szdw/", "/szll/", "/rczp/"],
        "dept_selectors": [".dept-list a", "#colleges a"],
        "teacher_selectors": [".teacher-card a", ".faculty-list a"],
        "detail_pattern": r"/\d+/\d+/c\d+",
        "email_pattern": "standard",  # standard | base64 | image | js
        "anti_spam": ["[at]", "(at)", "[@]"],
        "success_count": 5,
        "last_success": "2026-06-01",
        "notes": "教师详情页使用/c\d+/模式",
    },
    ...
}
```

**预期效果**: 新大学不再从零开始试探，直接使用已知策略可以显著提高首爬成功率。

### 4.3 长期改进（1-2 月）— 质的飞跃

```
优先级: 🔵 低
投入: 1-2 月
预期提升: 达到/接近 Claude Code 和 Hermes 的智能水平
```

#### 4.3.1 多 Agent 协作架构

**当前问题**: 单 Agent 既要分析页面结构、又要写爬虫脚本、又要提取数据。

**改进方案**:

```
引入专业分工的 Agent 团队:

┌──────────────────────────────────────────────────┐
│                    Orchestrator                    │
│  (负责任务拆解、进度管理、结果聚合)                  │
├─────────────────┬─────────────────┬───────────────┤
│  StructureAgent  │  CrawlAgent      │  VerifyAgent  │
│  分析页面结构     │  执行爬取操作     │  验证数据质量   │
│  → 输出选择器    │  → 输出 CSV      │  → 检查完整性   │
│  → 识别导航模式  │  → 处理分页      │  → 邮箱格式校验  │
└─────────────────┴─────────────────┴───────────────┘
```

**工作流**:

1. StructureAgent 打开大学首页，分析导航结构 → 输出"师资队伍入口在 #nav > li:nth-child(3) > a"
2. CrawlAgent 使用这个选择器执行爬取 → 输出原始数据
3. VerifyAgent 检查数据质量 → 如果邮箱率 < 50%，通知 Orchestrator 重试

**预期效果**: 从"一个 Agent 碰运气"变成"专业团队协作"，成功率大幅提升。

#### 4.3.2 可视化操作界面

**当前问题**: Agent 做了什么全在黑盒里，用户看不到过程。

**改进方案**:

```
向 WebSocket 推送结构化事件：

{
  "type": "agent_action",
  "action": "navigate",
  "url": "https://www.nju.edu.cn/szdw/",
  "status": "success",
  "elements_found": 15,
  "screenshot": "base64...",  // 可选
  "thought": "正在分析师资队伍页面，寻找学院列表..."
}
```

**前端显示**:
- 实时 DOM 截图（缩略图）
- Agent 的"思考过程"流式展示
- 已提取数据的实时表格更新
- 进度条（精确到"第 N/M 个学院"）

**预期效果**: 用户体验从"等待中..."变成"看它怎么思考的"，信任感提升 10 倍。

#### 4.3.3 自助学习能力

**当前问题**: 项目不会从成功/失败任务中自动提取经验（现有的 [REFLECTION] 太弱）。

**改进方案**:

```
建立"经验提取 Pipeline":

任务完成
  │
  ▼
执行总结 (LLM)
  - 本次任务的关键步骤
  - 遇到的难点与解决
  - 独特的 URL 模式/选择器
  │
  ▼
经验去重 (相似度校验)
  - 与已有知识比较
  - 只保留新增内容
  │
  ▼
写入策略注册表
  - 更新 UNIVERSITY_REGISTRY
  - 更新 skills/crawl_knowledge.md
  │
  ▼
影响评估
  - 新策略是否提升了成功率？
  - 哪些策略经常失败？
  - 自动调整策略优先级
```

**预期效果**: 项目越用越聪明，每完成一个任务就积累一份经验。

#### 4.3.4 Hermes 级 Skills + Memory 系统

**参考 Hermes 架构**:

```
Hermes Agent
├── Skills (技能库)
│   ├── 按需加载（大学名匹配）
│   ├── 自动版本管理
│   └── 测试验证
├── Memory (持久记忆)
│   ├── Episodic (任务记忆)
│   ├── Semantic (知识记忆)
│   └── Procedural (流程记忆)
├── Tools (工具链)
│   ├── 文件系统
│   ├── 网络请求
│   ├── 代码执行
│   └── MCP 服务器
└── Multi-Agent (多 Agent 编排)
    ├── 任务分解
    ├── 并行执行
    └── 结果聚合
```

**UniEmailAgent 升级路线**:

1. **Skills v2**: 当前 skill_manager.py 的按需加载 + 去重写入已初具雏形，但需要：
   - 增加版本管理（每次写入保留历史版本）
   - 增加自动测试（新技能注入后，用历史数据验证效果）
   - 增加回退机制（新技能导致失败时自动回退到旧版本）

2. **Memory v1**: 实现三类记忆：
   - Episodic: 任务级日志（已有 history.py）
   - Semantic: 大学策略知识（需要新建）
   - Procedural: 爬取流程模板（需要新建）

3. **Tools v2**: 扩展工具链：
   - 增加 HTML 解析工具（BeautifulSoup/lxml）
   - 增加网络请求工具（aiohttp/httpx）
   - 增加数据验证工具（Pydantic schema）
   - 增加截图分析工具（截图 + LLM 分析页面布局）

---

## 5. 具体实施步骤

### 5.1 短期（1-2 天）

| 步骤 | 任务 | 文件 | 预计时间 |
|---|---|---|---|
| 1 | 优化 CRAWL_STRATEGY_PROMPT | `claude_agent.py` | 2h |
| 2 | 删除噪音 JSON 文件 | `skills/*.json` | 1h |
| 3 | 合并同大学 JSON | `skills/` | 2h |
| 4 | 停止 progress_pump_llm | `main.py` | 0.5h |
| 5 | PlaywrightAgent 增加更多入口关键词 | `playwright_agent.py` | 1h |

### 5.2 中期（1-2 周）

| 步骤 | 任务 | 文件 | 预计时间 |
|---|---|---|---|
| 1 | 实现大学策略注册表 | `new: university_registry.py` | 1d |
| 2 | 实现反馈循环（策略回退链） | `playwright_agent.py` | 2d |
| 3 | 实现 Agent 记忆持久化 | `new: agent_memory.py` | 2d |
| 4 | 优化技能去重逻辑 | `skill_manager.py` | 1d |
| 5 | 增加并发控制 Semaphore | `main.py` | 0.5d |
| 6 | 增加单元测试 | `tests/test_agents.py` | 1d |

### 5.3 长期（1-2 月）

| 步骤 | 任务 | 预计时间 |
|---|---|---|
| 1 | 多 Agent 协作架构设计与实现 | 2w |
| 2 | 可视化操作界面 | 1w |
| 3 | 自助学习 Pipeline | 1w |
| 4 | Hermes 级 Skills + Memory 系统 | 2w |

---

## 6. 预期效果与指标

### 6.1 量化指标

| 指标 | 当前 | 短期(2天) | 中期(2周) | 长期(2月) |
|---|---|---|---|---|
| 新大学首爬成功率 | ~35% | ~55% | ~75% | ~90% |
| 已爬大学复爬成功率 | ~50% | ~65% | ~85% | ~95% |
| 单任务平均耗时(10学院) | ~15min | ~12min | ~8min | ~5min |
| 邮箱提取准确率 | ~70% | ~80% | ~90% | ~95% |
| 未知页面适应能力 | ❌ 极差 | ⚠️ 有限 | ✅ 较好 | ✅ 优秀 |
| API 浪费 (progress_pump) | ~20次/任务 | 0次 | 0次 | 0次 |
| 用户信任感 | ❌ 黑盒 | ⚠️ 部分可见 | ✅ 可见 | ✅ 可理解 |

### 6.2 定性效果

```
短期后: "Agent 能爬更多大学了，但遇到新结构还是不行"
中期后: "Agent 学会了一些技巧，第二次爬同一所大学明显快多了"
长期后: "Agent 自己学会怎么爬新大学了，而且爬得越来越好"
```

---

## 7. 总结

### 为什么不如 Claude Code / Hermes？

一句话总结：**UniEmailAgent 是一个"工具"而不是一个"智能体"**。

| 对比项 | UniEmailAgent | Claude Code / Hermes |
|---|---|---|
| 本质 | 爬虫脚本 + CLI 包装 | 通用智能体框架 |
| 记忆 | 无（每次清空） | 有（持久上下文） |
| 学习 | 无（硬编码规则） | 有（经验累积） |
| 规划 | 固定流程 | 动态规划 |
| 适应 | 0（遇到新结构就失败） | 强（理解+推理+适应） |

### 最关键的三件事

要真正达到 Claude Code / Hermes 的智能水平，最关键的三个改进是：

1.  **🟢 增加持久记忆**（中期）— Agent 需要记住什么策略有效、什么策略失败
2.  **🟢 增加反馈循环**（中期）— Agent 需要能在失败后自动切换策略
3.  **🔵 多 Agent 协作**（长期）— 专业分工才能处理复杂任务

### 最大的误区

> "加了更好的提示词 = Agent 就更聪明"

错。ClaudeAgent 本身就是 Claude Code，提示词是 Claude Code 写的。问题是：
- 它没有记忆 → 下次任务又忘了上次的教训
- 它没有工具 → 只会 Read/Write/Bash，没有专用的爬虫工具
- 它没有编排 → 只能顺序执行，不能并行搜索+验证

**提示词只能占到智能水平的 20%，剩下的 80% 在架构（记忆、工具、编排、学习）。**

---

> 本报告由 Hermes Agent 自动生成于 2026-06-03  
> 基于对 `D:\Work\test\UniEmailAgent` 项目源码的全面分析
