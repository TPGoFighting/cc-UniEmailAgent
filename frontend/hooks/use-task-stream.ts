"use client";

import { useEffect, useRef, useCallback } from "react";
import { getWsManager } from "@/services/websocket";
import { api } from "@/services/api";
import { useChatStore } from "@/stores/chat-store";
import type { ComposerState } from "@/lib/types";

interface UseTaskStreamOptions {
  taskId: string | null;
  initialComposerState?: ComposerState;
  enabled?: boolean;
  onFinish?: (taskId: string) => void;
  onError?: (taskId: string, message: string) => void;
}

let _streamConnected = false;

export function useTaskStream({ taskId, enabled = false, onFinish, onError }: UseTaskStreamOptions) {
  const connectionEstablishedRef = useRef(false);
  const stoppedRef = useRef(false);
  const prevTaskIdRef = useRef<string | null>(null);
  const appendMessage = useChatStore((s) => s.appendMessage);
  const setComposerState = useChatStore((s) => s.setComposerState);
  const removeRunningTask = useChatStore((s) => s.removeRunningTask);

  if (prevTaskIdRef.current !== taskId) {
    prevTaskIdRef.current = taskId;
    connectionEstablishedRef.current = false;
    stoppedRef.current = false;
  }
  if (!enabled) {
    connectionEstablishedRef.current = false;
  }

  useEffect(() => {
    if (!taskId || !enabled) return;
    if (_streamConnected || connectionEstablishedRef.current) return;
    connectionEstablishedRef.current = true;
    _streamConnected = true;

    const manager = getWsManager();
    const wsUrl = api.getWsUrl(taskId);
    let firstMessageReceived = false;

    manager.connect(taskId, wsUrl, {
      onLog: () => {},
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
        firstMessageReceived = true;
        appendMessage(taskId, {
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          role: "agent",
          content: message || "## 任务完成\n\n任务已执行完毕。",
        });
      },
      onError: (msg) => {
        firstMessageReceived = true;
        appendMessage(taskId, {
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          role: "agent",
          content: `执行出错：${msg}`,
        });
        onError?.(taskId, msg);
      },
      onClose: () => {
        _streamConnected = false;
        if (stoppedRef.current) {
          setComposerState(taskId, "stopped");
          removeRunningTask(taskId);
          onFinish?.(taskId);
        } else {
          setComposerState(taskId, "completed");
          removeRunningTask(taskId);
          if (firstMessageReceived) onFinish?.(taskId);
        }
      },
    });

    return () => {
      _streamConnected = false;
      manager.disconnect();
    };
  }, [taskId, enabled, appendMessage, onError, onFinish, removeRunningTask, setComposerState]);

  const stop = useCallback(() => {
    if (!taskId) return;
    stoppedRef.current = true;
    _streamConnected = false;
    setComposerState(taskId, "stopped");
    removeRunningTask(taskId);
    getWsManager().disconnect();
    onFinish?.(taskId);
  }, [taskId, setComposerState, removeRunningTask, onFinish]);

  return { stop };
}
