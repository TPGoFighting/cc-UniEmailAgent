"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/api";
import { useChatStore } from "@/stores/chat-store";
import { useEffect } from "react";
import type { Message } from "@/lib/types";

function normalizeMessages(rawMessages: unknown[]): Message[] {
  const seenIds = new Set<string>();
  return rawMessages.map((raw: unknown, idx: number) => {
    const m = raw as Record<string, unknown>;
    let mid = (m.id as string) || `h-${idx}`;
    if (seenIds.has(mid)) {
      mid = `${mid}-${idx}`;
    }
    seenIds.add(mid);
    // 历史中 role 为 "agent" 但后端发送的 type "text" 历史存储为 role "text"
    // 需要映射为前端显示需要的角色
    const rawRole = (m.role as string) || "log";
    const role = rawRole === "text" ? "agent" : rawRole;
    return {
      ...m,
      id: mid,
      role,
      content: m.content || "",
    } as Message;
  });
}

export function useTaskMessages(taskId: string | null) {
  const cacheMessages = useChatStore((s) => s.cacheMessages);
  const switchToTask = useChatStore((s) => s.switchToTask);

  const query = useQuery({
    queryKey: ["messages", taskId],
    queryFn: async () => {
      if (!taskId) return [];
      const data = await api.getTaskMessages(taskId) as { messages?: unknown[]; task?: { messages?: unknown[] } };
      const rawMessages =
        data.messages || (data.task as { messages?: unknown[] })?.messages || [];
      return normalizeMessages(rawMessages);
    },
    enabled: !!taskId,
    staleTime: 60_000,
    retry: 1,
  });

  // 同步到 Zustand store
  useEffect(() => {
    if (query.data && taskId) {
      cacheMessages(taskId, query.data);
      switchToTask(taskId, query.data);
    }
  }, [query.data, taskId, cacheMessages, switchToTask]);

  return query;
}
