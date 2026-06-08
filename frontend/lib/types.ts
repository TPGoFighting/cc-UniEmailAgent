export type MessageRole = "user" | "agent" | "text" | "progress" | "download" | "log" | "file";

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp?: string;
  filename?: string;
  url?: string;
  filepath?: string;
  isStreaming?: boolean;
  step?: number;
  total?: number;
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

export type ComposerState = "idle" | "connecting" | "streaming" | "completed" | "stopped" | "error";

export type IntentType = "simple_query" | "new_crawl" | "incremental";

export interface IntentResult {
  is_crawl: boolean;
  intent: IntentType;
  university: string;
  departments: string[];
  reason: string;
}

export type WSEvent =
  | { type: "progress"; message: string; step: number; total: number; timestamp: string }
  | { type: "download"; message: string; filename: string; url: string; timestamp: string }
  | { type: "file"; message: string; filename: string; filepath: string; timestamp: string }
  | { type: "log"; message: string; timestamp: string }
  | { type: "agent"; message: string; timestamp: string }
  | { type: "text"; message: string; timestamp: string }
  | { type: "done"; message?: string; timestamp?: string }
  | { type: "error"; message: string }
  | { type: "stage_start"; stage: string; college: string; college_index: number; college_total: number }
  | { type: "stage_progress"; stage: string; phase: "listing" | "extracting" | "done"; found?: number; extracted?: number; total_pages?: number }
  | { type: "stage_done"; stage: string; college: string; found: number; valid_email: number; elapsed_ms: number }
  // Phase 1: New WS message types
  | { type: "stage"; stage: number; stage_name: string; progress_pct: number; timestamp: string }
  | { type: "stats"; teachers_found: number; emails_extracted: number; departments_done: number; department_names: string[]; timestamp: string }
  | { type: "summary"; university: string; total_teachers: number; total_emails: number; duration: string; files: Array<{ filename: string; url: string }>; timestamp: string }
  | { type: "error_user"; message: string; severity: "warning" | "error"; timestamp: string }
  // 质量评估 + 追踪
  | { type: "eval"; message: string; quality_score: number; passed: boolean; warnings: string[]; email_rate: number; colleges_found: string[]; timestamp: string }
  | { type: "trace"; run_id: string; trace_url: string; timestamp: string };

export interface StageState {
  colleges: CollegeStage[];
}

export interface CollegeStage {
  name: string;
  status: "pending" | "active" | "done";
  found?: number;
  extracted?: number;
  total_pages?: number;
  valid_email?: number;
  elapsed_ms?: number;
}

export interface CollegeStageHandler {
  onStageStart: (stage: string, college: string, collegeIndex: number, collegeTotal: number) => void;
  onStageProgress: (stage: string, phase: string, found?: number, extracted?: number, totalPages?: number) => void;
  onStageDone: (stage: string, college: string, found: number, validEmail: number, elapsedMs: number) => void;
}

export interface WSEventHandlers {
  onLog: (msg: string, timestamp: string) => void;
  onText: (msg: string, timestamp: string) => void;
  onProgress: (msg: string, step: number, total: number, timestamp: string) => void;
  onDownload: (msg: string, filename: string, url: string, timestamp: string) => void;
  onFile: (msg: string, filename: string, filepath: string, timestamp: string) => void;
  onDone: (message?: string, timestamp?: string) => void;
  onError: (msg: string) => void;
  onClose: () => void;
  stageHandlers?: CollegeStageHandler;
  // Phase 2: New WS event handlers
  onCrawlStage?: (stage: number, stageName: string, progressPct: number, timestamp: string) => void;
  onCrawlStats?: (teachersFound: number, emailsExtracted: number, departmentsDone: number, departmentNames: string[], timestamp: string) => void;
  onCrawlSummary?: (university: string, totalTeachers: number, totalEmails: number, duration: string, files: Array<{ filename: string; url: string }>, timestamp: string) => void;
  onErrorUser?: (message: string, severity: "warning" | "error", timestamp: string) => void;
  onEval?: (data: QualityEvalData) => void;
  onTrace?: (traceUrl: string) => void;
}

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
}

// Phase 2: Crawl UI state types
export interface CrawlStageState {
  stage: number;
  stage_name: string;
  progress_pct: number;
  timestamp: string;
}

export interface CrawlStatsData {
  teachers_found: number;
  emails_extracted: number;
  departments_done: number;
  department_names: string[];
  timestamp: string;
}

export interface CrawlSummaryData {
  university: string;
  total_teachers: number;
  total_emails: number;
  duration: string;
  files: Array<{ filename: string; url: string }>;
  timestamp: string;
}

export interface ErrorUserData {
  message: string;
  severity: "warning" | "error";
  timestamp: string;
}

export interface QualityEvalData {
  quality_score: number;
  passed: boolean;
  warnings: string[];
  email_rate: number;       // 0-1
  colleges_found: string[];
  timestamp: string;
}
