"use client";

import { useState, useMemo } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ThemeToggle } from "@/components/theme-toggle";
import { SearchBar } from "@/components/search-bar";
import { SidebarTaskItem } from "@/components/sidebar-task-item";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { useTaskStore } from "@/stores/task-store";
import { useChatStore } from "@/stores/chat-store";
import { useUIStore } from "@/stores/ui-store";
import { useAgentChat } from "@/hooks/use-agent-chat";
import type { Task } from "@/lib/types";

type FilterKey = "all" | "running" | "hasData" | "failed";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "running", label: "运行中" },
  { key: "hasData", label: "有数据" },
  { key: "failed", label: "失败" },
];

/** 判断任务属于哪个时间段 */
function timeGroup(dateStr: string): string {
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return "更早";
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);

  const taskDate = new Date(d.getFullYear(), d.getMonth(), d.getDate());

  if (taskDate.getTime() >= today.getTime()) return "今天";
  if (taskDate.getTime() >= yesterday.getTime()) return "昨天";
  if (taskDate.getTime() >= weekAgo.getTime()) return "本周";
  return "更早";
}

/** 检查任务是否有数据产出 */
function taskHasData(task: Task): boolean {
  if (task.status !== "completed") return false;
  if (!task.messages) return false;
  return task.messages.some((m) => m.role === "download");
}

const GROUP_LABELS: Record<string, string> = {
  "今天": "今天",
  "昨天": "昨天",
  "本周": "本周",
  "更早": "更早",
};

export function Sidebar() {
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<FilterKey>("all");

  const tasks = useTaskStore((s) => s.tasks);
  const activeTaskId = useTaskStore((s) => s.activeTaskId);
  const runningTaskIds = useChatStore((s) => s.runningTaskIds);
  const searchQuery = useUIStore((s) => s.searchQuery);
  const setUniversityOpen = useUIStore((s) => s.setUniversityOpen);

  const {
    selectTask,
    newTask,
    renameTask,
    pinTask,
    deleteTask,
    search,
  } = useAgentChat({ streaming: false });

  // 搜索 + 筛选
  const filteredTasks = useMemo(() => {
    let result = tasks;

    // 搜索过滤
    if (searchQuery) {
      result = result.filter((t) =>
        t.title.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }

    // 筛选
    switch (activeFilter) {
      case "running":
        result = result.filter((t) => runningTaskIds.includes(t.id) || t.status === "running");
        break;
      case "hasData":
        result = result.filter((t) => taskHasData(t));
        break;
      case "failed":
        result = result.filter((t) => t.status === "failed" || t.status === "stopped");
        break;
    }

    return result;
  }, [tasks, searchQuery, activeFilter, runningTaskIds]);

  // 按时间分组
  const groupedTasks = useMemo(() => {
    const groups: Record<string, Task[]> = { "今天": [], "昨天": [], "本周": [], "更早": [] };
    for (const t of filteredTasks) {
      const g = timeGroup(t.date);
      groups[g].push(t);
    }
    // 只保留有内容的分组，按顺序排列
    return (["今天", "昨天", "本周", "更早"] as const).filter((k) => groups[k].length > 0).map((k) => ({
      label: GROUP_LABELS[k],
      tasks: groups[k],
    }));
  }, [filteredTasks]);

  const handleJumpToUniversity = (name: string) => {
    // 设置高校库打开并高亮指定大学
    useUIStore.getState().setHighlightUniversity?.(name);
    setUniversityOpen(true);
  };

  const handleDelete = () => {
    if (deleteTarget) {
      deleteTask(deleteTarget);
      setDeleteTarget(null);
    }
  };

  return (
    <aside className="flex h-full flex-col bg-sidebar bg-sidebar-glow">
      {/* Logo */}
      <div className="flex items-center px-5 py-5">
        <img src="/logo.png" alt="UniEmail Agent" className="h-10 object-contain img-blend" />
      </div>

      {/* 新建任务 */}
      <div className="px-4 pb-2">
        <Button
          variant="ghost"
          className="w-full justify-start gap-2.5 rounded-xl text-sm font-medium text-muted-foreground transition-all duration-250 hover:-translate-y-[0.5px] hover:bg-primary/10 hover:text-primary"
          onClick={newTask}
          style={{ transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)" }}
        >
          <Plus className="size-4" />
          新建任务
        </Button>
      </div>

      {/* 搜索 */}
      <SearchBar onSearch={search} />

      {/* 分隔 */}
      <div className="mx-4 border-t border-border/40" />

      {/* 任务列表 */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="px-2 py-2">
          {groupedTasks.length === 0 ? (
            <p className="px-5 py-6 text-xs text-muted-foreground/40">暂无任务</p>
          ) : (
            groupedTasks.map((group) => (
              <div key={group.label} className="mb-2">
                <p className="mb-1 px-5 py-1.5 text-[11px] font-medium tracking-wider text-muted-foreground/40 uppercase">
                  {group.label}
                </p>
                {group.tasks.map((task) => (
                  <SidebarTaskItem
                    key={task.id}
                    task={task}
                    isActive={activeTaskId === task.id}
                    isRunning={runningTaskIds.includes(task.id)}
                    onSelect={() => selectTask(task)}
                    onRename={(title) => renameTask(task.id, title)}
                    onDelete={() => setDeleteTarget(task.id)}
                  />
                ))}
              </div>
            ))
          )}
        </div>
      </ScrollArea>

      {/* 底部 */}
      <div className="flex items-center justify-center border-t border-border/40 px-4 py-3">
        <ThemeToggle />
      </div>

      {/* 删除确认 */}
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(o) => { if (!o) setDeleteTarget(null); }}
        title="删除对话"
        description="删除后无法恢复，确定要删除这个对话吗？"
        variant="destructive"
        confirmLabel="删除"
        onConfirm={handleDelete}
      />
    </aside>
  );
}
