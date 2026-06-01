"use client";

import { useState, type KeyboardEvent, type ChangeEvent } from "react";
import { ArrowUp, Loader2, Square, RotateCcw, Play } from "lucide-react";
import { useAutoResize } from "@/hooks/use-auto-resize";

export type ComposerState = "idle" | "connecting" | "streaming" | "completed" | "stopped" | "error";

interface ChatInputProps {
  onSend: (message: string) => void;
  onStop: () => void;
  onRegenerate: () => void;
  disabled?: boolean;
  composerState?: ComposerState;
}

export function ChatInput({
  onSend,
  onStop,
  onRegenerate,
  disabled,
  composerState = "idle",
}: ChatInputProps) {
  const [input, setInput] = useState("");
  const { textareaRef, resize } = useAutoResize();

  const handleSend = () => {
    const trimmed = input.trim();
    // idle / completed / stopped 状态下都允许发送新消息
    if (
      !trimmed ||
      disabled ||
      (composerState !== "idle" &&
        composerState !== "completed" &&
        composerState !== "stopped")
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
    if (e.key === "Enter" && !e.shiftKey) {
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

  return (
    <div className="px-4 pb-6 pt-2">
      <div className="mx-auto max-w-3xl">
        <div className="relative flex items-end gap-2 rounded-[24px] border bg-white/80 px-3 py-2 shadow-[0_2px_8px_rgba(0,0,0,0.04),0_8px_32px_rgba(0,0,0,0.03)] backdrop-blur-xl transition-shadow focus-within:shadow-[0_2px_12px_rgba(0,0,0,0.06),0_12px_40px_rgba(0,0,0,0.05)] dark:bg-[#2A2B32]/80 dark:shadow-none dark:focus-within:ring-1 dark:focus-within:ring-border"
          style={{ borderColor: "rgba(0,0,0,0.06)" }}
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={
              isCompleted
                ? "输入新指令，例如：把有邮箱和没邮箱的分成两个表格"
                : isStopped
                  ? "继续输入或点击 ▶ 恢复当前任务"
                  : "输入你的任务，例如：帮我抓取南京大学计算机学院教师邮箱"
            }
            disabled={disabled || isStreaming}
            rows={1}
            className="min-h-10 max-h-[200px] flex-1 resize-none overflow-y-auto bg-transparent px-2 py-2 text-sm text-foreground placeholder:text-[#9A9AA5] outline-none disabled:cursor-not-allowed disabled:opacity-50 dark:placeholder:text-[#6E6E80]"
          />

          {/* Send Button (idle, or completed/stopped with input) */}
          {(isIdle || ((isCompleted || isStopped) && input.trim())) && (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition-all duration-250 hover:-translate-y-[1px] hover:opacity-90 disabled:pointer-events-none disabled:opacity-30"
              style={{ transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)" }}
            >
              <ArrowUp className="size-4" />
            </button>
          )}

          {/* Connecting spinner */}
          {(composerState === "connecting") && (
            <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/80 text-primary-foreground">
              <Loader2 className="size-4 animate-spin" />
            </div>
          )}

          {/* Stop Button (streaming) */}
          {composerState === "streaming" && (
            <button
              onClick={onStop}
              className="flex size-9 shrink-0 items-center justify-center rounded-full bg-destructive text-destructive-foreground transition-all duration-250 hover:-translate-y-[1px] hover:opacity-90"
              style={{ transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)" }}
              title="停止生成"
            >
              <Square className="size-3.5" />
            </button>
          )}

          {/* Regenerate Button (completed, empty input) */}
          {isCompleted && !input.trim() && (
            <button
              onClick={onRegenerate}
              className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition-all duration-250 hover:-translate-y-[1px] hover:opacity-90"
              style={{ transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)" }}
              title="重新生成"
            >
              <RotateCcw className="size-4" />
            </button>
          )}

          {/* Continue Button (stopped, empty input) */}
          {isStopped && !input.trim() && (
            <button
              onClick={() => {
                onSend("继续");
              }}
              className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition-all duration-250 hover:-translate-y-[1px] hover:opacity-90"
              style={{ transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)" }}
              title="继续"
            >
              <Play className="size-4" />
            </button>
          )}
        </div>
        <p className="mt-2 text-center text-xs text-[#9A9AA5] dark:text-[#6E6E80]">
          Enter 发送 · Shift+Enter 换行
        </p>
      </div>
    </div>
  );
}
