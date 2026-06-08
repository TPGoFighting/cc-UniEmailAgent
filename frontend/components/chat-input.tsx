"use client";

import { useState, useEffect, type KeyboardEvent, type ChangeEvent } from "react";
import { ArrowUp, Loader2, Square, Play } from "lucide-react";
import { useAutoResize } from "@/hooks/use-auto-resize";

export type ComposerState = "idle" | "connecting" | "streaming" | "completed" | "stopped" | "error";

interface ChatInputProps {
  onSend: (message: string) => void;
  onStop: () => void;
  onRegenerate: () => void;
  disabled?: boolean;
  composerState?: ComposerState;
  externalValue?: string | null;
  onExternalValueConsumed?: () => void;
}

export function ChatInput({
  onSend,
  onStop,
  onRegenerate,
  disabled,
  composerState = "idle",
  externalValue,
  onExternalValueConsumed,
}: ChatInputProps) {
  const [input, setInput] = useState("");
  const { textareaRef, resize } = useAutoResize();

  // 外部值注入（跨面板联动）
  useEffect(() => {
    if (externalValue) {
      setInput(externalValue);
      onExternalValueConsumed?.();
    }
  }, [externalValue]);

  const handleSend = () => {
    const trimmed = input.trim();
    // idle / completed / stopped / error 状态下都允许发送新消息
    if (
      !trimmed ||
      disabled ||
      (composerState !== "idle" &&
        composerState !== "completed" &&
        composerState !== "stopped" &&
        composerState !== "error")
    )
      return;
    onSend(trimmed);
    setInput("");
    // 重置高度
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (!e.shiftKey || e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    resize();
  };

  const isStreaming = composerState === "connecting" || composerState === "streaming";
  const isCompleted = composerState === "completed";
  const isStopped = composerState === "stopped";
  const isIdle = composerState === "idle";

  // 智能占位符
  const placeholder = (() => {
    switch (composerState) {
      case "idle":
        return "💡 输入任务，例如：帮我抓取南京大学计算机学院教师邮箱";
      case "connecting":
        return "正在连接 AI 引擎...";
      case "streaming":
        return "任务执行中，可以输入新指令...";
      case "completed":
        return "继续输入新任务，或选择历史任务";
      case "stopped":
        return "任务已暂停，输入新内容继续";
      case "error":
        return "💡 输入任务，例如：帮我抓取南京大学计算机学院教师邮箱";
      default:
        return "输入你的任务，例如：帮我抓取南京大学计算机学院教师邮箱";
    }
  })();

  // 字数统计 (超过 200 字符时显示)
  const charCount = input.length;
  const showCharCount = charCount > 200;

  return (
    <div className="px-4 pb-5 pt-1">
      <div className="mx-auto max-w-3xl">
        <div className="relative flex items-end gap-2 rounded-2xl border border-border/40 bg-card/60 px-3 py-2 shadow-lg shadow-black/[0.03] backdrop-blur-xl transition-all duration-300 focus-within:border-primary/30 focus-within:shadow-[0_0_20px_rgba(34,211,238,0.08)] dark:bg-card/50"
        >
          <div className="relative flex-1">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              disabled={disabled || isStreaming}
              rows={1}
              className={`min-h-10 max-h-[200px] w-full resize-none overflow-y-auto bg-transparent px-2 py-2 text-sm text-foreground placeholder:text-muted-foreground/40 outline-none disabled:cursor-not-allowed disabled:opacity-50 ${
                isIdle ? "animate-placeholder-pulse" : ""
              }`}
              style={{
                animation: isIdle ? "placeholderPulse 3s ease-in-out infinite" : "none",
              }}
            />
            {/* 占位符脉冲动画 — 纯 CSS */}
            <style>{`
              @keyframes placeholderPulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.6; }
              }
            `}</style>
          </div>

          {/* 字数统计 */}
          {showCharCount && (
            <div className="absolute right-16 bottom-2 text-[10px] text-muted-foreground/40 pointer-events-none select-none">
              {charCount}/500
            </div>
          )}

          {/* Send Button — 所有非流式状态都显示发送按钮 */}
          {(isIdle || isCompleted || isStopped || composerState === "error") && (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className={`flex size-9 shrink-0 items-center justify-center rounded-xl transition-all duration-250 hover:-translate-y-[0.5px] active:scale-95 ${
                input.trim()
                  ? "bg-primary text-primary-foreground shadow-[0_0_12px_rgba(34,211,238,0.3)] hover:shadow-[0_0_20px_rgba(34,211,238,0.45)] disabled:pointer-events-none disabled:opacity-30 disabled:shadow-none"
                  : "bg-muted-foreground/15 text-muted-foreground/40 cursor-not-allowed"
              }`}
              style={{ transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)" }}
            >
              <ArrowUp className="size-4" />
            </button>
          )}

          {/* Connecting spinner */}
          {(composerState === "connecting") && (
            <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/80 text-primary-foreground shadow-[0_0_12px_rgba(34,211,238,0.3)]">
              <Loader2 className="size-4 animate-spin" />
            </div>
          )}

          {/* Stop Button (streaming) */}
          {composerState === "streaming" && (
            <button
              onClick={onStop}
              className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-destructive/90 text-destructive-foreground transition-all duration-250 hover:-translate-y-[0.5px] active:scale-95 hover:shadow-[0_0_16px_rgba(251,113,133,0.3)]"
              style={{ transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)" }}
              title="停止生成"
            >
              <Square className="size-3.5" />
            </button>
          )}

          {/* Continue Button (stopped, empty input) */}
          {isStopped && !input.trim() && (
            <button
              onClick={() => {
                onSend("继续");
              }}
              className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground transition-all duration-250 hover:-translate-y-[0.5px] active:scale-95 shadow-[0_0_12px_rgba(34,211,238,0.3)]"
              style={{ transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)" }}
              title="继续"
            >
              <Play className="size-4" />
            </button>
          )}
        </div>
        <p className="mt-2 text-center text-xs text-muted-foreground/40">
          Enter 发送 · Shift+Enter 换行 · Ctrl+Enter 发送
        </p>
      </div>
    </div>
  );
}
