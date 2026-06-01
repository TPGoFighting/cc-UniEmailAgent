"use client";

import { useState } from "react";
import { Plus, MessageSquare } from "lucide-react";
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

export function Sidebar() {
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const tasks = useTaskStore((s) => s.tasks);
  const activeTaskId = useTaskStore((s) => s.activeTaskId);
  const runningTaskIds = useChatStore((s) => s.runningTaskIds);
  const searchQuery = useUIStore((s) => s.searchQuery);

  const {
    selectTask,
    newTask,
    renameTask,
    pinTask,
    deleteTask,
    search,
  } = useAgentChat({ streaming: false });

  // 搜索过滤
  const filteredTasks = searchQuery
    ? tasks.filter((t) =>
        t.title.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : tasks;

  const pinnedTasks = filteredTasks.filter((t) => t.pinned);
  const recentTasks = filteredTasks.filter((t) => !t.pinned);

  const handleDelete = () => {
    if (deleteTarget) {
      deleteTask(deleteTarget);
      setDeleteTarget(null);
    }
  };

  return (
    <aside className="flex h-full flex-col bg-[#F7F7F8] dark:bg-[#202123]">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-4">
        <img 
          src="/logo.png" 
          alt="UniEmail Agent" 
          className="h-16 max-w-[180px] object-contain mix-blend-multiply dark:mix-blend-normal dark:invert" 
        />
      </div>

      {/* 新建任务 */}
      <div className="px-3 pb-2">
        <Button
          variant="ghost"
          className="w-full justify-start gap-2 rounded-[24px] text-sm font-normal text-muted-foreground transition-all duration-250 hover:-translate-y-[1px] hover:text-foreground"
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
      <div className="mx-3 border-t" style={{ borderColor: "rgba(0,0,0,0.04)" }} />

      {/* 任务列表 */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="px-2 py-2">
          {/* Pinned */}
          {pinnedTasks.length > 0 && (
            <div className="mb-2">
              <p className="mb-1 px-3 py-1.5 text-xs font-medium text-muted-foreground/60">
                已置顶
              </p>
              {pinnedTasks.map((task) => (
                <SidebarTaskItem
                  key={task.id}
                  task={task}
                  isActive={activeTaskId === task.id}
                  isRunning={runningTaskIds.includes(task.id)}
                  onSelect={() => selectTask(task)}
                  onRename={(title) => renameTask(task.id, title)}
                  onPin={() => pinTask(task.id)}
                  onDelete={() => setDeleteTarget(task.id)}
                />
              ))}
              <div className="mx-3 mb-1 mt-1 border-t" style={{ borderColor: "rgba(0,0,0,0.03)" }} />
            </div>
          )}

          {/* Recent */}
          <div>
            <p className="mb-1 px-3 py-1.5 text-xs font-medium text-muted-foreground/60">
              {pinnedTasks.length > 0 ? "最近" : "历史任务"}
            </p>
            {recentTasks.length === 0 ? (
              <p className="px-3 py-4 text-xs text-muted-foreground/60">
                暂无历史任务
              </p>
            ) : (
              recentTasks.map((task) => (
                <SidebarTaskItem
                  key={task.id}
                  task={task}
                  isActive={activeTaskId === task.id}
                  isRunning={runningTaskIds.includes(task.id)}
                  onSelect={() => selectTask(task)}
                  onRename={(title) => renameTask(task.id, title)}
                  onPin={() => pinTask(task.id)}
                  onDelete={() => setDeleteTarget(task.id)}
                />
              ))
            )}
          </div>
        </div>
      </ScrollArea>

      {/* 底部 */}
      <div className="flex items-center justify-between border-t px-4 py-3" style={{ borderColor: "rgba(0,0,0,0.04)" }}>
        <span className="text-xs text-[#9A9AA5] dark:text-[#6E6E80]">深色模式</span>
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
