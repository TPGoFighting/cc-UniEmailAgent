"use client";

import { useEffect, useRef } from "react";
import { X, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChatStore } from "@/stores/chat-store";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface LogPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function LogPanel({ open, onOpenChange }: LogPanelProps) {
  const viewingTaskId = useChatStore((s) => s.viewingTaskId);
  const logsMap = useChatStore((s) => s.logsMap);
  const clearLogs = useChatStore((s) => s.clearLogs);
  const lines = viewingTaskId ? logsMap[viewingTaskId] || [] : [];
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [open, lines.length]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-2xl max-w-[90vw] p-0"
        showCloseButton={false}
      >
        <DialogHeader className="flex flex-row items-center justify-between px-5 py-3 border-b shrink-0">
          <DialogTitle className="flex items-center gap-2 text-sm font-mono text-muted-foreground">
            <span className="inline-flex size-2 rounded-full bg-emerald-500 animate-pulse" />
            Agent 日志
            <span className="text-[10px] text-muted-foreground/50 font-normal">
              ({lines.length} 行)
            </span>
          </DialogTitle>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon-xs"
              className="text-muted-foreground hover:text-red-500"
              onClick={() => viewingTaskId && clearLogs(viewingTaskId)}
              title="清空日志"
            >
              <Trash2 className="size-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon-xs"
              className="text-muted-foreground"
              onClick={() => onOpenChange(false)}
            >
              <X className="size-4" />
            </Button>
          </div>
        </DialogHeader>

        <div
          className="overflow-auto font-mono text-xs leading-relaxed p-4 select-text"
          style={{
            maxHeight: "60vh",
            background: "#0d1117",
            color: "#c9d1d9",
          }}
        >
          {lines.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 gap-3 text-muted-foreground/40">
              <span className="text-2xl">📋</span>
              <span className="text-[11px]">暂无日志输出</span>
              <span className="text-[10px]">Agent 开始执行后日志将实时显示在此处</span>
            </div>
          ) : (
            lines.map((line, i) => (
              <div key={i} className="whitespace-pre-wrap break-all hover:bg-white/[0.04] px-1 rounded">
                {line}
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
