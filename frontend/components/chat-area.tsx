"use client";

import { PanelLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatInput } from "@/components/chat-input";
import { ChatMessage } from "@/components/chat-message";
import { TypingIndicator } from "@/components/typing-indicator";
import { EmptyState } from "@/components/empty-state";
import { useAutoScroll } from "@/hooks/use-auto-scroll";
import { useChatStore } from "@/stores/chat-store";
import { useTaskStore } from "@/stores/task-store";
import { useUIStore } from "@/stores/ui-store";
import { useAgentChat } from "@/hooks/use-agent-chat";
import { welcomeMessage } from "@/lib/mock-data";

export function ChatArea() {
  const messages = useChatStore((s) => s.currentMessages);
  const composerStateMap = useChatStore((s) => s.composerStateMap);
  const activeTaskId = useTaskStore((s) => s.activeTaskId);
  const activeTask = useTaskStore((s) => {
    const aid = s.activeTaskId;
    return aid ? s.tasks.find((t) => t.id === aid) || null : null;
  });
  const tasks = useTaskStore((s) => s.tasks);
  const composerState = activeTaskId ? (composerStateMap[activeTaskId] || "idle") : "idle";
  const setSidebarOpen = useUIStore((s) => s.setSidebarOpen);

  const {
    send,
    stop,
    regenerate,
    selectTask,
  } = useAgentChat();

  const bottomRef = useAutoScroll(messages);

  const displayMessages =
    messages.length > 0 ? messages : [welcomeMessage];

  // 是否显示空状态
  const showEmptyState =
    displayMessages.length === 1 &&
    displayMessages[0].id === "welcome" &&
    !activeTask &&
    composerState === "idle";

  return (
    <main className="flex h-full flex-1 flex-col min-w-0 overflow-hidden bg-white dark:bg-[#202123]">
      {/* 顶部栏 */}
      <header className="flex items-center gap-3 border-b px-5 py-3" style={{ borderColor: "rgba(0,0,0,0.06)" }}>
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          onClick={() => setSidebarOpen(true)}
          aria-label="打开侧边栏"
        >
          <PanelLeft className="size-4" />
        </Button>
        <div className="min-w-0">
          <h2 className="truncate text-sm font-medium text-foreground">
            {activeTask ? activeTask.title : "新建任务"}
          </h2>
          {activeTask && (
            <p className="text-xs text-[#9A9AA5] dark:text-[#6E6E80]">
              {activeTask.date}
            </p>
          )}
        </div>
      </header>

      {/* 空状态 / 消息列表 */}
      {showEmptyState ? (
        <EmptyState
          recentTasks={tasks.slice(0, 3)}
          onSelectTask={selectTask}
          onPromptClick={(prompt) => send(prompt)}
        />
      ) : (
        <ScrollArea className="flex-1 min-h-0">
          <div className="mx-auto max-w-3xl px-6 py-6 md:px-8 md:py-8">
            {displayMessages.map((msg) => (
              <ChatMessage
                key={msg.id}
                message={msg}
              />
            ))}
            {(composerState === "connecting" || composerState === "streaming") && (
              <div className="ml-11">
                <TypingIndicator />
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>
      )}

      {/* AI Composer */}
      <ChatInput
        onSend={send}
        onStop={stop}
        onRegenerate={regenerate}
        composerState={composerState}
      />
    </main>
  );
}
