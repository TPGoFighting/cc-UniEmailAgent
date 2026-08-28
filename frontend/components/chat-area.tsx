"use client";

import { useState, useEffect, useCallback } from "react";
import { PanelLeft, BookOpenText, Mail, Activity, Loader2, StopCircle, Search, Globe, RefreshCw, MoreHorizontal, Terminal, Key } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatInput } from "@/components/chat-input";
import { ChatMessage } from "@/components/chat-message";
import { TypingIndicator } from "@/components/typing-indicator";
import { CrawlProgress } from "@/components/crawl-progress";
import { AgentActivityCard } from "@/components/agent-activity-card";
import { CrawlProgressPanel } from "@/components/crawl-progress-panel";
import { TaskResultPanel } from "@/components/task-result-panel";
import { ParallelCrawlPanel } from "@/components/parallel-crawl-panel";
import { ErrorAlert } from "@/components/error-alert";
import { LogPanel } from "@/components/log-panel";
import { ApiKeyDialog } from "@/components/api-key-dialog";
import { AgentActivityIndicator } from "@/components/agent-activity-indicator";
import { EmptyState } from "@/components/empty-state";
import { StatusTicker } from "@/components/status-ticker";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";
import { useAutoScroll } from "@/hooks/use-auto-scroll";
import { useKeyboardShortcuts } from "@/hooks/use-keyboard-shortcuts";
import { useChatStore } from "@/stores/chat-store";
import { useTaskStore } from "@/stores/task-store";
import { useUIStore } from "@/stores/ui-store";
import { useAgentChat } from "@/hooks/use-agent-chat";
import { welcomeMessage } from "@/lib/mock-data";
import { api } from "@/services/api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

export function ChatArea() {
  const messages = useChatStore((s) => s.currentMessages);
  const composerStateMap = useChatStore((s) => s.composerStateMap);
  const runningTaskIds = useChatStore((s) => s.runningTaskIds);
  const removeRunningTask = useChatStore((s) => s.removeRunningTask);
  const parallelCrawlMap = useChatStore((s) => s.parallelCrawlMap);
  const activeTaskId = useTaskStore((s) => s.activeTaskId);
  const activeTask = useTaskStore((s) => {
    const aid = s.activeTaskId;
    return aid ? s.tasks.find((t) => t.id === aid) || null : null;
  });
  const tasks = useTaskStore((s) => s.tasks);
  const composerState = activeTaskId ? composerStateMap[activeTaskId] || "idle" : "idle";
  const currentParallelCrawl = activeTaskId ? parallelCrawlMap[activeTaskId] : undefined;
  const setSidebarOpen = useUIStore((s) => s.setSidebarOpen);
  const setUniversityOpen = useUIStore((s) => s.setUniversityOpen);
  const setMailOpen = useUIStore((s) => s.setMailOpen);
  const pendingInput = useUIStore((s) => s.pendingInput);
  const setPendingInput = useUIStore((s) => s.setPendingInput);

  const { send, stop, regenerate, selectTask } = useAgentChat({ streaming: true });

  useKeyboardShortcuts();

  const handleErrorRetry = useCallback(() => {
    if (!activeTaskId) return;
    const msgs = useChatStore.getState().taskMessages[activeTaskId] || [];
    const lastUser = [...msgs].reverse().find((m) => m.role === "user");
    if (lastUser) {
      send(lastUser.content);
    }
  }, [activeTaskId, send]);

  const [procOpen, setProcOpen] = useState(false);
  const [logPanelOpen, setLogPanelOpen] = useState(false);
  const [apiKeyOpen, setApiKeyOpen] = useState(false);
  const [activeProcs, setActiveProcs] = useState<
    Array<{ task_id: string; title: string; started_at: string }>
  >([]);
  const [killingTasks, setKillingTasks] = useState<Record<string, boolean>>({});

  const hasActiveProcs = activeProcs.length > 0 || runningTaskIds.length > 0;

  // 定时轮询后端运行中的任务
  useEffect(() => {
    const fetchProcs = () => {
      api
        .getActiveAgents()
        .then((res) => {
          setActiveProcs(res.active_tasks || []);
          const backendRunning = (res.active_tasks || []).map((t) => t.task_id);
          const currentRunning = useChatStore.getState().runningTaskIds;
          for (const taskId of backendRunning) {
            if (!currentRunning.includes(taskId)) {
              useChatStore.getState().addRunningTask(taskId);
            }
          }
        })
        .catch(() => {});
    };

    fetchProcs();
    const interval = setInterval(fetchProcs, procOpen ? 3000 : 10000);
    return () => clearInterval(interval);
  }, [procOpen, runningTaskIds]);

  const handleKill = async (taskId: string) => {
    setKillingTasks((prev) => ({ ...prev, [taskId]: true }));
    removeRunningTask(taskId);
    try {
      await api.terminateAgent(taskId);
    } catch {
      // ignore — task may already be done
    } finally {
      try {
        const active = await api.getActiveAgents();
        setActiveProcs(active.active_tasks || []);
      } catch {}
      setKillingTasks((prev) => ({ ...prev, [taskId]: false }));
    }
  };

  const { bottomRef, hasNewBelow, scrollToBottom } = useAutoScroll(messages);
  const filteredMessages = messages.filter((m) => m.role !== "log");
  const displayMessages =
    filteredMessages.length > 0 ? filteredMessages : [welcomeMessage];
  const showEmptyState =
    displayMessages.length === 1 &&
    displayMessages[0].id === "welcome" &&
    !activeTask &&
    composerState === "idle";

  const savedTaskId =
    typeof window !== "undefined" ? localStorage.getItem("activeTaskId") : null;
  const hasUnfinishedTask =
    !!savedTaskId &&
    !activeTaskId &&
    tasks.some((t) => t.id === savedTaskId);

  return (
    <main className="flex h-full min-w-0 flex-1 flex-col overflow-hidden bg-background">
      <div className="h-[1px] w-full bg-gradient-to-r from-transparent via-primary/30 to-transparent" />
      <header className="flex items-center gap-3 border-b border-border/30 px-5 py-3 bg-background/80 backdrop-blur-md">
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden hover:bg-primary/10 hover:text-primary"
          onClick={() => setSidebarOpen(true)}
          aria-label="打开侧边栏"
        >
          <PanelLeft className="size-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-medium text-foreground">
            {activeTask ? activeTask.title : "新建任务"}
          </h2>
          {activeTask && (
            <p className="text-xs text-muted-foreground/60">
              {activeTask.date}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <Button
            variant="outline"
            size="sm"
            className="gap-2 rounded-xl border-border/50 bg-background/50 text-muted-foreground hover:text-primary hover:border-primary/30 hover:bg-primary/[0.04]"
            onClick={() => setUniversityOpen(true)}
          >
            <BookOpenText className="size-4" />
            高校库
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="gap-2 rounded-xl border-border/50 bg-background/50 text-muted-foreground hover:text-primary hover:border-primary/30 hover:bg-primary/[0.04]"
            onClick={() => setMailOpen(true)}
          >
            <Mail className="size-4" />
            邮件发送
          </Button>
          <Button
            variant="outline"
            size="icon-sm"
            className="rounded-xl border-border/50 bg-background/50 text-muted-foreground hover:text-primary hover:border-primary/30 hover:bg-primary/[0.04]"
            onClick={() => setApiKeyOpen(true)}
            title="API Key 配置"
          >
            <Key className="size-4" />
          </Button>
          <Button
            variant="outline"
            size="icon-sm"
            className="rounded-xl border-border/50 bg-background/50 text-muted-foreground hover:text-primary hover:border-primary/30 hover:bg-primary/[0.04]"
            onClick={() => setLogPanelOpen(true)}
            title="Agent 实时日志"
          >
            <Terminal className="size-4" />
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger
              className="flex size-8 items-center justify-center rounded-xl text-muted-foreground transition-colors duration-250 hover:bg-primary/[0.06] hover:text-primary outline-none"
              aria-label="更多菜单"
            >
              <MoreHorizontal className="size-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuItem onClick={() => setProcOpen(true)}>
                <Activity className="size-4 text-emerald-500" />
                <span>后台进程管理</span>
                {hasActiveProcs && (
                  <span className="ml-auto relative flex size-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full size-2 bg-emerald-500"></span>
                  </span>
                )}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      {/* 后台进程轻提示 Banner */}
      {hasActiveProcs && !procOpen && (
        <div
          className="flex items-center justify-between px-5 py-2 cursor-pointer transition-colors hover:bg-muted/20"
          style={{ borderBottom: "1px solid rgba(0,0,0,0.04)" }}
          onClick={() => setProcOpen(true)}
        >
          <div className="flex items-center gap-2">
            <span className="relative flex size-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full size-2 bg-emerald-500"></span>
            </span>
            <span className="text-xs text-muted-foreground">
              {activeProcs.length > 0
                ? `有 ${activeProcs.length} 个 Agent 在后台运行`
                : `有 ${runningTaskIds.length} 个任务正在运行中`}
            </span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[10px] text-muted-foreground/60 hover:text-muted-foreground"
          >
            查看详情 →
          </Button>
        </div>
      )}

      {showEmptyState ? (
        <EmptyState
          recentTasks={tasks.slice(0, 3)}
          onSelectTask={selectTask}
          onPromptClick={(prompt) => send(prompt)}
          activeTaskId={activeTaskId}
          hasUnfinishedTask={hasUnfinishedTask}
        />
      ) : (
        <ScrollArea className="flex-1 min-h-0">
          <div className="mx-auto max-w-3xl px-6 py-6 md:px-8 md:py-8">
            {displayMessages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} />
            ))}

            {/* 任务进行中：打字指示器 */}
            {(composerState === "connecting" || composerState === "streaming") && (
              <div className="ml-11">
                <TypingIndicator />
              </div>
            )}

            {/* 并行爬取结果面板（任务完成后） */}
            {currentParallelCrawl && (
              <ParallelCrawlPanel crawlState={currentParallelCrawl} />
            )}

            {/* 任务结果面板 */}
            {composerState === "completed" && (
              <TaskResultPanel />
            )}

            <div ref={bottomRef} />
          </div>
        </ScrollArea>
      )}

      {/* 有新消息下方浮按钮 */}
      {hasNewBelow && (
        <div className="relative flex justify-center -mt-2 mb-1 z-10 pointer-events-none">
          <button
            onClick={scrollToBottom}
            className="pointer-events-auto inline-flex items-center gap-1.5 rounded-full border border-border/40 bg-background/90 px-3.5 py-1.5 text-[11px] font-medium text-primary shadow-sm backdrop-blur-md transition-all duration-250 hover:bg-background hover:shadow-md hover:-translate-y-0.5 animate-fade-in"
          >
            <span className="inline-block size-1.5 rounded-full bg-primary animate-pulse" />
            新消息 ↓
          </button>
        </div>
      )}

      <StatusTicker composerState={composerState} />

      <AgentActivityIndicator />

      <ChatInput
        onSend={send}
        onStop={stop}
        onRegenerate={regenerate}
        composerState={composerState}
        externalValue={pendingInput}
        onExternalValueConsumed={() => setPendingInput(null)}
      />

      <Dialog open={procOpen} onOpenChange={setProcOpen}>
        <DialogContent className="sm:max-w-md max-w-lg p-0 overflow-hidden">
          <DialogHeader className="px-5 py-4 border-b">
            <DialogTitle className="flex items-center gap-2">
              <Activity className="size-5 text-emerald-500 animate-pulse" />
              Agent 后台进程管理
            </DialogTitle>
            <DialogDescription>
              监控并管理正在后台执行抓取的 Agent 进程。
            </DialogDescription>
          </DialogHeader>
          <div className="p-5 max-h-[350px] overflow-y-auto space-y-3">
            {activeProcs.length === 0 && runningTaskIds.length === 0 ? (
              <div className="py-8 text-center text-xs text-muted-foreground flex flex-col items-center justify-center gap-2 border border-dashed rounded-lg">
                <Activity className="size-8 text-muted-foreground/30" />
                <span>暂无运行中的后台 Agent 进程</span>
              </div>
            ) : activeProcs.length === 0 && runningTaskIds.length > 0 ? (
              runningTaskIds.map((id) => (
                <div
                  key={id}
                  className="flex items-center justify-between gap-4 p-3 border rounded-lg hover:bg-muted/10 transition-colors"
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-semibold truncate text-foreground">
                      {id === activeTaskId && activeTask
                        ? activeTask.title
                        : "Agent 任务启动中..."}
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-1 flex items-center gap-2">
                      <span className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-600 font-mono scale-90 origin-left">
                        CONNECTING
                      </span>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 text-xs text-red-500 hover:bg-red-50 hover:text-red-600 shrink-0 gap-1"
                    disabled={killingTasks[id]}
                    onClick={() => handleKill(id)}
                  >
                    {killingTasks[id] ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <StopCircle className="size-3.5" />
                    )}
                    关闭进程
                  </Button>
                </div>
              ))
            ) : (
              activeProcs.map((proc) => (
                <div
                  key={proc.task_id}
                  className="flex items-center justify-between gap-4 p-3 border rounded-lg hover:bg-muted/10 transition-colors"
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-semibold truncate text-foreground">
                      {proc.title}
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-1 flex items-center gap-2">
                      <span className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-600 font-mono scale-90 origin-left">
                        RUNNING
                      </span>
                      <span>启动时间: {proc.started_at}</span>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 text-xs text-red-500 hover:bg-red-50 hover:text-red-600 shrink-0 gap-1"
                    disabled={killingTasks[proc.task_id]}
                    onClick={() => handleKill(proc.task_id)}
                  >
                    {killingTasks[proc.task_id] ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <StopCircle className="size-3.5" />
                    )}
                    关闭进程
                  </Button>
                </div>
              ))
            )}
          </div>
          <div className="px-5 py-3 border-t bg-muted/30 text-[10px] text-muted-foreground flex items-center justify-between">
            <span>自动刷新时间：每 3 秒</span>
            <span>当前活动进程数：{activeProcs.length}</span>
          </div>
        </DialogContent>
      </Dialog>

      <LogPanel open={logPanelOpen} onOpenChange={setLogPanelOpen} />
      <ApiKeyDialog open={apiKeyOpen} onOpenChange={setApiKeyOpen} />
    </main>
  );
}
