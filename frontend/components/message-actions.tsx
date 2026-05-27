"use client";

import { useState } from "react";
import { Copy, Pencil, Trash2, RotateCcw, Check } from "lucide-react";

interface MessageActionsProps {
  role: "user" | "agent";
  content: string;
  onCopy?: () => void;
  onEdit?: () => void;
  onRetry?: () => void;
  onDelete?: () => void;
}

export function MessageActions({
  role,
  content,
  onCopy,
  onEdit,
  onRetry,
  onDelete,
}: MessageActionsProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    onCopy?.();
  };

  return (
    <div
      className="flex items-center gap-0.5 opacity-0 transition-opacity duration-250 group-hover:opacity-100"
      style={{ transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)" }}
    >
      <button
        onClick={handleCopy}
        className="rounded-lg p-1.5 text-muted-foreground/40 hover:bg-muted hover:text-muted-foreground transition-colors"
        title={copied ? "已复制" : "复制"}
      >
        {copied ? <Check className="size-3.5 text-primary" /> : <Copy className="size-3.5" />}
      </button>

      {role === "user" ? (
        <>
          <button
            onClick={onEdit}
            className="rounded-lg p-1.5 text-muted-foreground/40 hover:bg-muted hover:text-muted-foreground transition-colors"
            title="编辑"
          >
            <Pencil className="size-3.5" />
          </button>
          <button
            onClick={onDelete}
            className="rounded-lg p-1.5 text-muted-foreground/40 hover:bg-destructive/10 hover:text-destructive transition-colors"
            title="删除"
          >
            <Trash2 className="size-3.5" />
          </button>
        </>
      ) : (
        <>
          <button
            onClick={onRetry}
            className="rounded-lg p-1.5 text-muted-foreground/40 hover:bg-muted hover:text-muted-foreground transition-colors"
            title="重试"
          >
            <RotateCcw className="size-3.5" />
          </button>
          <button
            onClick={onDelete}
            className="rounded-lg p-1.5 text-muted-foreground/40 hover:bg-destructive/10 hover:text-destructive transition-colors"
            title="删除"
          >
            <Trash2 className="size-3.5" />
          </button>
        </>
      )}
    </div>
  );
}
