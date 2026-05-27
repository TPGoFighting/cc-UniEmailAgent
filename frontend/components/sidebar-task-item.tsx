"use client";

import { useState, useRef, useEffect } from "react";
import { Loader2, CheckCircle2, XCircle, Pin, Pencil, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Task } from "@/lib/types";

interface SidebarTaskItemProps {
  task: Task;
  isActive: boolean;
  isRunning?: boolean;
  onSelect: () => void;
  onRename: (newTitle: string) => void;
  onPin: () => void;
  onDelete: () => void;
}

export function SidebarTaskItem({
  task,
  isActive,
  isRunning = false,
  onSelect,
  onRename,
  onPin,
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

  return (
    <div className="group relative">
      <button
        onClick={onSelect}
        className={cn(
          "flex w-full items-start gap-3 rounded-[24px] px-3 py-2.5 text-left transition-colors duration-250 hover:bg-black/[0.04] dark:hover:bg-white/[0.06]",
          isActive && "bg-black/[0.06] dark:bg-white/[0.08]"
        )}
        style={{ transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)" }}
      >
        <div className="mt-0.5 shrink-0">
          {task.pinned ? (
            <Pin className="size-3.5 text-primary/60" />
          ) : isRunning ? (
            <Loader2 className="size-3.5 animate-spin text-primary" />
          ) : task.status === "completed" ? (
            <CheckCircle2 className="size-3.5 text-primary" />
          ) : task.status === "running" ? (
            <div className="size-3.5 animate-pulse rounded-full bg-primary/60" />
          ) : (
            <XCircle className="size-3.5 text-muted-foreground/40" />
          )}
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
              className="w-full rounded-md border border-border bg-background px-1.5 py-0.5 text-sm outline-none"
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <p className="truncate text-sm font-medium text-foreground/80 group-hover:text-foreground">
              {task.title}
            </p>
          )}
          <p className="text-xs text-[#9A9AA5] dark:text-[#6E6E80]">{task.date}</p>
        </div>
      </button>

      {/* Hover 操作按钮 */}
      <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-0.5 opacity-0 transition-opacity duration-250 group-hover:opacity-100">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onPin();
          }}
          className="rounded-lg p-1.5 text-muted-foreground/50 hover:bg-black/[0.06] hover:text-muted-foreground dark:hover:bg-white/[0.08]"
          title={task.pinned ? "取消置顶" : "置顶"}
        >
          <Pin className={cn("size-3", task.pinned && "fill-primary/60 text-primary")} />
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setRenameValue(task.title);
            setIsRenaming(true);
          }}
          className="rounded-lg p-1.5 text-muted-foreground/50 hover:bg-black/[0.06] hover:text-muted-foreground dark:hover:bg-white/[0.08]"
          title="重命名"
        >
          <Pencil className="size-3" />
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="rounded-lg p-1.5 text-muted-foreground/50 hover:bg-destructive/10 hover:text-destructive dark:hover:bg-destructive/20"
          title="删除"
        >
          <Trash2 className="size-3" />
        </button>
      </div>
    </div>
  );
}
