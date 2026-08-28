import { create } from "zustand";
import { persist } from "zustand/middleware";
import type {
  Message,
  ComposerState,
  ParallelCrawlState,
  AgentActivity,
} from "@/lib/types";

interface ChatStore {
  /** 当前视图显示的消息 */
  currentMessages: Message[];
  /** 用户当前正在查看的任务 ID */
  viewingTaskId: string | null;
  /** 按 taskId 缓存的消息 */
  taskMessages: Record<string, Message[]>;
  /** 运行中的任务 ID */
  runningTaskIds: string[];
  /** 按 taskId 的 composer 状态 */
  composerStateMap: Record<string, ComposerState>;
  /** 按 taskId 的并行爬取进度 */
  parallelCrawlMap: Record<string, ParallelCrawlState>;
  /** 按 taskId 的实时日志行（保留最后 500 行） */
  logsMap: Record<string, string[]>;
  /** 当前 Agent 活动状态（非持久化，实时更新） */
  currentActivity: AgentActivity | null;

  setCurrentMessages: (messages: Message[]) => void;
  cacheMessages: (taskId: string, messages: Message[]) => void;
  appendMessage: (taskId: string, msg: Message) => void;
  updateMessage: (taskId: string, msgId: string, patch: Partial<Message>) => void;
  replaceMessages: (taskId: string, messages: Message[]) => void;
  addRunningTask: (taskId: string) => void;
  removeRunningTask: (taskId: string) => void;
  setComposerState: (taskId: string, state: ComposerState) => void;
  switchToTask: (taskId: string, messages?: Message[]) => void;
  clearTaskData: (taskId: string) => void;
  setParallelCrawl: (taskId: string, state: ParallelCrawlState) => void;
  updateWorkerProgress: (taskId: string, name: string, patch: Partial<{ status: "pending" | "running" | "done" | "error"; found: number; emails: number; error: string }>) => void;
  addLog: (taskId: string, line: string) => void;
  clearLogs: (taskId: string) => void;
  /** 设置当前 Agent 活动状态 */
  setCurrentActivity: (activity: AgentActivity | null) => void;
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      currentMessages: [],
      viewingTaskId: null,
      taskMessages: {},
      runningTaskIds: [],
      composerStateMap: {},
      parallelCrawlMap: {},
      logsMap: {},
      currentActivity: null,

      setCurrentMessages: (messages) => set({ currentMessages: messages }),

      cacheMessages: (taskId, messages) =>
        set((s) => ({
          taskMessages: { ...s.taskMessages, [taskId]: messages },
        })),

      appendMessage: (taskId, msg) =>
        set((s) => {
          const updated = [...(s.taskMessages[taskId] || []), msg];
          return {
            taskMessages: { ...s.taskMessages, [taskId]: updated },
            currentMessages:
              s.viewingTaskId === taskId
                ? [...s.currentMessages, msg]
                : s.currentMessages,
          };
        }),

      updateMessage: (taskId, msgId, patch) =>
        set((s) => {
          const updateFn = (msgs: Message[]) =>
            msgs.map((m) => (m.id === msgId ? { ...m, ...patch } : m));
          return {
            taskMessages: {
              ...s.taskMessages,
              [taskId]: updateFn(s.taskMessages[taskId] || []),
            },
            currentMessages:
              s.viewingTaskId === taskId
                ? updateFn(s.currentMessages)
                : s.currentMessages,
          };
        }),

      replaceMessages: (taskId, messages) =>
        set((s) => ({
          taskMessages: { ...s.taskMessages, [taskId]: messages },
          currentMessages:
            s.viewingTaskId === taskId ? messages : s.currentMessages,
        })),

      addRunningTask: (taskId) =>
        set((s) => ({
          runningTaskIds: s.runningTaskIds.includes(taskId)
            ? s.runningTaskIds
            : [...s.runningTaskIds, taskId],
        })),

      removeRunningTask: (taskId) =>
        set((s) => ({
          runningTaskIds: s.runningTaskIds.filter((id) => id !== taskId),
        })),

      setComposerState: (taskId, state) =>
        set((s) => ({
          composerStateMap: { ...s.composerStateMap, [taskId]: state },
        })),

      switchToTask: (taskId, messages) =>
        set((s) => {
          const msgs = messages || s.taskMessages[taskId] || [];
          return { viewingTaskId: taskId, currentMessages: [...msgs] };
        }),

      clearTaskData: (taskId) =>
        set((s) => {
          const { [taskId]: _, ...restMsgs } = s.taskMessages;
          const { [taskId]: __, ...restStates } = s.composerStateMap;
          const { [taskId]: ___, ...restCrawl } = s.parallelCrawlMap;
          const { [taskId]: ____, ...restLogs } = s.logsMap;
          return {
            taskMessages: restMsgs,
            composerStateMap: restStates,
            parallelCrawlMap: restCrawl,
            logsMap: restLogs,
            runningTaskIds: s.runningTaskIds.filter((id) => id !== taskId),
            viewingTaskId: s.viewingTaskId === taskId ? null : s.viewingTaskId,
            currentMessages: s.viewingTaskId === taskId ? [] : s.currentMessages,
          };
        }),

      setParallelCrawl: (taskId, state) =>
        set((s) => ({
          parallelCrawlMap: { ...s.parallelCrawlMap, [taskId]: state },
        })),

      updateWorkerProgress: (taskId, name, patch) =>
        set((s) => {
          const existing = s.parallelCrawlMap[taskId];
          if (!existing) return {};
          const workers = existing.workers.map((w) =>
            w.name === name ? { ...w, ...patch } : w
          );
          return {
            parallelCrawlMap: {
              ...s.parallelCrawlMap,
              [taskId]: { ...existing, workers },
            },
          };
        }),

      addLog: (taskId, line) =>
        set((s) => {
          const existing = s.logsMap[taskId] || [];
          const updated = [...existing, line].slice(-500);
          return { logsMap: { ...s.logsMap, [taskId]: updated } };
        }),

      clearLogs: (taskId) =>
        set((s) => {
          const { [taskId]: _, ...rest } = s.logsMap;
          return { logsMap: rest };
        }),

      setCurrentActivity: (activity) => set({ currentActivity: activity }),
    }),
    {
      name: "uniemail-chat",
      partialize: (state) => ({
        taskMessages: state.taskMessages,
        runningTaskIds: state.runningTaskIds,
        composerStateMap: state.composerStateMap,
        parallelCrawlMap: state.parallelCrawlMap,
        logsMap: state.logsMap,
      }),
    }
  )
);
