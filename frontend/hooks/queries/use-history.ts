"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/api";
import { useTaskStore } from "@/stores/task-store";
import { useEffect } from "react";
import type { Task } from "@/lib/types";

export function useHistory() {
  const setTasks = useTaskStore((s) => s.setTasks);

  const query = useQuery({
    queryKey: ["history"],
    queryFn: async () => {
      const data = await api.getHistory() as { tasks?: any[] };
      return (data.tasks || []).map(
        (t) =>
          ({
            ...t,
            status: t.status || "completed",
            messages: t.messages || [],
          }) as Task
      );
    },
    staleTime: 30_000,
    retry: 1,
  });

  // 同步到 Zustand store
  useEffect(() => {
    if (query.data) {
      setTasks(query.data);
    }
  }, [query.data, setTasks]);

  return query;
}
