"use client";

import { useState, useMemo } from "react";
import { BookOpenText, Plus } from "lucide-react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { SearchBar } from "@/components/search-bar";
import { SidebarTaskItem } from "@/components/sidebar-task-item";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { useTaskStore } from "@/stores/task-store";
import { useChatStore } from "@/stores/chat-store";
import { useUIStore } from "@/stores/ui-store";
import { useAgentChat } from "@/hooks/use-agent-chat";
import type { Task } from "@/lib/types";

type FilterKey = "all" | "running" | "failed";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "running", label: "运行中" },
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

const GROUP_LABELS: Record<string, string> = {
  "今天": "今天",
  "昨天": "昨天",
  "本周": "本周",
  "更早": "更早",
};

export function Sidebar() {
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<FilterKey>("all");
  const [fuseResultIds, setFuseResultIds] = useState<string[] | null>(null);

  const tasks = useTaskStore((s) => s.tasks);
  const activeTaskId = useTaskStore((s) => s.activeTaskId);
  const runningTaskIds = useChatStore((s) => s.runningTaskIds);
  const searchQuery = useUIStore((s) => s.searchQuery);
  const setUniversityOpen = useUIStore((s) => s.setUniversityOpen);
  
  const activeTab = useUIStore((s) => s.activeTab);
  const setActiveTab = useUIStore((s) => s.setActiveTab);

  const {
    selectTask,
    newTask,
    renameTask,
    pinTask,
    deleteTask,
    search,
  } = useAgentChat({ streaming: false });

  // 为 fuse 准备搜索数据（含消息内容）
  const searchableTasks = useMemo(() => {
    const runningIds = runningTaskIds;
    return tasks.map((t) => ({
      id: t.id,
      title: t.title,
      content: (t.messages || [])
        .map((m) => m.content)
        .filter(Boolean)
        .join(" "),
      running: runningIds.includes(t.id),
    }));
  }, [tasks, runningTaskIds]);

  // 搜索 + 筛选
  const filteredTasks = useMemo(() => {
    let result = tasks;

    // fuse 结果过滤（仅当有 fuse 结果时使用）
    if (fuseResultIds !== null) {
      result = result.filter((t) => fuseResultIds.includes(t.id));
    } else if (searchQuery) {
      // 后备：基本字符串匹配
      result = result.filter((t) =>
        t.title.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }

    // 筛选
    switch (activeFilter) {
      case "running":
        result = result.filter((t) => runningTaskIds.includes(t.id) || t.status === "running");
        break;
      case "failed":
        result = result.filter((t) => t.status === "failed" || t.status === "stopped");
        break;
    }

    return result;
  }, [tasks, searchQuery, activeFilter, runningTaskIds, fuseResultIds]);

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
      <div className="flex items-center px-5 py-5 border-b border-border/10 mb-3">
        <div className="flex items-center gap-2">
          <img src="/logo.png" alt="AI Info Collector" className="size-9 object-contain rounded-xl shadow-lg shadow-primary/10" />
          <div className="leading-none">
            <h1 className="text-sm font-bold text-foreground">AI Info Collector</h1>
            <span className="text-[10px] text-muted-foreground font-medium">智能采集工作台</span>
          </div>
        </div>
      </div>

      {/* 导航菜单 */}
      <div className="px-3 pb-4 space-y-1">
        {[
          { id: "collector", label: "高校库", icon: <BookOpenText className="size-4 shrink-0" /> },
        ].map((tab) => (
          <div key={tab.id} className="relative">
            {activeTab === tab.id && (
              <motion.div
                layoutId="active-sidebar-pill"
                className="absolute inset-0 bg-primary/10 border border-primary/20 rounded-xl"
                transition={{ type: "spring", stiffness: 380, damping: 30 }}
              />
            )}
            <button
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex w-full items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all relative z-10 ${
                activeTab === tab.id
                  ? "text-primary font-semibold"
                  : "text-muted-foreground hover:bg-muted/30 hover:text-foreground"
              }`}
            >
              {tab.icon}
              <span className="relative z-20">{tab.label}</span>
            </button>
          </div>
        ))}
      </div>

      <div className="mx-4 border-t border-border/30 my-2" />

      {/* 新建任务 */}
      <div className="px-3 pb-2">
        <Button
          variant="ghost"
          className="w-full justify-start gap-2.5 rounded-xl text-xs font-semibold text-muted-foreground/60 transition-all duration-250 hover:-translate-y-[0.5px] hover:bg-primary/10 hover:text-primary"
          onClick={newTask}
          style={{ transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)" }}
        >
          <Plus className="size-4" />
          新采集会话
        </Button>
      </div>

      {/* 搜索 */}
      <SearchBar
        onSearch={search}
        tasks={searchableTasks}
        onFuseResults={(ids) => {
          setFuseResultIds(ids.length > 0 ? ids : null);
        }}
      />

      {/* 筛选标签 */}
      <div className="flex gap-1 px-4 pb-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setActiveFilter(f.key)}
            className={`rounded-lg px-2 py-1 text-[11px] font-medium transition-colors ${
              activeFilter === f.key
                ? "bg-primary/15 text-primary"
                : "text-muted-foreground/50 hover:text-muted-foreground hover:bg-muted/30"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* 分隔 */}
      <div className="mx-4 border-t border-border/40" />

      {/* 任务列表 */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="px-2 py-2">
          {groupedTasks.length === 0 ? (
            <p className="px-5 py-6 text-xs text-muted-foreground/40">
              {searchQuery || fuseResultIds ? "无匹配结果" : "暂无任务"}
            </p>
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
        <span className="text-[10px] text-muted-foreground/40 font-mono">南京微特喜网络科技有限公司</span>
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
