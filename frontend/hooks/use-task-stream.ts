"use client";

import { useEffect, useRef, useCallback } from "react";
import { getWsManager } from "@/services/websocket";
import { api } from "@/services/api";
import { useChatStore } from "@/stores/chat-store";
import { isCrawlTask } from "@/services/classify";
import type { ComposerState } from "@/lib/types";

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

  // 用 ref 稳定化回调，避免 effect 依赖数组变动导致重连
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
    let firstMessageReceived = false;

    const msgsList = store().taskMessages[taskId || ""] || [];
    const firstUserMsg = msgsList.find((m) => m.role === "user");
    const isCrawlRef = { value: false };
    if (firstUserMsg) {
      isCrawlTask(firstUserMsg.content).then(r => { isCrawlRef.value = r; });
    }

    manager.connect(taskId, wsUrl, {
      onLog: (msg, timestamp) => {
        if (!isCrawlRef.value) {
          const currentMsgs = store().taskMessages[taskId] || [];
          const agentMsg = [...currentMsgs].reverse().find((m) => m.role === "agent");
          if (agentMsg) {
            const isPlaceholder = agentMsg.content === "正在思考中..." || agentMsg.content === "正在连接后端...";
            const newContent = isPlaceholder ? msg : agentMsg.content + msg;
            store().updateMessage(taskId, agentMsg.id, { content: newContent });
            return;
          }
        }
        store().appendMessage(taskId, {
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          role: "log",
          content: msg,
          timestamp,
        });
      },
      onText: (msg, timestamp) => {
        firstMessageReceived = true;
        const currentMsgs = store().taskMessages[taskId] || [];
        // 找到最后一个 agent 消息
        const lastAgent = [...currentMsgs].reverse().find((m) => m.role === "agent");
        const isPlaceholder = lastAgent && (
          lastAgent.content === "正在连接后端..." ||
          lastAgent.content === "正在思考中..." ||
          lastAgent.content === ""
        );
        if (isPlaceholder) {
          // 第一个 chunk：替换占位符
          store().updateMessage(taskId, lastAgent!.id, { content: msg, isStreaming: true });
        } else if (lastAgent && lastAgent.isStreaming) {
          // 流式后续 chunk：追加到同一条消息
          store().updateMessage(taskId, lastAgent.id, {
            content: lastAgent.content + msg,
            isStreaming: true,
          });
        } else {
          store().appendMessage(taskId, {
            id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            role: "agent",
            content: msg,
            timestamp,
          });
        }
      },
      onProgress: (msg, step, total, timestamp) => {
        firstMessageReceived = true;
        store().appendMessage(taskId, {
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
        store().appendMessage(taskId, {
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          role: "download",
          content: msg,
          filename,
          url,
          timestamp,
        });
      },
      onFile: (msg, filename, filepath, timestamp) => {
        firstMessageReceived = true;
        store().appendMessage(taskId, {
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          role: "file",
          content: msg,
          filename,
          filepath,
          timestamp,
        });
      },
      onDone: (message) => {
        doneRef.current = true;
        firstMessageReceived = true;

        if (!isCrawlRef.value) {
          const currentMsgs = store().taskMessages[taskId] || [];
          const agentMsg = [...currentMsgs].reverse().find((m) => m.role === "agent");
          if (agentMsg) {
            // 只设置 isStreaming=false，不覆盖真实回复内容
            // done 消息通常只用于标记结束，不为空时不覆盖已有内容
            store().updateMessage(taskId, agentMsg.id, {
              isStreaming: false,
            });
            return;
          }
        } else {
          const currentMsgs = store().taskMessages[taskId] || [];
          const filtered = currentMsgs.filter(m => !m.content.startsWith("收到任务，正在为你执行"));
          store().replaceMessages(taskId, filtered);
        }

        store().appendMessage(taskId, {
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          role: "agent",
          content: message || "## 任务完成\n\n任务已执行完毕。",
        });
      },
      onError: (msg) => {
        hadErrorRef.current = true;
        firstMessageReceived = true;

        if (!isCrawlRef.value) {
          const currentMsgs = store().taskMessages[taskId] || [];
          const agentMsg = [...currentMsgs].reverse().find((m) => m.role === "agent");
          if (agentMsg) {
            store().updateMessage(taskId, agentMsg.id, {
              isStreaming: false,
              content: `执行出错：${msg}`,
            });
            onErrorRef.current?.(taskId, msg);
            return;
          }
        }

        store().appendMessage(taskId, {
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          role: "agent",
          content: `执行出错：${msg}`,
        });
        onErrorRef.current?.(taskId, msg);
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
          if (firstMessageReceived) onFinishRef.current?.(taskId);
        } else {
          if (!firstMessageReceived) {
            setComposerState(taskId, "connecting");
          } else {
            setComposerState(taskId, "completed");
            removeRunningTask(taskId);
            if (firstMessageReceived) onFinishRef.current?.(taskId);
          }
        }
      },
    });

    return () => {
      manager.disconnect();
      connectionEstablishedRef.current = false;
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
