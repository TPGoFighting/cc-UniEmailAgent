"use client";

import { Copy, Pencil, Trash2, RotateCcw } from "lucide-react";
import {
  ContextMenu,
  ContextMenuTrigger,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
} from "@/components/ui/context-menu";

interface ContextMenuMessageProps {
  children: React.ReactNode;
  role: "user" | "agent";
  content: string;
  onCopy?: () => void;
  onEdit?: () => void;
  onRetry?: () => void;
  onDelete?: () => void;
}

export function ContextMenuMessage({
  children,
  role,
  onCopy,
  onEdit,
  onRetry,
  onDelete,
}: ContextMenuMessageProps) {
  return (
    <ContextMenu>
      <ContextMenuTrigger>{children}</ContextMenuTrigger>
      <ContextMenuContent className="w-40">
        <ContextMenuItem onClick={onCopy}>
          <Copy className="size-3.5" />
          <span>复制</span>
        </ContextMenuItem>
        {role === "user" ? (
          <>
            <ContextMenuItem onClick={onEdit}>
              <Pencil className="size-3.5" />
              <span>编辑</span>
            </ContextMenuItem>
            <ContextMenuSeparator />
            <ContextMenuItem variant="destructive" onClick={onDelete}>
              <Trash2 className="size-3.5" />
              <span>删除</span>
            </ContextMenuItem>
          </>
        ) : (
          <>
            <ContextMenuItem onClick={onRetry}>
              <RotateCcw className="size-3.5" />
              <span>重试</span>
            </ContextMenuItem>
            <ContextMenuSeparator />
            <ContextMenuItem variant="destructive" onClick={onDelete}>
              <Trash2 className="size-3.5" />
              <span>删除</span>
            </ContextMenuItem>
          </>
        )}
      </ContextMenuContent>
    </ContextMenu>
  );
}
