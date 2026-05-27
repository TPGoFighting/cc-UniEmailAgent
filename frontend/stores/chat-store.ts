import { create } from "zustand";
import type { Message, ComposerState } from "@/lib/types";

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
  /** 切换到指定任务的消息（更新 currentMessages + viewingTaskId） */
  switchToTask: (taskId: string, messages?: Message[]) => void;
  /** 清除某个任务的消息缓存 + composer 状态 */
  clearTaskData: (taskId: string) => void;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  currentMessages: [],
  viewingTaskId: null,
  taskMessages: {},
  runningTaskIds: [],
  composerStateMap: {},

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
      return {
        taskMessages: restMsgs,
        composerStateMap: restStates,
        runningTaskIds: s.runningTaskIds.filter((id) => id !== taskId),
        viewingTaskId: s.viewingTaskId === taskId ? null : s.viewingTaskId,
        currentMessages:
          s.viewingTaskId === taskId ? [] : s.currentMessages,
      };
    }),
}));
