# 角色设定
你现在是 UniEmailAgent 项目的首席架构师和高级全栈工程师。我们已经跑通了基础的意图路由和 Agent 爬取流程，现在需要进入 **“系统高可用与工程标准化重构阶段”**。

# 任务目标
请仔细阅读以下 5 个核心优化需求。你需要从后端防御性编程、模块解耦以及前端用户体验三个维度进行代码重构与开发。

# 核心开发需求清单

## 1. 🔴 增量爬取的可靠性保障 (Reliability Guard)
当前增量合并逻辑过于依赖 Agent 自身的 prompt 约束，缺乏程序化兜底。请实现以下机制：
- **前置备份**：在增量任务启动前，自动拷贝当前任务的 CSV 文件至 `outputs/{task_id}/backup_{ts}.csv`。
- **Diff 校验机制**：Agent 声明任务完成后，程序拦截并对比新旧数据，计算“新增行数”和“变更行数”，并在日志中生成 Diff 摘要。
- **自动回滚 (Auto-Rollback)**：如果检测到致命错误（例如：总行数不仅没增加反而减少了，即覆盖事故），系统需自动抛出告警并从 `backup` 文件恢复数据。

## 2. 🟡 Skill 检索精准化与去重 (Smart Context Injection)
随着大学增加，`load_skills_prompt()` 全量加载会导致 Prompt 严重膨胀（超 19KB）。请重构为：
- **按需加载**：实现基于“大学名称”的关键词或正则提取机制，每次只截取并加载 `global_rules` 以及**当前目标大学相关**的 Section，忽略其他大学的经验。
- **智能写入去重**：在执行 `reflect_and_save` 写入新的 `skills.md` 之前，必须对 Agent 总结的新经验与已有经验做相似度校验，防止相同爬取策略被重复写入。

## 3. 🟡 前端意图感知 UI 升级 (Frontend Intent Awareness)
后端 `/api/classify` 已经能返回 `{intent, university, departments}`，请将前端界面与之联动：
- **意图徽章**：在聊天输入框下方或对话气泡旁，展示当前任务的意图标签（如 `🔍 数据分析` / `🕷️ 全新爬取` / `🔄 增量补充`）。
- **非爬取态降级**：如果是简单的“数据分析”意图，前端应自动隐藏“爬取进度条/指示器”。
- **增量态面板**：如果是增量模式，在右侧边栏（或合适位置）临时展示当前任务已有的数据概况（如：已采集 3 学院，共 150 人）。

## 4. 🔵 爬虫脚本标准化 (Crawler Interface Standardization)
目前 `crawlers/` 目录下的 11 个脚本各自为战。请进行重构：
- 定义一个 Python 抽象基类 `BaseCrawler`，统一对外接口：`crawl(target: str) -> list[TeacherRecord]`。
- 制定统一的数据结构（如使用 Pydantic Model 定义 `TeacherRecord`）。
- 挑选 1-2 个现有脚本作为 Demo，将其重构为继承 `BaseCrawler` 的子类。

## 5. 🔵 全局并发任务管理 (Concurrency Control)
防止过多 Agent 同时开启浏览器导致内存或 CPU 耗尽。
- 请在 FastAPI 后端或调度层实现一个全局的并发信号量（Semaphore）或队列机制。
- 限制同时运行的 Playwright/Agent 爬取任务（例如最大并发数为 5）。超过限制的任务需进入等待队列。
