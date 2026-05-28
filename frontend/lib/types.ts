export type MessageRole = "user" | "agent" | "progress" | "download";

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp?: string;
  filename?: string;
  url?: string;
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

export type ComposerState = "idle" | "connecting" | "streaming" | "completed" | "stopped";

export type WSEvent =
  | { type: "progress"; message: string; step: number; total: number; timestamp: string }
  | { type: "download"; message: string; filename: string; url: string; timestamp: string }
  | { type: "done"; message?: string; timestamp?: string }
  | { type: "error"; message: string };

export interface WSEventHandlers {
  onLog: (msg: string, timestamp: string) => void;
  onProgress: (msg: string, step: number, total: number, timestamp: string) => void;
  onDownload: (msg: string, filename: string, url: string, timestamp: string) => void;
  onDone: (message?: string, timestamp?: string) => void;
  onError: (msg: string) => void;
  onClose: () => void;
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
