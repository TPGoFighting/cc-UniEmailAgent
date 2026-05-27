// ===== 消息和任务类型定义 =====

export type MessageRole = "user" | "agent" | "log" | "download";

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp?: string;
  filename?: string;
  url?: string;
  isStreaming?: boolean;
}

export type TaskStatus = "completed" | "failed" | "running";

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
  | "stopped";

// ===== WebSocket 事件类型 =====

export type WSEvent =
  | { type: "log"; message: string; timestamp: string }
  | { type: "download"; message: string; filename: string; url: string; timestamp: string }
  | { type: "done" }
  | { type: "error"; message: string };

export interface WSEventHandlers {
  onLog: (msg: string, timestamp: string) => void;
  onDownload: (msg: string, filename: string, url: string, timestamp: string) => void;
  onDone: () => void;
  onError: (msg: string) => void;
  onClose: () => void;
}
