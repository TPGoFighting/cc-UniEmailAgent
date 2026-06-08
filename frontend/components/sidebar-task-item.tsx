"use client";

import { useState, useRef, useEffect } from "react";
import { Pencil, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Task } from "@/lib/types";

interface SidebarTaskItemProps {
  task: Task;
  isActive: boolean;
  isRunning?: boolean;
  onSelect: () => void;
  onRename: (newTitle: string) => void;
  onDelete: () => void;
}

const MAX_TITLE_LENGTH = 12;

function truncateTitle(title: string): string {
  if (title.length <= MAX_TITLE_LENGTH) return title;
  return title.slice(0, MAX_TITLE_LENGTH) + "…";
}

function hasData(task: Task): boolean {
  if (task.status !== "completed") return false;
  if (!task.messages) return false;
  return task.messages.some((m) => m.role === "download");
}

function StatusIcon({ task, isRunning }: { task: Task; isRunning: boolean }) {
  return null;
}

function StatusBadge({ task, isRunning }: { task: Task; isRunning: boolean }) {
  return null;
}

export function SidebarTaskItem({
  task,
  isActive,
  isRunning = false,
  onSelect,
  onRename,
  onDelete,
}: SidebarTaskItemProps) {
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(task.title);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isRenaming && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isRenaming]);

  const handleRenameSubmit = () => {
    const trimmed = renameValue.trim();
    if (trimmed && trimmed !== task.title) {
      onRename(trimmed);
    }
    setIsRenaming(false);
  };


  // ===== 折叠态：图标 + 截断单行标题 + 状态标签 =====
  if (!isActive) {
    return (
      <button
        onClick={onSelect}
        className={cn(
          "flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-all duration-250",
          "hover:bg-primary/[0.06] hover:text-primary",
          "group",
        )}
        style={{ transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)" }}
      >
        <div className="mt-0.5 shrink-0">
          <StatusIcon task={task} isRunning={isRunning} />
        </div>
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground/70 transition-colors duration-250 group-hover:text-foreground">
          {truncateTitle(task.title)}
        </span>
        <StatusBadge task={task} isRunning={isRunning} />
      </button>
    );
  }

  // ===== 展开态：完整标题 + 元信息行 + 操作栏 =====
  return (
    <div
      className={cn(
        "rounded-xl transition-all duration-250",
        "bg-primary/[0.06] ring-1 ring-primary/20",
      )}
      style={{ transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)" }}
    >
      {/* 主内容区（可点击选择） */}
      <button
        onClick={onSelect}
        className="flex w-full items-start gap-3 px-3 pt-2.5 pb-2 text-left"
      >
        <div className="mt-0.5 shrink-0">
          <StatusIcon task={task} isRunning={isRunning} />
        </div>
        <div className="min-w-0 flex-1">
          {isRenaming ? (
            <input
              ref={inputRef}
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleRenameSubmit();
                if (e.key === "Escape") setIsRenaming(false);
              }}
              onBlur={handleRenameSubmit}
              className="w-full rounded-lg border border-border bg-background px-2 py-1 text-sm outline-none ring-1 ring-primary/20"
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <p className="text-sm font-medium text-foreground leading-snug">
              {truncateTitle(task.title)}
            </p>
          )}
        </div>
      </button>

      {/* 分隔线 */}
      <div className="mx-3 border-t border-border/30" />

      {/* 底部操作栏 */}
      <div className="flex items-center justify-between gap-1 px-3 py-2">
        <span className="text-[10px] text-muted-foreground/50 px-1">{task.date}</span>
        <div className="flex items-center gap-1">
        <button
          onClick={(e) => {
            e.stopPropagation();
            setRenameValue(task.title);
            setIsRenaming(true);
          }}
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] text-muted-foreground/50 hover:bg-primary/10 hover:text-primary transition-colors whitespace-nowrap"
        >
          <Pencil className="size-3" />
          重命名
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] text-muted-foreground/50 hover:bg-destructive/15 hover:text-destructive transition-colors whitespace-nowrap"
        >
          <Trash2 className="size-3" />
          删除
        </button>
        </div>
      </div>
    </div>
  );
}
