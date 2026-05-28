"use client";

import { useEffect, useRef, useCallback } from "react";
import { getWsManager } from "@/services/websocket";
import { api } from "@/services/api";
import { useChatStore } from "@/stores/chat-store";
import type { ComposerState } from "@/lib/types";

function isCrawlTask(message: string): boolean {
  const keywords = [
    "抓取", "爬取", "爬虫", "邮箱", "教师",
    "crawl", "scrape", "email", "faculty", "teacher", "学院",
  ];
  const lower = message.toLowerCase();
  const hits = keywords.filter(kw => lower.includes(kw)).length;
  const combos = ["教师邮箱", "crawl email", "scrape email"];
  if (combos.some(c => lower.includes(c))) {
    return true;
  }
  return hits >= 2;
}

interface UseTaskStreamOptions {
  taskId: string | null;
  initialComposerState?: ComposerState;
  enabled?: boolean;
  onFinish?: (taskId: string) => void;
  onError?: (taskId: string, message: string) => void;
}

export function useTaskStream({ taskId, enabled = false, onFinish, onError }: UseTaskStreamOptions) {
  const connectionEstablishedRef = useRef(false);
  const stoppedRef = useRef(false);
  const hadErrorRef = useRef(false);
  const doneRef = useRef(false);
  const prevTaskIdRef = useRef<string | null>(null);
  const appendMessage = useChatStore((s) => s.appendMessage);
  const setComposerState = useChatStore((s) => s.setComposerState);
  const removeRunningTask = useChatStore((s) => s.removeRunningTask);

  if (prevTaskIdRef.current !== taskId) {
    prevTaskIdRef.current = taskId;
    connectionEstablishedRef.current = false;
    stoppedRef.current = false;
    hadErrorRef.current = false;
    doneRef.current = false;
  }
  if (!enabled) {
    connectionEstablishedRef.current = false;
  }

  useEffect(() => {
    if (!taskId || !enabled) return;
    if (connectionEstablishedRef.current) return;
    connectionEstablishedRef.current = true;

    const manager = getWsManager();
    const wsUrl = api.getWsUrl(taskId);
    let firstMessageReceived = false;

    const msgsList = useChatStore.getState().taskMessages[taskId || ""] || [];
    const userMsg = [...msgsList].reverse().find((m) => m.role === "user");
    const isCrawl = userMsg ? isCrawlTask(userMsg.content) : true;

    manager.connect(taskId, wsUrl, {
      onLog: (msg, timestamp) => {
        if (!isCrawl) {
          // 非爬取任务：直接流式追加到占位消息中，避免显示“收到任务...”
          const currentMsgs = useChatStore.getState().taskMessages[taskId] || [];
          const agentMsg = [...currentMsgs].reverse().find((m) => m.role === "agent");
          if (agentMsg) {
            const isPlaceholder = agentMsg.content === "正在思考中..." || agentMsg.content === "正在连接后端...";
            const newContent = isPlaceholder ? msg : agentMsg.content + msg;
            useChatStore.getState().updateMessage(taskId, agentMsg.id, {
              content: newContent,
            });
            return;
          }
        }
        // 爬取任务或兜底：正常记录日志
        appendMessage(taskId, {
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          role: "log",
          content: msg,
          timestamp,
        });
      },
      onProgress: (msg, step, total, timestamp) => {
        firstMessageReceived = true;
        appendMessage(taskId, {
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          role: "progress",
          content: msg,
          step,
          total,
          timestamp,
        });
      },
      onDownload: (msg, filename, url, timestamp) => {
        firstMessageReceived = true;
        appendMessage(taskId, {
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          role: "download",
          content: msg,
          filename,
          url,
          timestamp,
        });
      },
      onDone: (message) => {
        doneRef.current = true;
        firstMessageReceived = true;

        if (!isCrawl) {
          // 非爬取任务：直接把占位消息设为完成状态即可，无需重复追加消息
          const currentMsgs = useChatStore.getState().taskMessages[taskId] || [];
          const agentMsg = [...currentMsgs].reverse().find((m) => m.role === "agent");
          if (agentMsg) {
            useChatStore.getState().updateMessage(taskId, agentMsg.id, {
              isStreaming: false,
              content: message || agentMsg.content,
            });
            return;
          }
        } else {
          // 爬取任务：删除“收到任务，正在为你执行：...”的占位消息，保持历史整洁
          const currentMsgs = useChatStore.getState().taskMessages[taskId] || [];
          const filtered = currentMsgs.filter(m => !m.content.startsWith("收到任务，正在为你执行"));
          useChatStore.getState().replaceMessages(taskId, filtered);
        }

        appendMessage(taskId, {
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          role: "agent",
          content: message || "## 任务完成\n\n任务已执行完毕。",
        });
      },
      onError: (msg) => {
        hadErrorRef.current = true;
        firstMessageReceived = true;

        if (!isCrawl) {
          // 非爬取任务：直接把占位消息替换为错误信息，避免冗余
          const currentMsgs = useChatStore.getState().taskMessages[taskId] || [];
          const agentMsg = [...currentMsgs].reverse().find((m) => m.role === "agent");
          if (agentMsg) {
            useChatStore.getState().updateMessage(taskId, agentMsg.id, {
              isStreaming: false,
              content: `执行出错：${msg}`,
            });
            onError?.(taskId, msg);
            return;
          }
        }

        appendMessage(taskId, {
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          role: "agent",
          content: `执行出错：${msg}`,
        });
        onError?.(taskId, msg);
      },
      onClose: () => {
        if (stoppedRef.current) {
          setComposerState(taskId, "stopped");
          removeRunningTask(taskId);
          onFinish?.(taskId);
        } else if (hadErrorRef.current) {
          setComposerState(taskId, "error");
          removeRunningTask(taskId);
        } else if (doneRef.current) {
          setComposerState(taskId, "completed");
          removeRunningTask(taskId);
          if (firstMessageReceived) onFinish?.(taskId);
        } else {
          setComposerState(taskId, "completed");
          removeRunningTask(taskId);
          if (firstMessageReceived) onFinish?.(taskId);
        }
      },
    });

    return () => {
      manager.disconnect();
      connectionEstablishedRef.current = false;
    };
  }, [taskId, enabled, appendMessage, onError, onFinish, removeRunningTask, setComposerState]);

  const stop = useCallback(() => {
    if (!taskId) return;
    stoppedRef.current = true;
    setComposerState(taskId, "stopped");
    removeRunningTask(taskId);
    getWsManager().disconnect();
    onFinish?.(taskId);
  }, [taskId, setComposerState, removeRunningTask, onFinish]);

  return { stop };
}
