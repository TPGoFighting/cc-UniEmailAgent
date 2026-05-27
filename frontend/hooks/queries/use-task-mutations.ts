"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/services/api";
import { useTaskStore } from "@/stores/task-store";
import { useChatStore } from "@/stores/chat-store";

/** 重命名任务 */
export function useRenameTask() {
  const queryClient = useQueryClient();
  const updateTask = useTaskStore((s) => s.updateTask);

  return useMutation({
    mutationFn: ({ taskId, title }: { taskId: string; title: string }) =>
      api.renameTask(taskId, title),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["history"] });
    },
    // 乐观更新：先更新本地状态
    onMutate: ({ taskId, title }) => {
      updateTask(taskId, { title });
    },
  });
}

/** 切换置顶 */
export function usePinTask() {
  const queryClient = useQueryClient();
  const updateTask = useTaskStore((s) => s.updateTask);

  return useMutation({
    mutationFn: (taskId: string) => api.pinTask(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["history"] });
    },
    onMutate: (taskId) => {
      // 乐观更新会由 useTaskStore 处理
    },
  });
}

/** 删除任务 */
export function useDeleteTask() {
  const queryClient = useQueryClient();
  const removeTask = useTaskStore((s) => s.removeTask);
  const clearTaskData = useChatStore((s) => s.clearTaskData);

  return useMutation({
    mutationFn: (taskId: string) => api.deleteTask(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["history"] });
    },
    onMutate: (taskId) => {
      removeTask(taskId);
      clearTaskData(taskId);
    },
  });
}
