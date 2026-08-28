function normalizeUrl(url: string): string {
  return url.replace(/\/+$/, "");
}

function isLocalHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}

function pointsToLocalhost(url: string): boolean {
  try {
    const parsed = new URL(url);
    return isLocalHost(parsed.hostname);
  } catch {
    return false;
  }
}

function getBackendUrl(): string {
  if (typeof window !== "undefined") {
    const { origin, hostname } = window.location;
    const onLocalHost = isLocalHost(hostname);
    const localUrl = localStorage.getItem("backendUrl");
    if (localUrl && (onLocalHost || !pointsToLocalhost(localUrl))) {
      return normalizeUrl(localUrl);
    }
    if (!onLocalHost) {
      return origin;
    }
  }
  // 优先使用 NEXT_PUBLIC_BACKEND_URL 环境变量（开发环境指向后端端口）
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_BACKEND_URL) {
    return normalizeUrl(process.env.NEXT_PUBLIC_BACKEND_URL);
  }
  if (typeof window !== "undefined") {
    return normalizeUrl(window.location.origin);
  }
  return "http://localhost:8070";
}

const BACKEND_URL = getBackendUrl();

function getUserId(): string {
  if (typeof window === "undefined") return "";
  const key = "uniemailUserId";
  let value = localStorage.getItem(key);
  if (!value) {
    value = crypto.randomUUID();
    localStorage.setItem(key, value);
  }
  return value;
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {};
  if (!(options?.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const userId = getUserId();
  if (userId) headers["X-UniEmail-User-Id"] = userId;
  const res = await fetch(url, {
    ...options,
    headers: { ...headers, ...(options?.headers ?? {}) },
  });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

function downloadUrl(filename: string, taskId?: string): string {
  const prefix = taskId ? `${encodeURIComponent(taskId)}/` : "";
  return `${BACKEND_URL}/api/download/${prefix}${encodeURIComponent(filename)}`;
}

interface UniversityListResponse {
  total: number;
  groups: Array<{ province: string; count: number; cities: Array<{ city: string; count: number; universities: any[] }> }>;
  provinces: string[];
  storage?: UniversityStorageInfo;
  tier_counts: Record<string, number>;
}

interface UniversityStorageInfo {
  root?: string;
  data_dir?: string;
  universities_dir?: string;
  mail_dir?: string;
  catalog_file?: string;
}

interface UniversityTableResponse {
  columns: string[];
  rows: Record<string, string>[];
  total: number;
  raw_total: number;
  offset: number;
  limit: number;
  valid_email_count: number;
  departments: string[];
}

export const api = {
  // ── 核心对话 ──
  getHistory: () =>
    request<{ tasks: Array<{ id: string; title: string; date: string; status: string; messages?: unknown[]; pinned?: boolean }> }>(`${BACKEND_URL}/api/history`),
  getTaskMessages: (taskId: string, limit = 0) =>
    request<{ messages?: unknown[]; total?: number; task?: { messages?: unknown[] } }>(`${BACKEND_URL}/api/history/${taskId}?limit=${limit}`),
  createChat: (message: string, taskId?: string) =>
    request<{ task_id: string }>(`${BACKEND_URL}/api/chat`, { method: "POST", body: JSON.stringify({ message, task_id: taskId }) }),
  renameTask: (taskId: string, title: string) =>
    request<void>(`${BACKEND_URL}/api/history/${taskId}/rename`, { method: "PATCH", body: JSON.stringify({ title }) }),
  pinTask: (taskId: string) =>
    request<void>(`${BACKEND_URL}/api/history/${taskId}/pin`, { method: "PATCH" }),
  deleteTask: (taskId: string) =>
    request<void>(`${BACKEND_URL}/api/history/${taskId}`, { method: "DELETE" }),

  // ── 工具 ──
  downloadUrl,
  getBackendUrl: () => BACKEND_URL,
  getWsUrl: (taskId: string) =>
    `${BACKEND_URL.replace("http", "ws")}/ws/${taskId}?user_id=${encodeURIComponent(getUserId())}`,
  getActiveAgents: () =>
    request<{ active_tasks: Array<{ task_id: string; title: string; started_at: string }> }>(`${BACKEND_URL}/api/agent/active`),
  terminateAgent: (taskId: string) =>
    request<{ ok: boolean; message: string }>(`${BACKEND_URL}/api/agent/terminate`, { method: "POST", body: JSON.stringify({ task_id: taskId }) }),
  getTaskSummary: (taskId: string) =>
    request<import("@/lib/types").TaskSummary>(`${BACKEND_URL}/api/history/${taskId}/summary`),

  // ── 助手 ──
  classifyTask: (message: string) =>
    request<{ is_crawl: boolean; intent: string; university: string; departments: string[]; reason: string }>(`${BACKEND_URL}/api/classify`, { method: "POST", body: JSON.stringify({ message }) }),
  askKnowledgeAgent: (message: string, university?: string) =>
    request<{ answer: string; sources?: Array<Record<string, string>> }>(`${BACKEND_URL}/api/assistant/kb`, { method: "POST", body: JSON.stringify({ message, university }) }),
  askChatAgent: (message: string) =>
    request<{ answer: string }>(`${BACKEND_URL}/api/assistant/chat`, { method: "POST", body: JSON.stringify({ message }) }),

  // ── 高校库 ──
  getUniversities: (params?: { province?: string; tier?: string; q?: string }) => {
    const search = new URLSearchParams();
    if (params?.province) search.set("province", params.province);
    if (params?.tier) search.set("tier", params.tier);
    if (params?.q) search.set("q", params.q);
    return request<UniversityListResponse>(`${BACKEND_URL}/api/universities${search.toString() ? `?${search.toString()}` : ""}`);
  },
  getUniversityRecords: (name: string) =>
    request<any>(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/records`),
  getUniversityStorage: () =>
    request<{ storage: UniversityStorageInfo }>(`${BACKEND_URL}/api/universities/storage`),
  updateUniversityStorage: (data_dir: string) =>
    request<{ ok: boolean; storage: UniversityStorageInfo }>(`${BACKEND_URL}/api/universities/storage`, { method: "POST", body: JSON.stringify({ data_dir }) }),
  getUniversityTable: (name: string, params?: { task_id?: string; file?: string; limit?: number; offset?: number; q?: string; department?: string; valid_only?: boolean }) => {
    const search = new URLSearchParams();
    if (params?.task_id) search.set("task_id", params.task_id);
    if (params?.file) search.set("file", params.file);
    if (params?.limit != null) search.set("limit", String(params.limit));
    if (params?.offset != null) search.set("offset", String(params.offset));
    if (params?.q) search.set("q", params.q);
    if (params?.department) search.set("department", params.department);
    if (params?.valid_only) search.set("valid_only", "true");
    return request<UniversityTableResponse>(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/table?${search.toString()}`);
  },
  uploadUniversityFile: (name: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    const userId = getUserId();
    return fetch(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/files`, {
      method: "POST", body: form,
      headers: userId ? { "X-UniEmail-User-Id": userId } : undefined,
    }).then((r) => r.json());
  },
  deleteUniversityFile: (name: string, task_id: string, filename: string) =>
    request<{ ok: boolean }>(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/files?task_id=${encodeURIComponent(task_id)}&filename=${encodeURIComponent(filename)}`, { method: "DELETE" }),
  renameUniversityFile: (name: string, task_id: string, filename: string, new_filename: string) =>
    request<{ ok: boolean }>(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/files`, { method: "PATCH", body: JSON.stringify({ task_id, filename, new_filename }) }),
  addTableRow: (name: string, task_id: string, file: string, row: Record<string, string>) =>
    request<{ ok: boolean; row_index: number }>(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/table/rows`, { method: "POST", body: JSON.stringify({ task_id, file, row }) }),
  updateTableRow: (name: string, task_id: string, file: string, row_index: number, row: Record<string, string>) =>
    request<{ ok: boolean }>(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/table/rows/${row_index}`, { method: "PUT", body: JSON.stringify({ task_id, file, row }) }),
  deleteTableRow: (name: string, task_id: string, file: string, row_index: number) =>
    request<{ ok: boolean }>(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/table/rows/${row_index}?task_id=${encodeURIComponent(task_id)}&file=${encodeURIComponent(file)}`, { method: "DELETE" }),
  cleanUniversityTable: (name: string) =>
    request<any>(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/clean`, { method: "POST" }),
  exportUniversityTable: (name: string, task_id: string, file: string, formats: string[]) =>
    request<{ ok: boolean; files: Record<string, string> }>(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/export`, { method: "POST", body: JSON.stringify({ task_id, file, formats }) }),

  // ── 配置 ──
  getConfig: () =>
    request<{ deepseek_api_key: string; has_deepseek_key: boolean; service_mode: string; session_tokens?: number }>(`${BACKEND_URL}/api/config`),
  updateConfig: (data: { deepseek_api_key?: string | null; service_mode?: string }) =>
    request<{ ok: boolean; has_deepseek_key: boolean }>(`${BACKEND_URL}/api/config`, { method: "POST", body: JSON.stringify({ service_mode: "custom", ...data }) }),

  // ── SMTP / 邮件 ──
  detectSmtp: (email: string) =>
    request<Record<string, unknown>>(`${BACKEND_URL}/api/smtp/detect`, { method: "POST", body: JSON.stringify({ email }) }),
  verifySmtp: (input: Record<string, unknown>) =>
    request<Record<string, unknown>>(`${BACKEND_URL}/api/smtp/verify`, { method: "POST", body: JSON.stringify(input) }),
  previewMail: (input: Record<string, unknown>) =>
    request<any>(`${BACKEND_URL}/api/mail/preview`, { method: "POST", body: JSON.stringify(input) }),
  sendMail: (input: Record<string, unknown>) =>
    request<{ jobId: string; sendableCount: number }>(`${BACKEND_URL}/api/mail/send`, { method: "POST", body: JSON.stringify(input) }),
  getMailJob: (jobId: string) =>
    request<Record<string, unknown>>(`${BACKEND_URL}/api/mail/jobs/${jobId}`),
  exportMailJobUrl: (jobId: string, format = "csv") =>
    `${BACKEND_URL}/api/mail/jobs/${jobId}/export?format=${encodeURIComponent(format)}`,
};
