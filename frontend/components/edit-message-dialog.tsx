"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useUIStore } from "@/stores/ui-store";
import { useAgentChat } from "@/hooks/use-agent-chat";

export function EditMessageDialog() {
  const editTarget = useUIStore((s) => s.editTarget);
  const setEditTarget = useUIStore((s) => s.setEditTarget);
  const { editSave } = useAgentChat();

  const [content, setContent] = useState(editTarget?.content || "");

  const open = editTarget !== null;

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) setEditTarget(null);
        if (o && editTarget) setContent(editTarget.content);
      }}
    >
      <DialogContent className="rounded-[24px] sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>编辑消息</DialogTitle>
          <DialogDescription>修改后会自动重新发送</DialogDescription>
        </DialogHeader>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          className="min-h-[100px] w-full resize-none rounded-[24px] border border-border bg-muted/50 px-4 py-3 text-sm outline-none focus:ring-1 focus:ring-ring"
          autoFocus
        />
        <DialogFooter>
          <Button variant="ghost" onClick={() => setEditTarget(null)} className="rounded-xl">
            取消
          </Button>
          <Button
            onClick={() => {
              if (content.trim()) {
                editSave(content.trim());
              }
            }}
            disabled={!content.trim()}
            className="rounded-xl"
          >
            保存并重新发送
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
