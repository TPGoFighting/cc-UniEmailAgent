"use client";

import { useChatStore } from "@/stores/chat-store";

/**
 * Agent 实时活动指示器
 *
 * 展示 DirectorAgent 的 Reflection-Before-Action 状态：
 * 🧠 思考中 → 🔧 执行工具 → ✅ 工具完成
 *
 * 参考 PageAgent 的 Activity Event 系统设计
 */
export function AgentActivityIndicator() {
  const activity = useChatStore((s) => s.currentActivity);

  if (!activity) return null;

  if (activity.type === "thinking") {
    return (
      <div className="flex items-center gap-2 px-4 py-2 text-sm text-muted-foreground">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
        </span>
        <span>Agent 思考中...</span>
      </div>
    );
  }

  if (activity.type === "executing" && activity.tool) {
    const inputSummary = activity.input
      ? Object.entries(activity.input)
          .map(([k, v]) => `${k}=${String(v).slice(0, 30)}`)
          .join(", ")
      : "";

    return (
      <div className="flex items-center gap-2 px-4 py-2 text-sm">
        <span className="text-amber-500">🔧</span>
        <span className="font-medium text-foreground">{activity.tool}</span>
        {inputSummary && (
          <span className="text-muted-foreground truncate max-w-[300px]">
            {inputSummary}
          </span>
        )}
        {activity.reflection?.next_goal && (
          <span className="text-muted-foreground text-xs italic truncate max-w-[200px]">
            🎯 {activity.reflection.next_goal.slice(0, 60)}
          </span>
        )}
      </div>
    );
  }

  if (activity.type === "executed" && activity.tool) {
    return (
      <div className="flex items-center gap-2 px-4 py-2 text-sm text-muted-foreground">
        <span className="text-emerald-500">✅</span>
        <span className="font-medium">{activity.tool}</span>
        {activity.summary && (
          <span className="truncate max-w-[400px]">{activity.summary.slice(0, 80)}</span>
        )}
      </div>
    );
  }

  return null;
}
