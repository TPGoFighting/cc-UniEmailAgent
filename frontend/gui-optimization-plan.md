# GUI 优化方案报告

基于 Open WebUI 的设计启示，结合 UniEmailAgent 前端现有架构（Next.js 16 + shadcn/ui v4 + Zustand + TailwindCSS 4），规划以下优化项。

---

## P0 — 核心体验（必须做）

### 0-1 流式消息闪烁光标

**描述**：Agent 消息流式输出时，在文本末尾显示一个闪烁的光标，直观表明"正在输出中"。流结束后光标自动消失。

**实现思路**：
- `chat-message.tsx`：在 `role === "text" | "agent"` 且 `message.isStreaming === true` 时，于 ReactMarkdown 内容末尾附加一个 `<span className="inline-block w-[2px] h-[1em] bg-primary animate-cursor-blink ml-0.5 align-middle" />`
- `globals.css`：新增 `@keyframes cursor-blink`（0%/100% opacity:1, 50% opacity:0）
- 替换现有的 `TypingIndicator`（三点弹跳动画），改为更紧凑的闪烁光标；流结束时，`isStreaming` 切换为 `false`，光标自然消失

**涉及文件**：`components/chat-message.tsx`、`app/globals.css`

**预期效果**：用户能清晰感知"Agent 正在说话"而不是静态等待，且不再看到段落级别切换时的 placeholder 闪烁。

---

### 0-2 代码块复制按钮

**描述**：ShikiHighlight 渲染的代码块右上角缺少"一键复制"按钮，用户需要手动选中复制，体验不佳。

**实现思路**：
- `shiki-highlight.tsx`：在外层容器上添加 `group` 类，然后用绝对定位在右上角放置复制按钮
- 复制按钮 hover 时出现（`opacity-0 group-hover:opacity-100`），点击后调用 `navigator.clipboard.writeText(code)`，短暂显示 ✓ 反馈（2s 后复原）
- 用 shadcn/ui 的 `Button` 或自定义小按钮，尺寸 `h-7 w-7`

**涉及文件**：`components/shiki-highlight.tsx`

**预期效果**：一键复制代码，反馈明确，与 GitHub/Open WebUI 行为一致。

---

### 0-3 Zustand persist 中间件

**描述**：当前三个 Zustand store（chat、task、ui）均未使用 `persist` 中间件，刷新页面后所有状态丢失（仅 `task-store` 手动将 `activeTaskId` 写入 `localStorage`）。历史消息需等 API 重新加载，UI 状态（侧边栏、搜索词等）完全丢失。

**实现思路**：
- `stores/chat-store.ts`：对 `taskMessages`、`runningTaskIds`、`summaryMap` 等关键状态接入 `persist`；
  1. 导入 `persist` from `zustand/middleware`
  2. 用 `create<ChatStore>()(persist((set, get) => ({...})), { name: "uniemail-chat", partialize: (state) => ({ taskMessages: state.taskMessages, summaryMap: state.summaryMap }) })`
  3. 避免持久化 `currentMessages`（始终从 `taskMessages` 派生）和 `undoQueue`
- `stores/ui-store.ts`：持久化 `sidebarOpen`、`searchQuery`（如果用户半途刷新，恢复搜索状态）
- `stores/task-store.ts`：替换手动的 `localStorage` 写入，改用 `persist`，持久化 `tasks` 和 `activeTaskId`

**涉及文件**：`stores/chat-store.ts`、`stores/ui-store.ts`、`stores/task-store.ts`

**预期效果**：页面刷新后对话列表、当前任务、UI 状态完全恢复，消除"刷新就丢失上下文"的问题。

---

### 0-4 右键上下文菜单

**描述**：消息气泡上缺少右键菜单（复制/编辑/删除/重试等），用户习惯于右键触发操作。

**实现思路**：
- 新建 `components/context-menu-message.tsx`，基于 shadcn/ui 的 `ContextMenu` 组件（需先 `npx shadcn@latest add -d context-menu`，如果 base-nova 支持的话）
- 包裹 `ChatMessage` 渲染内容，提供：
  - 用户消息：复制、编辑、删除
  - Agent 消息：复制、重试、删除
- 对应操作复用 `useAgentChat` 的 `copyMessage` / `editMessage` / `deleteMessage` / `regenerate`

**涉及文件**：`components/chat-message.tsx`（包裹 ContextMenu）、`components/context-menu-message.tsx`（新建）

**预期效果**：右键触达所有消息操作，效率提升。

---

## P1 — 体验增强（应该做）

### 1-1 对话模糊搜索（fuse.js）

**描述**：当前搜索仅按任务标题做 `includes()` 全字匹配，不支持模糊搜索、拼音纠错、消息内容搜索。

**实现思路**：
- 安装 `fuse.js`
- `components/search-bar.tsx`：将搜索逻辑改为 fuse.js 实例搜索，索引字段包括 `title` 和（可选）消息内容
- 在 `sidebar.tsx` 中，当前 `filteredTasks` 的搜索过滤逻辑替换为 fuse 搜索结果
- 搜索词高亮：为匹配到的字符添加 `<mark>` 标记（fuse 返回的 `matches` 提供了索引位置）

**涉及文件**：`components/search-bar.tsx`、`components/sidebar.tsx`、`package.json`

**预期效果**：拼写错误、部分匹配、内容搜索均能找到任务，搜索体验接近 Open WebUI。

---

### 1-2 流式消息渲染时稳定容器

**描述**：消息流式输出时，ReactMarkdown 逐步解析内容，有时会导致容器高度抖动或 content flash。

**实现思路**：
- `chat-message.tsx`：在 `role === "agent" | "text"` 且 `isStreaming` 时，给外层容器添加 `min-h-[2em]` 和 `transition: min-height 0.15s ease`，防止内容频繁溢出
- 内容区域的 `prose` 类加上 `min-w-0`（已有）和 `break-words`
- 在 content 为空时不渲染空白气泡，直接显示闪烁光标

**涉及文件**：`components/chat-message.tsx`

**预期效果**：流式输出平稳，不再出现视觉抖动。

---

### 1-3 统一设置面板（右侧 Sheet）

**描述**：目前没有任何用户设置入口——API 配置、主题偏好、导出格式默认值、键盘快捷键说明等全部缺乏 UI。

**实现思路**：
- 新建 `components/settings-panel.tsx`，基于 shadcn/ui 的 `Sheet` 组件，从右侧滑出
- 面板包含多个 Tab 或分节：
  - **通用**：主题切换（dark/light）、语言（预留）
  - **API 配置**：后端地址显示、WebSocket 地址
  - **导出偏好**：默认格式（CSV/XLSX/MD 等）
  - **快捷键**：列出所有支持的键盘快捷键（静态文字）
- `ui-store.ts`：新增 `settingsOpen: boolean` 和 `setSettingsOpen`
- `layout.tsx` 或 `page.tsx`：渲染 `<SettingsPanel />`
- `chat-area.tsx`：标题栏的"更多"下拉菜单中增加"设置"入口

**涉及文件**：`components/settings-panel.tsx`（新建）、`stores/ui-store.ts`、`app/page.tsx`、`components/chat-area.tsx`

**预期效果**：用户有统一的配置界面，消除配置入口缺失的问题。

---

### 1-4 多主题 CSS 变量切换

**描述**：当前只支持 dark/light 两套主题，不可扩展。

**实现思路**：
- `globals.css`：新增 `.theme-dracula`、`.theme-nord`、`.theme-monokai` 等 CSS 变量组（在 `.dark` 和 `:root` 块之外），覆盖 `--background`、`--foreground`、`--primary` 等核心变量
- `components/theme-toggle.tsx`：从简单的 dark/light 切换改为下拉菜单或弹出选择器，列出所有可用主题
- `components/theme-provider.tsx`：结合 `next-themes` 的 `attribute="class"`，将主题名同时写入 class（如 `dark theme-dracula`）
- 主题的选择存入 `localStorage`（可通过 persist 或 next-themes 的 `setTheme` 实现）

**涉及文件**：`app/globals.css`、`components/theme-toggle.tsx`、`components/theme-provider.tsx`

**预期效果**：用户可自由切换 Dracula / Nord / Monokai 等风格，视觉定制能力强。

---

### 1-5 Ctrl+Enter 快捷键及键盘增强

**描述**：当前仅支持 Enter 发送、Shift+Enter 换行，缺少常用快捷操作。

**实现思路**：
- `chat-input.tsx`：增加 `Ctrl+Enter` 也触发发送（目前仅 Enter）
- 全局键盘监听（在 `chat-area.tsx` 或新建 `hooks/use-keyboard-shortcuts.ts`）：
  - `Ctrl+K`：聚焦搜索栏
  - `Ctrl+N`：新建任务
  - `Ctrl+Shift+,`：打开设置面板
  - `Escape`：关闭侧边栏/弹窗
- 在 `settings-panel.tsx` 的快捷键页面列出所有支持的快捷键
- 使用 `useEffect` 在 `chat-area.tsx` 中注册 `keydown` 监听，在 `onDestroy` 时清理

**涉及文件**：`components/chat-input.tsx`、`components/chat-area.tsx`、`hooks/use-keyboard-shortcuts.ts`（新建）、`components/settings-panel.tsx`

**预期效果**：快捷键触达主要操作，资深用户效率提升明显。

---

## P2 — 细节打磨（值得做）

### 2-1 消息编辑内联模式

**描述**：当前编辑消息通过 `EditMessageDialog` 弹窗完成，打断了对话流。

**实现思路**：
- 点击编辑后，不弹对话框，而是将消息气泡原地切换为 `<textarea>` 编辑模式
- 编辑完成后按 Enter 提交（Shift+Enter 换行），Escape 取消，点击外部区域也可取消
- 编辑状态由 `ui-store` 的 `editTarget` 控制，新增 `editingTaskId: string | null` 标识哪个任务正在被编辑
- 参考 GitHub PR 评论的 inline edit 交互模式

**涉及文件**：`components/chat-message.tsx`、`stores/ui-store.ts`、`components/edit-message-dialog.tsx`（可替换或降级为后备）

**预期效果**：消息编辑不再跳弹窗，沉浸式编辑体验。

---

### 2-2 会话历史分组排序

**描述**：侧边栏目前按"今天/昨天/本周/更早"硬编码分组，不支持自定义分组、置顶会话固定（pin 功能已有但展示层面无区分）、归档。

**实现思路**：
- `sidebar.tsx`：调整分组逻辑，置顶任务始终在最上方（独立分组"置顶"）
- 在 `task-store.ts` 中增加 `pinnedTaskIds: string[]`，排序时优先展示
- 增加折叠/展开分组的功能（点击分组标题收拢）
- 分组标题增加任务计数

**涉及文件**：`components/sidebar.tsx`、`components/sidebar-task-item.tsx`、`stores/task-store.ts`

**预期效果**：重要任务可置顶，频繁使用的任务始终可快速访问。

---

### 2-3 消息撤回（Undo）增强

**描述**：当前删除消息后通过 `UndoToast` 提供撤销（`undoQueue`），但仅在删除时触发，且撤销队列无 UI 提示具体内容。

**实现思路**：
- `undo-toast.tsx`：优化 Toast 内容，显示被删除消息的前 30 字摘要，而非仅"消息已删除"
- 增加"批量撤销"按钮（当队列有多条消息时）
- `chat-store.ts`：增加撤销生存期，3 分钟后自动清空过期条目

**涉及文件**：`components/undo-toast.tsx`、`stores/chat-store.ts`

**预期效果**：撤销更直观，用户知道自己在撤回什么。

---

### 2-4 网络连接状态指示

**描述**：WebSocket 断开时，目前可能静默重连（`websocket.ts` 有自动重连逻辑），但用户没有感知。

**实现思路**：
- `connection-banner.tsx`（已有组件 file，但功能是否就位需确认）：在 WebSocket 断开时显示顶部黄色横幅"连接已断开，正在重连…"
- 使用 `useTaskStream` 或 `websocket.ts` 暴露的连接状态事件
- 连接恢复后横幅自动消失（3s 渐变退场）

**涉及文件**：`components/connection-banner.tsx`、`hooks/use-task-stream.ts`、`services/websocket.ts`

**预期效果**：网络问题透明化，用户不会因为连接断开而困惑。

---

### 2-5 导出格式偏好记忆

**描述**：用户每次导出时选择格式，下次默认为 CSV，没有记忆性。

**实现思路**：
- `ui-store.ts` 中增加 `defaultExportFormat: string`，持久化到 localStorage
- `chat-area.tsx` 或 `task-result-panel.tsx` 中的导出按钮/下拉菜单读取此偏好，优先选中用户上次使用的格式
- 设置面板中提供导出格式默认值的选择器

**涉及文件**：`stores/ui-store.ts`、`components/task-result-panel.tsx`、`components/settings-panel.tsx`

**预期效果**：减少重复操作，导出流程更顺滑。

---

## 优先级总览

| 编号 | 项目 | 优先级 | 复杂度 | 文件改动数 |
|------|------|--------|--------|-----------|
| 0-1 | 流式消息闪烁光标 | P0 | 低 | 2 |
| 0-2 | 代码块复制按钮 | P0 | 低 | 1 |
| 0-3 | Zustand persist 持久化 | P0 | 中 | 3 |
| 0-4 | 右键上下文菜单 | P0 | 中 | 2（含新建） |
| 1-1 | fuse.js 模糊搜索 | P1 | 中 | 3 |
| 1-2 | 流式渲染容器稳定 | P1 | 低 | 1 |
| 1-3 | 统一设置面板 | P1 | 高 | 4（含新建） |
| 1-4 | 多主题 CSS 变量 | P1 | 中 | 3 |
| 1-5 | Ctrl+Enter 及键盘增强 | P1 | 中 | 3（含新建） |
| 2-1 | 消息内联编辑 | P2 | 中 | 3 |
| 2-2 | 会话分组增强 + 置顶 | P2 | 低 | 3 |
| 2-3 | 撤销增强 | P2 | 低 | 2 |
| 2-4 | 网络连接状态指示 | P2 | 低 | 3 |
| 2-5 | 导出格式偏好记忆 | P2 | 低 | 3 |

**建议实施顺序**：P0 → P1 → P2，同层级内按编号顺序。0-3（persist）建议最先做，因为它会 touch 三个 store，后面的改动都受益于状态的持久化。
