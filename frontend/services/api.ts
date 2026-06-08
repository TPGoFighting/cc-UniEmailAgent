function getBackendUrl(): string {
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_BACKEND_URL) {
    return process.env.NEXT_PUBLIC_BACKEND_URL;
  }
  return "http://localhost:8000";
}

const BACKEND_URL = getBackendUrl();

/** Generic request helper */
async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {};
  // When body is FormData, let the browser set Content-Type (multipart boundary)
  if (!(options?.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(url, {
    ...options,
    headers: {
      ...headers,
      ...(options?.headers ?? {}),
    },
  });

  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/** Helper to build download URL */
function downloadUrl(filename: string, taskId?: string): string {
  const prefix = taskId ? `${encodeURIComponent(taskId)}/` : "";
  return `${BACKEND_URL}/api/download/${prefix}${encodeURIComponent(filename)}`;
}

/** Types for university endpoints */
interface UniversityListResponse {
  total: number;
  groups: Array<{ province: string; count: number; cities: Array<{ city: string; count: number; universities: any[] }> }>;
  provinces: string[];
  tier_counts: Record<string, number>;
}

interface UniversityRecordsResponse {
  name: string;
  summary: Record<string, number>;
  records: Array<{ task_id: string; filename: string; ext: string; url: string; size: number; updated_at: string; row_count: number; valid_email_count: number; previewable: boolean }>;
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

interface MailPreviewResponse {
  variables: string[];
  previews: Array<Record<string, unknown>>;
  totalRows: number;
  invalidCount: number;
  sendableCount: number;
  threshold: number;
}

interface MailSendResponse {
  jobId: string;
  sendableCount: number;
}

export const api = {
  getHistory: () => request<{ tasks: Array<{ id: string; title: string; date: string; status: string; messages?: unknown[]; pinned?: boolean }> }>(`${BACKEND_URL}/api/history`),
  getTaskMessages: (taskId: string, limit = 0) => request<{ messages?: unknown[]; total?: number; task?: { messages?: unknown[] } }>(`${BACKEND_URL}/api/history/${taskId}?limit=${limit}`),
  searchTasks: (query: string) => request<{ tasks: Array<{ id: string; title: string; date: string; status: string; messages?: unknown[]; pinned?: boolean }> }>(`${BACKEND_URL}/api/history/search?q=${encodeURIComponent(query)}`),
  createChat: (message: string, taskId?: string) => request<{ task_id: string }>(`${BACKEND_URL}/api/chat`, { method: "POST", body: JSON.stringify({ message, task_id: taskId }) }),
  renameTask: (taskId: string, title: string) => request<void>(`${BACKEND_URL}/api/history/${taskId}/rename`, { method: "PATCH", body: JSON.stringify({ title }) }),
  pinTask: (taskId: string) => request<void>(`${BACKEND_URL}/api/history/${taskId}/pin`, { method: "PATCH" }),
  deleteTask: (taskId: string) => request<void>(`${BACKEND_URL}/api/history/${taskId}`, { method: "DELETE" }),
  downloadUrl,
  getBackendUrl: () => BACKEND_URL,
  getWsUrl: (taskId: string) => `${BACKEND_URL.replace("http", "ws")}/ws/${taskId}`,
  getUniversities: (params?: { province?: string; tier?: string; q?: string }) => {
    const search = new URLSearchParams();
    if (params?.province) search.set("province", params.province);
    if (params?.tier) search.set("tier", params.tier);
    if (params?.q) search.set("q", params.q);
    return request<UniversityListResponse>(`${BACKEND_URL}/api/universities${search.toString() ? `?${search.toString()}` : ""}`);
  },
  getUniversityRecords: (name: string) => request<UniversityRecordsResponse>(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/records`),
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
  // ── 高校文件 CRUD ──
  uploadUniversityFile: (name: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/files`, { method: "POST", body: form }).then(r => r.json());
  },
  deleteUniversityFile: (name: string, task_id: string, filename: string) =>
    request<{ ok: boolean }>(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/files?task_id=${encodeURIComponent(task_id)}&filename=${encodeURIComponent(filename)}`, { method: "DELETE" }),
  renameUniversityFile: (name: string, task_id: string, filename: string, new_filename: string) =>
    request<{ ok: boolean }>(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/files`, { method: "PATCH", body: JSON.stringify({ task_id, filename, new_filename }) }),
  // ── 表格行 CRUD ──
  addTableRow: (name: string, task_id: string, file: string, row: Record<string, string>) =>
    request<{ ok: boolean; row_index: number }>(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/table/rows`, { method: "POST", body: JSON.stringify({ task_id, file, row }) }),
  updateTableRow: (name: string, task_id: string, file: string, row_index: number, row: Record<string, string>) =>
    request<{ ok: boolean }>(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/table/rows/${row_index}`, { method: "PUT", body: JSON.stringify({ task_id, file, row }) }),
  deleteTableRow: (name: string, task_id: string, file: string, row_index: number) =>
    request<{ ok: boolean }>(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/table/rows/${row_index}?task_id=${encodeURIComponent(task_id)}&file=${encodeURIComponent(file)}`, { method: "DELETE" }),
  // ── SMTP / 邮件 ──
  detectSmtp: (email: string) => request<Record<string, unknown>>(`${BACKEND_URL}/api/smtp/detect`, { method: "POST", body: JSON.stringify({ email }) }),
  verifySmtp: (input: Record<string, unknown>) => request<Record<string, unknown>>(`${BACKEND_URL}/api/smtp/verify`, { method: "POST", body: JSON.stringify(input) }),
  previewMail: (input: Record<string, unknown>) => request<MailPreviewResponse>(`${BACKEND_URL}/api/mail/preview`, { method: "POST", body: JSON.stringify(input) }),
  sendMail: (input: Record<string, unknown>) => request<MailSendResponse>(`${BACKEND_URL}/api/mail/send`, { method: "POST", body: JSON.stringify(input) }),
  getMailJob: (jobId: string) => request<Record<string, unknown>>(`${BACKEND_URL}/api/mail/jobs/${jobId}`),
  exportMailJobUrl: (jobId: string, format = "csv") => `${BACKEND_URL}/api/mail/jobs/${jobId}/export?format=${encodeURIComponent(format)}`,
  getActiveAgents: () => request<{ active_tasks: Array<{ task_id: string; title: string; started_at: string }> }>(`${BACKEND_URL}/api/agent/active`),
  terminateAgent: (taskId: string) => request<{ ok: boolean; message: string }>(`${BACKEND_URL}/api/agent/terminate`, { method: "POST", body: JSON.stringify({ task_id: taskId }) }),
  classifyTask: (message: string) => request<{ is_crawl: boolean; intent: string; university: string; departments: string[]; reason: string }>(`${BACKEND_URL}/api/classify`, { method: "POST", body: JSON.stringify({ message }) }),
  getTaskSummary: (taskId: string) => request<import("@/lib/types").TaskSummary>(`${BACKEND_URL}/api/history/${taskId}/summary`),
  // ── 高校表格导出 ──
  exportUniversityTable: (name: string, task_id: string, file: string, formats: string[]) =>
    request<{ ok: boolean; files: Record<string, string> }>(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/export`, {
      method: "POST",
      body: JSON.stringify({ task_id, file, formats }),
    }),
};
