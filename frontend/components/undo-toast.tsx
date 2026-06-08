"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Undo2 } from "lucide-react";
import { useChatStore } from "@/stores/chat-store";

export function UndoToast() {
  const [visible, setVisible] = useState(false);
  const [label, setLabel] = useState("");

  // 订阅 store 中的 undoQueue 变化
  useEffect(() => {
    const unsub = useChatStore.subscribe((s) => {
      const q = s.undoQueue;
      if (q.length > 0) {
        const last = q[q.length - 1];
        const preview = last.message.content.slice(0, 40);
        setLabel(last.message.role === "user" ? `已删除消息: "${preview}..."` : "已删除回复");
        setVisible(true);
      }
    });
    return unsub;
  }, []);

  const handleUndo = useCallback(() => {
    const entry = useChatStore.getState().popUndo();
    if (entry) {
      // 恢复消息到原任务
      useChatStore.getState().appendMessage(entry.taskId, entry.message);
    }
    setVisible(false);
  }, []);

  // 5 秒后自动隐藏
  useEffect(() => {
    if (!visible) return;
    const timer = setTimeout(() => {
      useChatStore.getState().clearUndoQueue();
      setVisible(false);
    }, 5000);
    return () => clearTimeout(timer);
  }, [visible]);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ y: 80, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 80, opacity: 0 }}
          transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
          className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2"
        >
          <div className="flex items-center gap-3 rounded-2xl border border-border bg-background px-4 py-3 shadow-lg">
            <span className="text-sm text-muted-foreground">{label}</span>
            <button
              onClick={handleUndo}
              className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary hover:bg-primary/20 transition-colors"
            >
              <Undo2 className="size-3" />
              撤销
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
