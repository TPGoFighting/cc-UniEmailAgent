"use client";

import { useEffect, useRef, useCallback } from "react";
import { WebSocketManager } from "@/services/websocket";
import { api } from "@/services/api";
import { useChatStore } from "@/stores/chat-store";
import type { ComposerState } from "@/lib/types";

interface UseTaskStreamOptions {
  /** 要连接的任务 ID */
  taskId: string | null;
  /** 初始 composer 状态（connecting/streaming） */
  initialComposerState?: ComposerState;
  /** 是否启动流式连接 */
  enabled?: boolean;
  /** 流式完成回调 */
  onFinish?: (taskId: string) => void;
  /** 流式错误回调 */
  onError?: (taskId: string, message: string) => void;
}

/**
 * 管理单个任务的 WebSocket 流式连接
 * 自动管理连接生命周期，将 WebSocket 事件转换为 chatStore 操作
 */
export function useTaskStream({
  taskId,
  enabled = false,
  onFinish,
  onError,
}: UseTaskStreamOptions) {
  const wsManagerRef = useRef<WebSocketManager | null>(null);
  /** 本轮（taskId + 连续 enabled=true）是否已建立过连接 */
  const connectionEstablishedRef = useRef(false);
  /** 用户是否主动停止了 */
  const stoppedRef = useRef(false);
  /** 上一个 taskId，用于检测任务切换 */
  const prevTaskIdRef = useRef<string | null>(null);
  const appendMessage = useChatStore((s) => s.appendMessage);
  const updateMessage = useChatStore((s) => s.updateMessage);
  const setComposerState = useChatStore((s) => s.setComposerState);
  const removeRunningTask = useChatStore((s) => s.removeRunningTask);

  const getConnection = useCallback(() => {
    if (!wsManagerRef.current) {
      wsManagerRef.current = new WebSocketManager();
    }
    return wsManagerRef.current;
  }, []);

  // 当 taskId 变化或 enabled 变为 false 时，重置连接标记
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

    // 防止重复连接：同一个 enabled 周期内只连一次
    if (connectionEstablishedRef.current) return;
    connectionEstablishedRef.current = true;

    const manager = getConnection();
    const wsUrl = api.getWsUrl(taskId);

    let firstMessageReceived = false;

    manager.connect(taskId, wsUrl, {
      onLog: (msg, timestamp) => {
        firstMessageReceived = true;
        appendMessage(taskId, {
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          role: "log",
          content: msg,
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

      onDone: () => {
        firstMessageReceived = true;
        appendMessage(taskId, {
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          role: "agent",
          content: "## 任务完成\n\n任务已执行完毕。",
        });
      },

      onError: (msg) => {
        appendMessage(taskId, {
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          role: "agent",
          content: `执行出错：${msg}`,
        });
        onError?.(taskId, msg);
      },

      onClose: () => {
        // 正常完成或主动停止才更新状态，避免竞态覆盖
        if (firstMessageReceived || stoppedRef.current) {
          setComposerState(taskId, stoppedRef.current ? "stopped" : "completed");
          removeRunningTask(taskId);
          onFinish?.(taskId);
        }
      },
    });

    return () => {
      manager.disconnect();
    };
  }, [taskId, enabled]);

  /** 停止流式生成 */
  const stop = useCallback(() => {
    if (taskId) {
      stoppedRef.current = true;
      setComposerState(taskId, "stopped");
      removeRunningTask(taskId);
      getConnection().disconnect();
      onFinish?.(taskId);
    }
  }, [taskId, setComposerState, removeRunningTask, getConnection, onFinish]);

  return { stop };
}
