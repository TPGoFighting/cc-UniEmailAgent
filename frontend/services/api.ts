const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

// ===== 通用 fetch 封装 =====

async function request<T>(
  url: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    throw new Error(`请求失败: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

function downloadUrl(filename: string): string {
  return `${BACKEND_URL}/api/download/${encodeURIComponent(filename)}`;
}

// ===== API 类型 =====

interface CreateChatResponse {
  task_id: string;
}

interface HistoryResponse {
  tasks: Array<{
    id: string;
    title: string;
    date: string;
    status: string;
    messages?: unknown[];
    pinned?: boolean;
  }>;
}

interface TaskMessagesResponse {
  messages?: unknown[];
  total?: number;
  task?: { messages?: unknown[] };
}

// ===== API 函数 =====

export const api = {
  /** 获取历史任务列表 */
  getHistory: () =>
    request<HistoryResponse>(`${BACKEND_URL}/api/history`),

  /** 获取指定任务的消息 */
  getTaskMessages: (taskId: string, limit = 200) =>
    request<TaskMessagesResponse>(
      `${BACKEND_URL}/api/history/${taskId}?limit=${limit}`
    ),

  /** 搜索历史任务 */
  searchTasks: (query: string) =>
    request<HistoryResponse>(
      `${BACKEND_URL}/api/history/search?q=${encodeURIComponent(query)}`
    ),

  /** 创建聊天任务 */
  createChat: (message: string, taskId?: string) =>
    request<CreateChatResponse>(`${BACKEND_URL}/api/chat`, {
      method: "POST",
      body: JSON.stringify({ message, task_id: taskId }),
    }),

  /** 重命名任务 */
  renameTask: (taskId: string, title: string) =>
    request<void>(`${BACKEND_URL}/api/history/${taskId}/rename`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),

  /** 切换置顶状态 */
  pinTask: (taskId: string) =>
    request<void>(`${BACKEND_URL}/api/history/${taskId}/pin`, {
      method: "PATCH",
    }),

  /** 删除任务 */
  deleteTask: (taskId: string) =>
    request<void>(`${BACKEND_URL}/api/history/${taskId}`, {
      method: "DELETE",
    }),

  /** 构建下载 URL */
  downloadUrl,

  /** 后端基础 URL */
  getBackendUrl: () => BACKEND_URL,

  /** WebSocket URL */
  getWsUrl: (taskId: string) =>
    `${BACKEND_URL.replace("http", "ws")}/ws/${taskId}`,
};
