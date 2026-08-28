"use client";

import { useEffect, useRef, useCallback } from "react";
import { getWsManager } from "@/services/websocket";
import { api } from "@/services/api";
import { useChatStore } from "@/stores/chat-store";
import type { ComposerState } from "@/lib/types";

/** 桌面通知（仅在 document.hidden 时发送） */
function notify(title: string, body: string) {
  if (typeof window === "undefined" || !("Notification" in window)) return;
  if (Notification.permission !== "granted") return;
  if (!document.hidden) return;
  try {
    new Notification(title, { body, icon: "/logo.png" });
  } catch {
    // ignore
  }
}

interface UseTaskStreamOptions {
  taskId: string | null;
  initialComposerState?: ComposerState;
  enabled?: boolean;
  onFinish?: (taskId: string) => void;
  onError?: (taskId: string, message: string) => void;
}

let msgCounter = 0;
function nextId(): string {
  msgCounter += 1;
  return `msg-${Date.now()}-${msgCounter}`;
}

export function useTaskStream({
  taskId,
  enabled = false,
  onFinish,
  onError,
}: UseTaskStreamOptions) {
  const connectionEstablishedRef = useRef(false);
  const stoppedRef = useRef(false);
  const hadErrorRef = useRef(false);
  const doneRef = useRef(false);
  const prevTaskIdRef = useRef<string | null>(null);

  const onFinishRef = useRef(onFinish);
  onFinishRef.current = onFinish;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

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

    const store = () => useChatStore.getState();
    const manager = getWsManager();
    const wsUrl = api.getWsUrl(taskId);

    manager.connect(taskId, wsUrl, {
      onLog: (msg, timestamp) => {
        store().appendMessage(taskId, {
          id: nextId(),
          role: "log",
          content: msg,
          timestamp,
        });
        store().addLog(taskId, `[${timestamp || new Date().toISOString().slice(11, 19)}] ${msg}`);
      },

      onText: (msg, timestamp) => {
        const msgs = store().taskMessages[taskId] || [];
        const lastAgent = [...msgs].reverse().find((m) => m.role === "agent");

        if (!lastAgent) {
          // 第一条 agent 消息
          store().appendMessage(taskId, {
            id: nextId(),
            role: "agent",
            content: msg,
            timestamp,
            isStreaming: true,
          });
        } else if (lastAgent.isStreaming) {
          // 流式追加
          store().updateMessage(taskId, lastAgent.id, {
            content: lastAgent.content + msg,
            isStreaming: true,
          });
        } else {
          // 非流式新消息
          store().appendMessage(taskId, {
            id: nextId(),
            role: "agent",
            content: msg,
            timestamp,
          });
        }
      },

      onDownload: (msg, filename, url, timestamp) => {
        store().appendMessage(taskId, {
          id: nextId(),
          role: "download",
          content: msg,
          filename,
          url,
          timestamp,
        });
      },

      onDone: (message) => {
        doneRef.current = true;

        const msgs = store().taskMessages[taskId] || [];
        const lastAgent = [...msgs].reverse().find((m) => m.role === "agent");

        if (lastAgent) {
          if (lastAgent.isStreaming) {
            // 流式结束：用 done 消息替换或标记结束
            store().updateMessage(taskId, lastAgent.id, {
              content: message || lastAgent.content,
              isStreaming: false,
            });
          }
          // 非流式消息不需要处理
        } else if (message) {
          // 无 agent 消息但有 done 内容
          store().appendMessage(taskId, {
            id: nextId(),
            role: "agent",
            content: message,
          });
        }

        // 获取任务摘要（含爬取统计）
        api.getTaskSummary(taskId).then((summary) => {
          // 如果有 colleges 数据，构造成并行爬取状态
          if (summary.colleges && summary.colleges.length > 0) {
            store().setParallelCrawl(taskId, {
              university: "",
              total_workers: summary.colleges.length,
              workers: summary.colleges.map((c) => ({
                name: c.name,
                status: "done" as const,
                found: c.count,
              })),
              started_at: new Date().toISOString(),
            });
          }
        }).catch(() => { /* 非爬取任务可能没有 summary */ });

        const userMsg = msgs.find((m) => m.role === "user");
        notify("任务完成", (userMsg?.content || "").slice(0, 50));
      },

      onError: (msg) => {
        hadErrorRef.current = true;
        store().appendMessage(taskId, {
          id: nextId(),
          role: "agent",
          content: `执行出错：${msg}`,
        });
        onErrorRef.current?.(taskId, msg);
        notify("任务失败", msg.slice(0, 60));
      },

      onActivity: (activity) => {
        store().setCurrentActivity(activity);
        // 记录到日志
        if (activity.type === "thinking") {
          store().addLog(taskId, `🧠 Agent 思考中...`);
        } else if (activity.type === "executing" && activity.tool) {
          const input = activity.input ? JSON.stringify(activity.input).slice(0, 80) : "";
          store().addLog(taskId, `🔧 执行: ${activity.tool} ${input}`);
        } else if (activity.type === "executed" && activity.tool) {
          store().addLog(taskId, `✅ ${activity.tool}: ${(activity.summary || "").slice(0, 100)}`);
        }
      },

      onWorkerProgress: (progress) => {
        const existing = store().parallelCrawlMap[taskId];
        if (!existing) {
          // 首次收到 worker_progress，初始化并行爬取状态
          store().setParallelCrawl(taskId, {
            university: "",
            total_workers: 1,
            workers: [progress],
            started_at: new Date().toISOString(),
          });
        } else {
          store().updateWorkerProgress(taskId, progress.name, progress);
        }
        store().addLog(taskId, `👷 Worker「${progress.name}」${progress.status === "done" ? "✅ 完成" : progress.status === "error" ? "❌ 失败" : progress.status}`);
      },

      onClose: () => {
        const setComposerState = store().setComposerState;
        const removeRunningTask = store().removeRunningTask;

        if (stoppedRef.current) {
          setComposerState(taskId, "stopped");
          removeRunningTask(taskId);
          onFinishRef.current?.(taskId);
        } else if (hadErrorRef.current) {
          setComposerState(taskId, "error");
          removeRunningTask(taskId);
        } else if (doneRef.current) {
          setComposerState(taskId, "completed");
          removeRunningTask(taskId);
          onFinishRef.current?.(taskId);
        } else {
          setComposerState(taskId, "connecting");
        }
      },
    });

    return () => {
      // cleanup: don't disconnect here — let the next connect() or explicit stop handle it
    };
  }, [taskId, enabled]);

  const stop = useCallback(() => {
    if (!taskId) return;
    stoppedRef.current = true;
    const store = useChatStore.getState();
    store.setComposerState(taskId, "stopped");
    store.removeRunningTask(taskId);
    getWsManager().disconnect();
  }, [taskId]);

  return { stop };
}
