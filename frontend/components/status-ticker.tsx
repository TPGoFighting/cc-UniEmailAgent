"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useChatStore } from "@/stores/chat-store";
import { useTaskStore } from "@/stores/task-store";
import type { ComposerState } from "@/lib/types";

function getEmoji(content: string): string {
  const lower = content.toLowerCase();
  if (/完成|成功|done|完成|结束/.test(lower)) return "✅";
  if (/搜索|查找|探索|浏览|导航|listing|navigat/.test(lower)) return "🔍";
  if (/处理|提取|解析|抓取|extract|pars|crawl/.test(lower)) return "📄";
  if (/分析|思考|识别|generat|analyz/.test(lower)) return "🤔";
  return "🔄";
}

interface StatusTickerProps {
  composerState: ComposerState;
}

export function StatusTicker({ composerState }: StatusTickerProps) {
  const activeTaskId = useTaskStore((s) => s.activeTaskId);
  const taskMessages = useChatStore((s) => (activeTaskId ? s.taskMessages[activeTaskId] : undefined));

  const [currentIndex, setCurrentIndex] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Only show during active task execution
  const isActive = composerState === "connecting" || composerState === "streaming";

  // Extract messages with role "log" or "progress"
  const statusMessages = isActive && taskMessages
    ? taskMessages
        .filter((m) => m.role === "log" || m.role === "progress")
        .slice(-3)
    : [];

  // Reset index when messages change
  useEffect(() => {
    setCurrentIndex(0);
  }, [statusMessages.length]);

  // Cycle through messages every 3 seconds
  useEffect(() => {
    if (!isActive || statusMessages.length <= 1) {
      if (timerRef.current) clearInterval(timerRef.current);
      return;
    }

    timerRef.current = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % statusMessages.length);
    }, 3000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isActive, statusMessages.length]);

  if (!isActive || statusMessages.length === 0) return null;

  const currentMessage = statusMessages[currentIndex];
  if (!currentMessage) return null;

  return (
    <div className="mx-auto max-w-3xl px-6 md:px-8">
      <div className="h-5 flex items-center">
        <AnimatePresence mode="wait">
          <motion.span
            key={`${currentIndex}-${currentMessage.id}`}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            className="text-[11px] text-muted-foreground/60 truncate"
            title={currentMessage.content}
          >
            {getEmoji(currentMessage.content)} {currentMessage.content}
          </motion.span>
        </AnimatePresence>
      </div>
    </div>
  );
}
