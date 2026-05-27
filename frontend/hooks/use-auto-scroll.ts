"use client";

import { useEffect, useRef } from "react";

/**
 * 自动滚动到底部。
 * 直接设置 scrollTop 避免 scrollIntoView 的平滑动画在流式输出时互相冲突，
 * 也避免与 @base-ui/react ScrollArea 的内部滚动管理冲突。
 */
export function useAutoScroll(dependency: unknown) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = bottomRef.current;
    if (!el) return;
    // 找到 @base-ui/react ScrollArea 的 viewport（最近的滚动容器）
    const scrollParent = el.closest<HTMLElement>(
      '[data-slot="scroll-area-viewport"]'
    );
    if (scrollParent) {
      scrollParent.scrollTop = scrollParent.scrollHeight;
    }
  }, [dependency]);

  return bottomRef;
}
