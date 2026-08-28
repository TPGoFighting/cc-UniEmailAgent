"use client";

import { useCallback, useEffect, useRef } from "react";
import { useTaskStore } from "@/stores/task-store";
import { useChatStore } from "@/stores/chat-store";
import { useUIStore } from "@/stores/ui-store";
import { api } from "@/services/api";
import { getWsManager } from "@/services/websocket";
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
  streaming?: boolean;
} = {}) {
  // ===== Stores =====
  const { tasks, activeTaskId, setActiveTask, getActiveTask, addTask, updateTask } =
    useTaskStore();

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
  const composerState = activeTaskId
    ? composerStateMap[activeTaskId] || "idle"
    : "idle";
  const isRunning = activeTaskId ? runningTaskIds.includes(activeTaskId) : false;

  // ===== TanStack Query =====
  const historyQuery = useHistory();
  const messagesQuery = useTaskMessages(
    activeTaskId && !useChatStore.getState().taskMessages[activeTaskId]
      ? activeTaskId
      : null
  );

  // ===== WebSocket Stream =====
  const streamEnabled =
    streaming &&
    (composerState === "connecting" || composerState === "streaming" || isRunning);

  const { stop: stopStream } = useTaskStream({
    taskId: activeTaskId,
    enabled: streamEnabled,
  });

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
        if (
          target.status === "running" &&
          !useChatStore.getState().runningTaskIds.includes(target.id)
        ) {
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

  const handleSend = useCallback(
    async (content: string) => {
      let taskId = activeTaskId;
      lastSentContentRef.current = content;

      // 新建任务
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

        try {
          await api.renameTask(taskId, title);
        } catch {
          // ignore
        }
      } else if (activeTask?.title === "新建任务") {
        const newTitle =
          content.length > 30 ? content.slice(0, 30) + "..." : content;
        try {
          await api.renameTask(taskId, newTitle);
        } catch {
          // ignore
        }
        updateTask(taskId, { title: newTitle });
      }

      // 追加用户消息
      appendMessage(taskId, {
        id: nextId(),
        role: "user",
        content,
      });

      // 占位消息
      appendMessage(taskId, {
        id: nextId(),
        role: "agent",
        content: "正在处理您的请求...",
        isStreaming: true,
      });

      switchToTask(taskId);

      try {
        const chatPromise = api.createChat(content, taskId);
        setComposerState(taskId, "connecting");
        addRunningTask(taskId);

        const res = await chatPromise;
        const currentState = useChatStore.getState().composerStateMap[taskId];
        if (currentState === "connecting") {
          setComposerState(taskId, "streaming");
        }
      } catch (err) {
        useChatStore.getState().replaceMessages(taskId, [
          ...(useChatStore.getState().taskMessages[taskId]?.filter(
            (m) => m.role !== "agent" || !m.isStreaming
          ) || []),
          {
            id: nextId(),
            role: "agent",
            content: `无法连接后端服务：${err instanceof Error ? err.message : "未知错误"}。`,
          },
        ]);
        setComposerState(taskId, "completed");
      }
    },
    [activeTaskId, activeTask]
  );

  const handleStop = useCallback(() => {
    stopStream();
  }, [stopStream]);

  const handleRegenerate = useCallback(() => {
    if (!activeTaskId) return;
    const msgs = useChatStore.getState().taskMessages[activeTaskId] || [];
    const lastUserIdx = [...msgs].reverse().findIndex((m) => m.role === "user");
    if (lastUserIdx === -1) return;

    const idx = msgs.length - 1 - lastUserIdx;
    const lastUserMsg = msgs[idx];

    getWsManager().disconnect();
    api.terminateAgent(activeTaskId).catch(() => {});

    const trimmedMsgs = msgs.slice(0, idx);
    useChatStore.getState().replaceMessages(activeTaskId, trimmedMsgs);
    useChatStore.getState().setCurrentMessages(trimmedMsgs);

    lastSentContentRef.current = lastUserMsg.content;

    appendMessage(activeTaskId, {
      id: nextId(),
      role: "user",
      content: lastUserMsg.content,
    });
    setComposerState(activeTaskId, "connecting");
    addRunningTask(activeTaskId);

    api
      .createChat(lastUserMsg.content, activeTaskId)
      .then(() => {
        const currentState =
          useChatStore.getState().composerStateMap[activeTaskId];
        if (currentState === "connecting") {
          setComposerState(activeTaskId, "streaming");
        }
      })
      .catch((err) => {
        appendMessage(activeTaskId, {
          id: nextId(),
          role: "agent",
          content: `无法连接后端服务：${err instanceof Error ? err.message : "未知错误"}。`,
        });
        setComposerState(activeTaskId, "completed");
      });
  }, [activeTaskId]);

  const handleSelectTask = useCallback(
    (task: Task) => {
      setActiveTask(task.id);
      switchToTask(task.id, task.messages);
      const cached = useChatStore.getState().taskMessages[task.id];
      if (cached && cached.length > 0) {
        switchToTask(task.id, cached);
      }
    },
    [setActiveTask, switchToTask]
  );

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

  const handleCopyMessage = useCallback(async (content: string) => {
    await navigator.clipboard.writeText(content);
  }, []);

  const handleEditMessage = useCallback(
    (messageId: string, content: string) => {
      useUIStore.getState().setEditTarget({ messageId, content });
    },
    []
  );

  const handleEditSave = useCallback(
    (newContent: string) => {
      const editTarget = useUIStore.getState().editTarget;
      if (!editTarget || !activeTaskId) return;

      const msg = useChatStore
        .getState()
        .taskMessages[activeTaskId]
        ?.find((m) => m.id === editTarget.messageId);

      if (msg && msg.role === "user") {
        useChatStore
          .getState()
          .updateMessage(activeTaskId, editTarget.messageId, {
            content: newContent,
          });

        const msgs =
          useChatStore.getState().taskMessages[activeTaskId] || [];
        const idx = msgs.findIndex((m) => m.id === editTarget.messageId);
        if (idx !== -1) {
          const trimmedMsgs = msgs.slice(0, idx + 1);
          useChatStore.getState().replaceMessages(activeTaskId, trimmedMsgs);
          useChatStore.getState().setCurrentMessages(trimmedMsgs);
        }

        handleSend(newContent);
      }

      useUIStore.getState().setEditTarget(null);
    },
    [activeTaskId, handleSend]
  );

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

  const handleSearch = useCallback(
    async (query: string) => {
      setSearchQuery(query);
      if (!query.trim()) {
        historyQuery.refetch();
        return;
      }
      try {
        const data = (await api.getHistory()) as any;
        const results = (data.tasks || [])
          .filter(
            (t: any) =>
              (t.title || "").toLowerCase().includes(query.toLowerCase())
          )
          .map((t: any) => ({ ...t, status: t.status || "completed" } as Task));
        useTaskStore.getState().setTasks(results);
      } catch {
        // ignore
      }
    },
    [setSearchQuery, historyQuery]
  );

  const renameTaskMut = useRenameTask();
  const pinTaskMut = usePinTask();
  const deleteTaskMut = useDeleteTask();

  return {
    tasks,
    activeTask,
    activeTaskId,
    messages: currentMessages,
    composerState,
    isRunning,

    isLoading: historyQuery.isLoading,
    isError: historyQuery.isError,

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
      renameTaskMut.mutate({ taskId, title }),
    pinTask: (taskId: string) => pinTaskMut.mutate(taskId),
    deleteTask: (taskId: string) => deleteTaskMut.mutate(taskId),
  };
}
