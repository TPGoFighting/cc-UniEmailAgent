"use client";

import { useEffect, useRef, useCallback } from "react";
import { getWsManager } from "@/services/websocket";
import { api } from "@/services/api";
import { useChatStore } from "@/stores/chat-store";
import { isCrawlTask } from "@/services/classify";
import type { ComposerState, CollegeStage } from "@/lib/types";

/** 占位符消息集合（与 onText、onDone 三处共用） */
const PLACEHOLDER_PATTERNS = [
  "正在连接后端…准备爬取任务",
  "正在连接后端…准备增量补充",
  "正在连接后端...",
  "正在分析数据…",
  "正在思考中...",
  "",
];

/** 桌面通知（仅在 document.hidden 时发送） */
function notify(title: string, body: string) {
  if (typeof window === "undefined" || !("Notification" in window)) return;
  if (Notification.permission !== "granted") return;
  if (!document.hidden) return;
  try {
    new Notification(title, { body, icon: "/logo.png" });
  } catch {
    // 忽略通知失败
  }
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
    // 从 store 同步读取意图分类结果（由 use-agent-chat.ts 在发起请求前写入），避免异步竞态
    const intentResult = store().intentMap[taskId || ""];
    const isCrawlRef = { value: intentResult?.is_crawl ?? false };

    manager.connect(taskId, wsUrl, {
      stageHandlers: {
        onStageStart: (stage, college, collegeIndex, collegeTotal) => {
          const currentStage = store().stageMap[taskId];
          if (!currentStage) {
            // 首次收到阶段事件，初始化所有学院为 pending
            const colleges = Array.from({ length: collegeTotal }, (_, i) => ({
              name: i === collegeIndex - 1 ? college : "加载中...",
              status: (i === collegeIndex - 1 ? "active" : "pending") as CollegeStage["status"],
            }));
            store().initStages(taskId, colleges.map((c) => c.name));
          }
          store().updateCollegeStage(taskId, college, { status: "active" });
        },
        onStageProgress: (stage, phase, found, extracted, totalPages) => {
          const s = store().stageMap[taskId];
          if (!s) return;
          const active = s.colleges.find((c) => c.status === "active");
          if (active) {
            store().updateCollegeStage(taskId, active.name, {
              found: found ?? active.found,
              extracted: extracted ?? active.extracted,
              total_pages: totalPages ?? active.total_pages,
            });
          }
        },
        onStageDone: (stage, college, found, validEmail, elapsedMs) => {
          store().updateCollegeStage(taskId, college, {
            status: "done",
            found,
            valid_email: validEmail,
            elapsed_ms: elapsedMs,
          });
          // 更新 college name（以防初始化时是占位名）
          store().updateCollegeStage(taskId, college, { name: college });
        },
      },
      // Phase 2: New WS event handlers
      onCrawlStage: (stageNum, stageName, progressPct, timestamp) => {
        store().setCrawlStage(taskId, { stage: stageNum, stage_name: stageName, progress_pct: progressPct, timestamp });
      },
      onCrawlStats: (teachersFound, emailsExtracted, departmentsDone, departmentNames, timestamp) => {
        store().setCrawlStats(taskId, { teachers_found: teachersFound, emails_extracted: emailsExtracted, departments_done: departmentsDone, department_names: departmentNames, timestamp });
      },
      onCrawlSummary: (university, totalTeachers, totalEmails, duration, files, timestamp) => {
        store().setCrawlSummary(taskId, { university, total_teachers: totalTeachers, total_emails: totalEmails, duration, files, timestamp });
      },
      onErrorUser: (message, severity, timestamp) => {
        store().appendCrawlError(taskId, { message, severity, timestamp });
      },
      onEval: (evalData) => {
        try {
          store().setQualityEval(taskId, evalData);
        } catch {
          // 静默兜底
        }
      },
      onTrace: (traceUrl) => {
        try {
          store().setTraceUrl(taskId, traceUrl);
        } catch {
          // 静默兜底
        }
      },
      onLog: (msg, timestamp) => {
        // 同时写入消息列表（历史持久化）和实时日志面板
        store().appendMessage(taskId, {
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          role: "log",
          content: msg,
          timestamp,
        });
        store().addLog(taskId, `[${timestamp || new Date().toISOString().slice(11, 19)}] ${msg}`);
      },
      onText: (msg, timestamp) => {
        firstMessageReceived = true;
        const currentMsgs = store().taskMessages[taskId] || [];
        // 找到最后一个 agent 消息
        const lastAgent = [...currentMsgs].reverse().find((m) => m.role === "agent");
        // 占位符检测：匹配 use-agent-chat.ts 中定义的所有占位消息
        const isPlaceholder = lastAgent && PLACEHOLDER_PATTERNS.includes(lastAgent.content);
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

        // === 判断此任务是否为爬虫任务 ===
        // 优先使用 intentMap 同步结果；落地检查 store 中的爬虫专用数据作为后备
        const isDefinitelyCrawl = isCrawlRef.value ||
          !!store().crawlStageMap[taskId] ||
          !!store().crawlStatsMap[taskId];

        if (!isDefinitelyCrawl) {
          const currentMsgs = store().taskMessages[taskId] || [];
          const agentMsg = [...currentMsgs].reverse().find((m) => m.role === "agent");
          if (agentMsg) {
            const isPlaceholder = PLACEHOLDER_PATTERNS.includes(agentMsg.content);

            if (isPlaceholder && message) {
              // 占位符还在 → 用 done 消息内容替换
              store().updateMessage(taskId, agentMsg.id, {
                content: message,
                isStreaming: false,
              });
            } else if (isPlaceholder && !message) {
              // 占位符还在，但没有 done 消息 → 设一个默认提示
              store().updateMessage(taskId, agentMsg.id, {
                content: "## 任务完成\n\n任务已执行完毕。",
                isStreaming: false,
              });
            } else {
              // agent 已经有真实内容 → 仅标记结束
              store().updateMessage(taskId, agentMsg.id, {
                isStreaming: false,
              });
            }
            return;
          }
        } else {
          const currentMsgs = store().taskMessages[taskId] || [];
          const filtered = currentMsgs.filter(m => !m.content.startsWith("收到任务，正在为你执行"));
          store().replaceMessages(taskId, filtered);

          // 爬取分支：检查是否已有 onText 流式写入的真实 agent 消息
          const lastAgent = [...filtered].reverse().find((m) => m.role === "agent");
          if (lastAgent) {
            const isPlaceholder = PLACEHOLDER_PATTERNS.includes(lastAgent.content);
            if (isPlaceholder && message) {
              // 占位符还在 → 用 done 消息内容替换
              store().updateMessage(taskId, lastAgent.id, {
                content: message,
                isStreaming: false,
              });
            } else if (isPlaceholder && !message) {
              store().updateMessage(taskId, lastAgent.id, {
                content: "## 任务完成\n\n任务已执行完毕。",
                isStreaming: false,
              });
            } else {
              // agent 已经有真实内容 → 仅标记结束
              store().updateMessage(taskId, lastAgent.id, {
                isStreaming: false,
              });
            }
          } else {
            // 没有任何 agent 消息 → 追加 done 消息
            store().appendMessage(taskId, {
              id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
              role: "agent",
              content: message || "## 任务完成\n\n任务已执行完毕。",
            });
          }
        }

        // 爬取任务完成后获取摘要数据
        if (isCrawlRef.value) {
          api.getTaskSummary(taskId).then(summary => {
            store().setSummary(taskId, summary);
          }).catch(() => {});
        }

        // 桌面通知
        const taskTitle = store().taskMessages[taskId]?.find(m => m.role === "user")?.content || "任务";
        notify("任务完成", taskTitle.slice(0, 50));
      },
      onError: (msg) => {
        hadErrorRef.current = true;
        firstMessageReceived = true;

        // isDefinitelyCrawl 判断（同 onDone）
        const isDefinitelyCrawl = isCrawlRef.value ||
          !!store().crawlStageMap[taskId] ||
          !!store().crawlStatsMap[taskId];

        if (!isDefinitelyCrawl) {
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

        // 桌面通知
        const errorTitle = store().taskMessages[taskId]?.find(m => m.role === "user")?.content || "任务";
        notify("任务失败", `${errorTitle.slice(0, 40)}: ${msg.slice(0, 60)}`);
      },
      onClose: () => {
        const setComposerState = store().setComposerState;
        const removeRunningTask = store().removeRunningTask;

        if (stoppedRef.current) {
          manager.disconnect();
          setComposerState(taskId, "stopped");
          removeRunningTask(taskId);
          onFinishRef.current?.(taskId);
        } else if (hadErrorRef.current) {
          manager.disconnect();
          setComposerState(taskId, "error");
          removeRunningTask(taskId);
        } else if (doneRef.current) {
          manager.disconnect();
          setComposerState(taskId, "completed");
          removeRunningTask(taskId);
          if (firstMessageReceived) onFinishRef.current?.(taskId);
        } else {
          manager.disconnect();
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
