const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

function downloadUrl(filename: string): string {
  return `${BACKEND_URL}/api/download/${encodeURIComponent(filename)}`;
}


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
  getTaskMessages: (taskId: string, limit = 0) =>
    request<{ messages?: unknown[]; total?: number; task?: { messages?: unknown[] } }>(`${BACKEND_URL}/api/history/${taskId}?limit=${limit}`),
  searchTasks: (query: string) =>
    request<{ tasks: Array<{ id: string; title: string; date: string; status: string; messages?: unknown[]; pinned?: boolean }> }>(`${BACKEND_URL}/api/history/search?q=${encodeURIComponent(query)}`),
  createChat: (message: string, taskId?: string) =>
    request<{ task_id: string }>(`${BACKEND_URL}/api/chat`, {
      method: "POST",
      body: JSON.stringify({ message, task_id: taskId }),
    }),
  renameTask: (taskId: string, title: string) =>
    request<void>(`${BACKEND_URL}/api/history/${taskId}/rename`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  pinTask: (taskId: string) =>
    request<void>(`${BACKEND_URL}/api/history/${taskId}/pin`, { method: "PATCH" }),
  deleteTask: (taskId: string) =>
    request<void>(`${BACKEND_URL}/api/history/${taskId}`, { method: "DELETE" }),
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
  getUniversityRecords: (name: string) =>
    request<UniversityRecordsResponse>(`${BACKEND_URL}/api/universities/${encodeURIComponent(name)}/records`),
  getUniversityTable: (
    name: string,
    params?: { task_id?: string; file?: string; limit?: number; offset?: number; q?: string; department?: string; valid_only?: boolean }
  ) => {
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
  detectSmtp: (email: string) =>
    request<Record<string, unknown>>(`${BACKEND_URL}/api/smtp/detect`, {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  verifySmtp: (input: Record<string, unknown>) =>
    request<Record<string, unknown>>(`${BACKEND_URL}/api/smtp/verify`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  previewMail: (input: Record<string, unknown>) =>
    request<MailPreviewResponse>(`${BACKEND_URL}/api/mail/preview`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  sendMail: (input: Record<string, unknown>) =>
    request<MailSendResponse>(`${BACKEND_URL}/api/mail/send`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  getMailJob: (jobId: string) => request<Record<string, unknown>>(`${BACKEND_URL}/api/mail/jobs/${jobId}`),
  exportMailJobUrl: (jobId: string, format = "csv") =>
    `${BACKEND_URL}/api/mail/jobs/${jobId}/export?format=${encodeURIComponent(format)}`,
};
