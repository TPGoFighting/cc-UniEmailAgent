// ═══════════════════════════════════════════════════════════════
// 消息系统 — 精简为 4 种角色
// ═══════════════════════════════════════════════════════════════

export type MessageRole = "user" | "agent" | "log" | "download" | "activity" | "worker_progress";

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp?: string;
  filename?: string;
  url?: string;
  isStreaming?: boolean;
}

export type TaskStatus = "completed" | "failed" | "running" | "stopped";

export interface Task {
  id: string;
  title: string;
  date: string;
  status: TaskStatus;
  messages: Message[];
  pinned?: boolean;
}

export type ComposerState =
  | "idle"
  | "connecting"
  | "streaming"
  | "completed"
  | "stopped"
  | "error";

// ═══════════════════════════════════════════════════════════════
// 活动事件系统 — Agent 实时活动流
// ═══════════════════════════════════════════════════════════════

export type AgentActivityType = "thinking" | "executing" | "executed";

export interface AgentActivity {
  type: AgentActivityType;
  tool?: string;
  input?: Record<string, unknown>;
  summary?: string;
  reflection?: {
    evaluation?: string;
    memory?: string;
    next_goal?: string;
  };
}

// ═══════════════════════════════════════════════════════════════
// Worker 进度事件
// ═══════════════════════════════════════════════════════════════

export interface WorkerProgress {
  name: string;
  status: "pending" | "running" | "done" | "error";
  found?: number;
  emails?: number;
  error?: string;
}

// ═══════════════════════════════════════════════════════════════
// WebSocket 协议 — 扩展后的事件类型
// ═══════════════════════════════════════════════════════════════

export type WSEvent =
  | { type: "text"; message: string; timestamp: string }
  | { type: "log"; message: string; timestamp: string }
  | { type: "download"; message: string; filename: string; url: string; timestamp: string }
  | { type: "done"; message?: string; timestamp?: string }
  | { type: "error"; message: string }
  | { type: "activity"; activity: AgentActivity; timestamp: string }
  | { type: "worker_progress"; worker_progress: WorkerProgress; timestamp: string };

export interface WSEventHandlers {
  onLog: (msg: string, timestamp: string) => void;
  onText: (msg: string, timestamp: string) => void;
  onDownload: (msg: string, filename: string, url: string, timestamp: string) => void;
  onDone: (message?: string, timestamp?: string) => void;
  onError: (msg: string) => void;
  onActivity: (activity: AgentActivity, timestamp: string) => void;
  onWorkerProgress: (progress: WorkerProgress, timestamp: string) => void;
  onClose: () => void;
}

// ═══════════════════════════════════════════════════════════════
// 并行爬取状态（dispatch_workers 工具）
// ═══════════════════════════════════════════════════════════════

export interface ParallelCrawlState {
  university: string;
  total_workers: number;
  workers: WorkerProgress[];
  started_at: string;
}

// ═══════════════════════════════════════════════════════════════
// 高校库类型（不变）
// ═══════════════════════════════════════════════════════════════

export interface University {
  name: string;
  province: string;
  city: string;
  type: string;
  domain?: string;
  website?: string;
  is_985: boolean;
  is_211: boolean;
  is_double_first_class: boolean;
  tags: string[];
  has_data: boolean;
  records: {
    file_count: number;
    table_count: number;
    row_count: number;
    valid_email_count: number;
  };
}

export interface UniversityGroup {
  province: string;
  count: number;
  cities: Array<{ city: string; count: number; universities: University[] }>;
}

// ═══════════════════════════════════════════════════════════════
// 任务摘要 / 高校产出（不变）
// ═══════════════════════════════════════════════════════════════

export interface TaskSummary {
  task_id: string;
  status: string;
  files: Array<{ filename: string; size: number; url: string }>;
  total_teachers: number;
  valid_emails: number;
  coverage: number;
  colleges: Array<{ name: string; count: number }>;
  preview_rows: Array<{ name: string; email: string; department: string }>;
}

export interface UniversityRecord {
  task_id: string;
  filename: string;
  ext: string;
  url: string;
  size: number;
  updated_at: string;
  row_count: number;
  valid_email_count: number;
  previewable: boolean;
  is_best?: boolean;
}

// ═══════════════════════════════════════════════════════════════
// 质量评估（不变）
// ═══════════════════════════════════════════════════════════════

export interface QualityEvalData {
  quality_score: number;
  passed: boolean;
  warnings: string[];
  email_rate: number;
  colleges_found: string[];
  timestamp: string;
}

// ═══════════════════════════════════════════════════════════════
// 意图分类（后端 DirectorAgent 内部处理，前端仅保留引用）
// ═══════════════════════════════════════════════════════════════

export type IntentType = "simple_query" | "new_crawl" | "incremental";

export interface IntentResult {
  is_crawl: boolean;
  intent: IntentType;
  university: string;
  departments: string[];
  reason: string;
}
