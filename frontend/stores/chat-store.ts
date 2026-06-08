import { create } from "zustand";
import type { Message, ComposerState, IntentResult, StageState, CollegeStage, TaskSummary, CrawlStageState, CrawlStatsData, CrawlSummaryData, ErrorUserData, QualityEvalData } from "@/lib/types";

interface ChatStore {
  /** 当前视图显示的消息 */
  currentMessages: Message[];
  /** 用户当前正在查看的任务 ID */
  viewingTaskId: string | null;
  /** 按 taskId 缓存的所有消息 */
  taskMessages: Record<string, Message[]>;
  /** 正在运行的任务 ID 列表 */
  runningTaskIds: string[];
  /** 按 taskId 存储的 composer 状态 */
  composerStateMap: Record<string, ComposerState>;
  /** 按 taskId 存储的意图分类结果 */
  intentMap: Record<string, IntentResult>;
  /** 按 taskId 存储的爬取阶段状态 */
  stageMap: Record<string, StageState>;
  /** 按 taskId 存储的任务完成摘要 */
  summaryMap: Record<string, TaskSummary>;
  /** 撤销队列：[{taskId, message}]，用于恢复被删除的消息 */
  undoQueue: Array<{ taskId: string; message: Message }>;
  /** Phase 2: 按 taskId 存储的爬取 5 阶段状态 */
  crawlStageMap: Record<string, CrawlStageState>;
  /** Phase 2: 按 taskId 存储的实时统计数据 */
  crawlStatsMap: Record<string, CrawlStatsData>;
  /** Phase 2: 按 taskId 存储的爬取完成摘要 */
  crawlSummaryMap: Record<string, CrawlSummaryData>;
  /** Phase 2: 按 taskId 存储的用户友好错误列表 */
  crawlErrorsMap: Record<string, ErrorUserData[]>;
  /** 按 taskId 存储的质量评估数据 */
  qualityEvalMap: Record<string, QualityEvalData>;
  /** 按 taskId 存储的 LangSmith trace URL */
  traceUrlMap: Record<string, string>;
  /** 按 taskId 存储的实时调试日志行（保留最后 500 条） */
  logsMap: Record<string, string[]>;

  /** 设置当前视图消息 */
  setCurrentMessages: (messages: Message[]) => void;
  /** 缓存某个任务的消息 */
  cacheMessages: (taskId: string, messages: Message[]) => void;
  /** 追加消息到指定任务（如该任务是当前视图，同步更新 currentMessages） */
  appendMessage: (taskId: string, msg: Message) => void;
  /** 更新指定任务中的某条消息 */
  updateMessage: (taskId: string, msgId: string, patch: Partial<Message>) => void;
  /** 替换指定任务的整个消息列表 */
  replaceMessages: (taskId: string, messages: Message[]) => void;
  /** 添加运行中任务 */
  addRunningTask: (taskId: string) => void;
  /** 移除运行中任务 */
  removeRunningTask: (taskId: string) => void;
  /** 设置某个任务的 composer 状态 */
  setComposerState: (taskId: string, state: ComposerState) => void;
  /** 设置某个任务的意图 */
  setIntent: (taskId: string, intent: IntentResult) => void;
  /** 设置某任务阶段状态 */
  initStages: (taskId: string, colleges: string[]) => void;
  updateCollegeStage: (taskId: string, college: string, patch: Partial<CollegeStage>) => void;
  /** 设置任务完成摘要 */
  setSummary: (taskId: string, summary: TaskSummary) => void;
  /** 将消息推入撤销队列 */
  pushUndo: (taskId: string, message: Message) => void;
  /** 从撤销队列弹出最近的消息（用于恢复） */
  popUndo: () => { taskId: string; message: Message } | null;
  /** 清空撤销队列 */
  clearUndoQueue: () => void;
  /** 切换到指定任务的消息（更新 currentMessages + viewingTaskId） */
  switchToTask: (taskId: string, messages?: Message[]) => void;
  /** 清除某个任务的消息缓存 + composer 状态 */
  clearTaskData: (taskId: string) => void;
  /** Phase 2: 设置爬取 5 阶段状态 */
  setCrawlStage: (taskId: string, stage: CrawlStageState) => void;
  /** Phase 2: 设置实时统计数据 */
  setCrawlStats: (taskId: string, stats: CrawlStatsData) => void;
  /** Phase 2: 设置爬取完成摘要 */
  setCrawlSummary: (taskId: string, summary: CrawlSummaryData) => void;
  /** Phase 2: 追加用户友好错误 */
  appendCrawlError: (taskId: string, error: ErrorUserData) => void;
  /** 设置质量评估数据 */
  setQualityEval: (taskId: string, evalData: QualityEvalData) => void;
  /** 设置 LangSmith trace URL */
  setTraceUrl: (taskId: string, url: string) => void;
  /** 追加一条实时调试日志（保留最后 500 行） */
  addLog: (taskId: string, line: string) => void;
  /** 清空某个任务的日志 */
  clearLogs: (taskId: string) => void;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  currentMessages: [],
  viewingTaskId: null,
  taskMessages: {},
  runningTaskIds: [],
  composerStateMap: {},
  intentMap: {},
  stageMap: {},
  summaryMap: {},
  undoQueue: [],
  crawlStageMap: {},
  crawlStatsMap: {},
  crawlSummaryMap: {},
  crawlErrorsMap: {},
  qualityEvalMap: {},
  traceUrlMap: {},
  logsMap: {},

  setCurrentMessages: (messages) => set({ currentMessages: messages }),

  cacheMessages: (taskId, messages) =>
    set((s) => ({
      taskMessages: { ...s.taskMessages, [taskId]: messages },
    })),

  appendMessage: (taskId, msg) =>
    set((s) => {
      const updatedTaskMsgs = [...(s.taskMessages[taskId] || []), msg];
      return {
        taskMessages: { ...s.taskMessages, [taskId]: updatedTaskMsgs },
        // 如果当前查看的正是这个任务，同步更新 currentMessages
        currentMessages:
          s.viewingTaskId === taskId
            ? [...(s.currentMessages.length > 0 ? s.currentMessages : []), msg]
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

  setIntent: (taskId, intent) =>
    set((s) => ({
      intentMap: { ...s.intentMap, [taskId]: intent },
    })),

  initStages: (taskId, colleges) =>
    set((s) => ({
      stageMap: {
        ...s.stageMap,
        [taskId]: {
          colleges: colleges.map((name, i) => ({
            name,
            status: i === 0 ? "active" as const : "pending" as const,
          })),
        },
      },
    })),

  updateCollegeStage: (taskId, college, patch) =>
    set((s) => {
      const current = s.stageMap[taskId];
      if (!current) return {};
      const colleges = current.colleges.map((c) =>
        c.name === college ? { ...c, ...patch } : c
      );
      return { stageMap: { ...s.stageMap, [taskId]: { colleges } } };
    }),

  setSummary: (taskId, summary) =>
    set((s) => ({
      summaryMap: { ...s.summaryMap, [taskId]: summary },
    })),

  pushUndo: (taskId, message) =>
    set((s) => ({
      undoQueue: [...s.undoQueue, { taskId, message }],
    })),

  popUndo: () => {
    const queue = get().undoQueue;
    if (queue.length === 0) return null;
    const last = queue[queue.length - 1];
    set((s) => ({ undoQueue: s.undoQueue.slice(0, -1) }));
    return last;
  },

  clearUndoQueue: () => set({ undoQueue: [] }),

  switchToTask: (taskId, messages) =>
    set((s) => {
      const msgs = messages || s.taskMessages[taskId] || [];
      return {
        viewingTaskId: taskId,
        currentMessages: [...msgs],
      };
    }),

  clearTaskData: (taskId) =>
    set((s) => {
      const { [taskId]: removed, ...restMsgs } = s.taskMessages;
      const { [taskId]: removedState, ...restStates } = s.composerStateMap;
      const { [taskId]: removedIntent, ...restIntents } = s.intentMap;
      const { [taskId]: removedStage, ...restStages } = s.stageMap;
      const { [taskId]: removedSummary, ...restSummaries } = s.summaryMap;
      const { [taskId]: removedCrawlStage, ...restCrawlStages } = s.crawlStageMap;
      const { [taskId]: removedCrawlStats, ...restCrawlStats } = s.crawlStatsMap;
      const { [taskId]: removedCrawlSummary, ...restCrawlSummaries } = s.crawlSummaryMap;
      const { [taskId]: removedCrawlErrors, ...restCrawlErrors } = s.crawlErrorsMap;
      const { [taskId]: removedQualityEval, ...restQualityEvals } = s.qualityEvalMap;
      const { [taskId]: removedTraceUrl, ...restTraceUrls } = s.traceUrlMap;
      const { [taskId]: removedLogs, ...restLogs } = s.logsMap;
      return {
        taskMessages: restMsgs,
        composerStateMap: restStates,
        intentMap: restIntents,
        stageMap: restStages,
        summaryMap: restSummaries,
        crawlStageMap: restCrawlStages,
        crawlStatsMap: restCrawlStats,
        crawlSummaryMap: restCrawlSummaries,
        crawlErrorsMap: restCrawlErrors,
        qualityEvalMap: restQualityEvals,
        traceUrlMap: restTraceUrls,
        logsMap: restLogs,
        runningTaskIds: s.runningTaskIds.filter((id) => id !== taskId),
        viewingTaskId: s.viewingTaskId === taskId ? null : s.viewingTaskId,
        currentMessages:
          s.viewingTaskId === taskId ? [] : s.currentMessages,
      };
    }),

  // Phase 2: Store methods for new WS message types
  setCrawlStage: (taskId, stage) =>
    set((s) => ({
      crawlStageMap: { ...s.crawlStageMap, [taskId]: stage },
    })),

  setCrawlStats: (taskId, stats) =>
    set((s) => ({
      crawlStatsMap: { ...s.crawlStatsMap, [taskId]: stats },
    })),

  setCrawlSummary: (taskId, summary) =>
    set((s) => ({
      crawlSummaryMap: { ...s.crawlSummaryMap, [taskId]: summary },
    })),

  appendCrawlError: (taskId, error) =>
    set((s) => {
      const existing = s.crawlErrorsMap[taskId] || [];
      return {
        crawlErrorsMap: {
          ...s.crawlErrorsMap,
          [taskId]: [...existing, error],
        },
      };
    }),

  setQualityEval: (taskId, evalData) =>
    set((s) => ({
      qualityEvalMap: { ...s.qualityEvalMap, [taskId]: evalData },
    })),

  setTraceUrl: (taskId, url) =>
    set((s) => ({
      traceUrlMap: { ...s.traceUrlMap, [taskId]: url },
    })),

  addLog: (taskId, line) =>
    set((s) => {
      const existing = s.logsMap[taskId] || [];
      // 保留最后 500 行，避免内存溢出
      const updated = [...existing, line].slice(-500);
      return { logsMap: { ...s.logsMap, [taskId]: updated } };
    }),

  clearLogs: (taskId) =>
    set((s) => {
      const { [taskId]: _, ...rest } = s.logsMap;
      return { logsMap: rest };
    }),
}));
