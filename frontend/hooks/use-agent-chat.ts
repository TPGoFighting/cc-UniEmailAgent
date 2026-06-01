"use client";

import { useCallback, useEffect, useRef } from "react";
import { useTaskStore } from "@/stores/task-store";
import { useChatStore } from "@/stores/chat-store";
import { useUIStore } from "@/stores/ui-store";
import { api } from "@/services/api";
import { isCrawlTask } from "@/services/classify";
import { useHistory } from "@/hooks/queries/use-history";
import { useTaskMessages } from "@/hooks/queries/use-task-messages";
import { useRenameTask, usePinTask, useDeleteTask } from "@/hooks/queries/use-task-mutations";
import { useTaskStream } from "@/hooks/use-task-stream";
import { welcomeMessage } from "@/lib/mock-data";
import type { Message, Task } from "@/lib/types";

let messageCounter = 0;
function nextId(): string {
  messageCounter += 1;
  return `msg-${Date.now()}-${messageCounter}`;
}

export function useAgentChat({
   streaming = false,
}: {
  /** 是否启用 WebSocket 流式连接。侧边栏等不需要流式推送的组件设为 false。 */
  streaming?: boolean;
} = {}) {
  // ===== Stores =====
  const {
    tasks,
    activeTaskId,
    setActiveTask,
    getActiveTask,
    addTask,
    updateTask,
  } = useTaskStore();

  const {
    currentMessages,
    composerStateMap,
    runningTaskIds,
    setCurrentMessages,
    appendMessage,
    setComposerState,
    addRunningTask,
    switchToTask,
  } = useChatStore();

  const { setSearchQuery } = useUIStore();

  const activeTask = getActiveTask();
  const composerState = activeTaskId ? (composerStateMap[activeTaskId] || "idle") : "idle";
  const isRunning = activeTaskId ? runningTaskIds.includes(activeTaskId) : false;

  // ===== TanStack Query =====
  const historyQuery = useHistory();
  const messagesQuery = useTaskMessages(
    // 仅在需要时加载消息（没有缓存的）
    activeTaskId && !useChatStore.getState().taskMessages[activeTaskId]
      ? activeTaskId
      : null
  );

  // ===== WebSocket Stream =====
  const streamEnabled = streaming &&
    (composerState === "connecting" || composerState === "streaming" || isRunning);

  const { stop: stopStream } = useTaskStream({
    taskId: activeTaskId,
    enabled: streamEnabled,
  });

  // ===== 本地状态追踪（避免闭包陈旧） =====
  const lastSentContentRef = useRef<string>("");

  // ===== 自动恢复上次活跃任务 =====
  const initialLoadDoneRef = useRef(false);
  useEffect(() => {
    if (initialLoadDoneRef.current) return;

    if (historyQuery.data && historyQuery.data.length > 0 && !activeTaskId) {
      const savedTaskId = localStorage.getItem("activeTaskId");
      const target = savedTaskId
        ? historyQuery.data.find((t: Task) => t.id === savedTaskId)
        : historyQuery.data[0];

      if (target) {
        handleSelectTask(target);
        // 如果任务状态是 running 且不在 runningTaskIds 中，尝试重连 WebSocket
        if (target.status === "running" && !useChatStore.getState().runningTaskIds.includes(target.id)) {
          setComposerState(target.id, "connecting");
          addRunningTask(target.id);
        }
      }
      initialLoadDoneRef.current = true;
    } else if (historyQuery.data && historyQuery.data.length === 0) {
      initialLoadDoneRef.current = true;
    }
  }, [historyQuery.data]);

  // ===== 操作 =====

  /** 发送消息 */
  const handleSend = useCallback(
    async (content: string) => {
      let taskId = activeTaskId;
      lastSentContentRef.current = content;

      // 没有活跃任务时自动创建
      if (!taskId) {
        taskId = crypto.randomUUID();
        const title =
          content.length > 30 ? content.slice(0, 30) + "..." : content;
        const newTask: Task = {
          id: taskId,
          title,
          date: new Date().toISOString().slice(0, 10),
          status: "running",
          messages: [],
        };
        addTask(newTask);
        setActiveTask(taskId);
        switchToTask(taskId);

        // 更新标题
        try {
          await api.renameTask(taskId, title);
        } catch {
          // 后端可能尚未保存此任务，忽略
        }
      } else if (activeTask?.title === "新建任务") {
        const newTitle =
          content.length > 30 ? content.slice(0, 30) + "..." : content;
        try {
          await api.renameTask(taskId, newTitle);
        } catch {
          // 忽略
        }
        updateTask(taskId, { title: newTitle });
      }

      // 追加用户消息
      const userMsg: Message = {
        id: nextId(),
        role: "user",
        content,
      };

      appendMessage(taskId, userMsg);

      // 占位消息（后端连接提示）
      const isCrawl = await isCrawlTask(content);
      const placeholderMsg: Message = {
        id: nextId(),
        role: "agent",
        content: isCrawl ? "正在连接后端..." : "正在思考中...",
        isStreaming: true,
      };
      appendMessage(taskId, placeholderMsg);

      // 确保当前视图切换到该任务
      switchToTask(taskId);

      try {
        // ⚡ 先发请求再等结果，利用 API 延迟期间建立 WS
        const chatPromise = api.createChat(content, taskId);

        // 立即建立 WebSocket 连接，减少等待时间
        setComposerState(taskId, "connecting");
        addRunningTask(taskId);

        const res = await chatPromise;
        const { task_id } = res;

        // 仅当仍处于 connecting 状态时才切换到 streaming
        // 防止 API 延迟返回时覆盖 WebSocket onClose 已设置的状态
        const currentState = useChatStore.getState().composerStateMap[taskId];
        if (currentState === "connecting") {
          setComposerState(taskId, "streaming");
        }
      } catch (err) {
        const errorMsg: Message = {
          id: nextId(),
          role: "agent",
          content: `无法连接后端服务：${err instanceof Error ? err.message : "未知错误"}。`,
        };
        useChatStore.getState().replaceMessages(taskId, [
          ...(useChatStore.getState().taskMessages[taskId]?.filter(
            (m) => m.id !== placeholderMsg.id
          ) || []),
          errorMsg,
        ]);
        setComposerState(taskId, "completed");
      }
    },
    [activeTaskId, activeTask]
  );

  /** 停止生成 */
  const handleStop = useCallback(() => {
    stopStream();
  }, [stopStream]);

  /** 重新生成 */
  const handleRegenerate = useCallback(() => {
    if (!activeTaskId) return;
    const msgs = useChatStore.getState().taskMessages[activeTaskId] || [];
    const lastUserIdx = [...msgs].reverse().findIndex((m) => m.role === "user");
    if (lastUserIdx === -1) return;

    const idx = msgs.length - 1 - lastUserIdx;
    const lastUserMsg = msgs[idx];

    // 删除此消息之后的所有消息
    const trimmedMsgs = msgs.slice(0, idx);
    useChatStore.getState().replaceMessages(activeTaskId, trimmedMsgs);
    useChatStore.getState().setCurrentMessages(trimmedMsgs);

    // 重新发送
    lastSentContentRef.current = lastUserMsg.content;

    const userMsg: Message = {
      id: nextId(),
      role: "user",
      content: lastUserMsg.content,
    };

    appendMessage(activeTaskId, userMsg);
    setComposerState(activeTaskId, "connecting");
    addRunningTask(activeTaskId);

    api.createChat(lastUserMsg.content, activeTaskId).then((res) => {
      const { task_id } = res as { task_id: string };
      const currentState = useChatStore.getState().composerStateMap[activeTaskId];
      if (currentState === "connecting") {
        setComposerState(activeTaskId, "streaming");
      }
    }).catch((err) => {
      const errorMsg: Message = {
        id: nextId(),
        role: "agent",
        content: `无法连接后端服务：${err instanceof Error ? err.message : "未知错误"}。`,
      };
      appendMessage(activeTaskId, errorMsg);
      setComposerState(activeTaskId, "completed");
    });
  }, [activeTaskId]);

  /** 选择任务 */
  const handleSelectTask = useCallback(
    (task: Task) => {
      setActiveTask(task.id);
      switchToTask(task.id, task.messages);
      // 如果有缓存消息，直接切换
      const cached = useChatStore.getState().taskMessages[task.id];
      if (cached && cached.length > 0) {
        switchToTask(task.id, cached);
      }
    },
    [setActiveTask, switchToTask]
  );

  /** 新建任务 */
  const handleNewTask = useCallback(() => {
    const taskId = crypto.randomUUID();
    const newTask: Task = {
      id: taskId,
      title: "新建任务",
      date: new Date().toISOString().slice(0, 10),
      status: "running",
      messages: [],
    };
    addTask(newTask);
    setActiveTask(taskId);
    switchToTask(taskId);
    setCurrentMessages([welcomeMessage]);
  }, [addTask, setActiveTask, switchToTask, setCurrentMessages]);

  /** 复制消息 */
  const handleCopyMessage = useCallback(async (content: string) => {
    await navigator.clipboard.writeText(content);
  }, []);

  /** 编辑消息 */
  const handleEditMessage = useCallback(
    (messageId: string, content: string) => {
      useUIStore.getState().setEditTarget({ messageId, content });
    },
    []
  );

  /** 编辑保存 */
  const handleEditSave = useCallback(
    (newContent: string) => {
      const editTarget = useUIStore.getState().editTarget;
      if (!editTarget || !activeTaskId) return;

      const msg = useChatStore
        .getState()
        .taskMessages[activeTaskId]
        ?.find((m) => m.id === editTarget.messageId);

      if (msg && msg.role === "user") {
        // 更新消息
        useChatStore
          .getState()
          .updateMessage(activeTaskId, editTarget.messageId, {
            content: newContent,
          });

        // 删除该消息之后的内容
        const msgs = useChatStore.getState().taskMessages[activeTaskId] || [];
        const idx = msgs.findIndex((m) => m.id === editTarget.messageId);
        if (idx !== -1) {
          const trimmedMsgs = msgs.slice(0, idx + 1);
          useChatStore.getState().replaceMessages(activeTaskId, trimmedMsgs);
          useChatStore.getState().setCurrentMessages(trimmedMsgs);
        }

        // 重新发送
        handleSend(newContent);
      }

      useUIStore.getState().setEditTarget(null);
    },
    [activeTaskId, handleSend]
  );

  /** 删除消息 */
  const handleDeleteMessage = useCallback(
    (messageId: string) => {
      if (!activeTaskId) return;
      const msgs = useChatStore.getState().taskMessages[activeTaskId] || [];
      const filtered = msgs.filter((m) => m.id !== messageId);
      useChatStore.getState().replaceMessages(activeTaskId, filtered);
      useChatStore.getState().setCurrentMessages(filtered);
    },
    [activeTaskId]
  );

  /** 搜索 */
  const handleSearch = useCallback(
    async (query: string) => {
      setSearchQuery(query);
      if (!query.trim()) {
        historyQuery.refetch();
        return;
      }
      try {
        const data = await api.searchTasks(query) as { tasks?: any[] };
        const results = (data.tasks || []).map(
          (t) => ({ ...t, status: t.status || "completed" } as Task)
        );
        useTaskStore.getState().setTasks(results);
      } catch {
        // ignore
      }
    },
    [setSearchQuery]
  );

  const renameTask = useRenameTask();
  const pinTask = usePinTask();
  const deleteTask = useDeleteTask();

  return {
    // 状态
    tasks,
    activeTask,
    activeTaskId,
    messages: currentMessages,
    composerState,
    isRunning,

    // TanStack Query 状态
    isLoading: historyQuery.isLoading,
    isError: historyQuery.isError,

    // 操作
    send: handleSend,
    stop: handleStop,
    regenerate: handleRegenerate,
    selectTask: handleSelectTask,
    newTask: handleNewTask,
    copyMessage: handleCopyMessage,
    editMessage: handleEditMessage,
    editSave: handleEditSave,
    deleteMessage: handleDeleteMessage,
    search: handleSearch,
    renameTask: (taskId: string, title: string) =>
      renameTask.mutate({ taskId, title }),
    pinTask: (taskId: string) => pinTask.mutate(taskId),
    deleteTask: (taskId: string) => deleteTask.mutate(taskId),
  };
}
