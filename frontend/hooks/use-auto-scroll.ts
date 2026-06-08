"use client";

import { useEffect, useRef, useState, useCallback } from "react";

interface AutoScrollResult {
  bottomRef: React.RefObject<HTMLDivElement | null>;
  /** 用户是否向上滚动查看历史，有新消息在下方 */
  hasNewBelow: boolean;
  /** 滚动到底部并恢复自动滚动 */
  scrollToBottom: () => void;
}

/**
 * 智能自动滚动 hook：
 * - 用户滚动到底部时自动跟随新内容
 * - 用户向上翻阅历史时停止自动滚动
 * - 有新消息时显示"新消息 ↓"指示
 */
export function useAutoScroll(dependency: unknown): AutoScrollResult {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [hasNewBelow, setHasNewBelow] = useState(false);
  const userScrolledUpRef = useRef(false);
  const scrollContainerRef = useRef<HTMLElement | null>(null);

  // 检测用户滚动位置
  useEffect(() => {
    const el = bottomRef.current;
    if (!el) return;

    const scrollParent = el.closest<HTMLElement>(
      '[data-slot="scroll-area-viewport"]'
    );

    if (!scrollParent) return;
    scrollContainerRef.current = scrollParent;

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = scrollParent;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 80;
      userScrolledUpRef.current = !isNearBottom;
      if (isNearBottom) {
        setHasNewBelow(false);
      }
    };

    scrollParent.addEventListener("scroll", handleScroll, { passive: true });
    return () => scrollParent.removeEventListener("scroll", handleScroll);
  }, []);

  // 新内容时自动滚动或标记有新消息
  useEffect(() => {
    const el = bottomRef.current;
    const scrollParent = scrollContainerRef.current;
    if (!el || !scrollParent) return;

    if (userScrolledUpRef.current) {
      // 用户正在翻阅历史 → 标记有新内容，不自动滚动
      setHasNewBelow(true);
    } else {
      // 用户在看底部 → 直接滚到底
      scrollParent.scrollTop = scrollParent.scrollHeight;
      setHasNewBelow(false);
    }
  }, [dependency]);

  const scrollToBottom = useCallback(() => {
    const el = bottomRef.current;
    const scrollParent = scrollContainerRef.current;
    if (!el || !scrollParent) return;
    userScrolledUpRef.current = false;
    setHasNewBelow(false);
    scrollParent.scrollTo({ top: scrollParent.scrollHeight, behavior: "smooth" });
  }, []);

  return { bottomRef, hasNewBelow, scrollToBottom };
}
