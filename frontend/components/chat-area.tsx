"use client";

import { useState, useEffect } from "react";
import { PanelLeft, BookOpenText, Mail, Activity, Loader2, StopCircle, Bug } from "lucide-react";
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
  const activeTaskId = useTaskStore((s) => s.activeTaskId);
  const activeTask = useTaskStore((s) => {
    const aid = s.activeTaskId;
    return aid ? s.tasks.find((t) => t.id === aid) || null : null;
  });
  const tasks = useTaskStore((s) => s.tasks);
  const composerState = activeTaskId ? composerStateMap[activeTaskId] || "idle" : "idle";
  const setSidebarOpen = useUIStore((s) => s.setSidebarOpen);
  const setUniversityOpen = useUIStore((s) => s.setUniversityOpen);
  const setMailOpen = useUIStore((s) => s.setMailOpen);

  const { send, stop, regenerate, selectTask } = useAgentChat({ streaming: true });

  const [procOpen, setProcOpen] = useState(false);
  const [activeProcs, setActiveProcs] = useState<Array<{ task_id: string; title: string; started_at: string }>>([]);
  const [killingTasks, setKillingTasks] = useState<Record<string, boolean>>({});
  const [showDebug, setShowDebug] = useState(false);

  // 定时轮询后端运行中的任务，用于刷新后恢复 running 状态
  useEffect(() => {
    const fetchProcs = () => {
      api.getActiveAgents()
        .then((res) => {
          setActiveProcs(res.active_tasks || []);
          // 同步后端运行中的任务到前端的 runningTaskIds
          const backendRunning = (res.active_tasks || []).map(t => t.task_id);
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
    // 立即从 store 移除，避免进程列表继续显示该任务
    removeRunningTask(taskId);
    try {
      const res = await api.terminateAgent(taskId);
      console.log('Terminate response', res);
    } catch (err) {
      if (err instanceof Error && err.message.includes('404')) {
        console.log('Task already finished, removed from UI');
      } else {
        console.error('Failed to terminate task:', err);
      }
    } finally {
      try {
        const active = await api.getActiveAgents();
        setActiveProcs(active.active_tasks || []);
      } catch {}
      setKillingTasks((prev) => ({ ...prev, [taskId]: false }));
    }
  };
  const bottomRef = useAutoScroll(messages);
  const filteredMessages = showDebug ? messages : messages.filter((m) => m.role !== "log");
  const displayMessages = filteredMessages.length > 0 ? filteredMessages : [welcomeMessage];
  const showEmptyState =
    displayMessages.length === 1 &&
    displayMessages[0].id === "welcome" &&
    !activeTask &&
    composerState === "idle";

  return (
    <main className="flex h-full min-w-0 flex-1 flex-col overflow-hidden bg-background">
      <header className="flex items-center gap-3 border-b px-5 py-3" style={{ borderColor: "rgba(0,0,0,0.06)" }}>
        <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setSidebarOpen(true)} aria-label="打开侧边栏">
          <PanelLeft className="size-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-medium text-foreground">
            {activeTask ? activeTask.title : "新建任务"}
          </h2>
          {activeTask && <p className="text-xs text-muted-foreground">{activeTask.date}</p>}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant={showDebug ? "default" : "outline"}
            size="sm"
            className="gap-1.5"
            onClick={() => setShowDebug((v) => !v)}
            title="开发调试：显示 Agent 原始日志"
          >
            <Bug className="size-3.5" />
            <span className="text-xs">日志</span>
          </Button>
          <Button variant="outline" size="sm" className="gap-2 text-muted-foreground hover:text-foreground" onClick={() => setProcOpen(true)}>
            <Activity className={`size-4 text-emerald-500 ${activeProcs.length > 0 || runningTaskIds.length > 0 ? "animate-pulse" : ""}`} />
            后台进程
            {(activeProcs.length > 0 || runningTaskIds.length > 0) && (
              <span className="relative flex size-2 ml-0.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full size-2 bg-emerald-500"></span>
              </span>
            )}
          </Button>
          <Button variant="outline" size="sm" className="gap-2" onClick={() => setUniversityOpen(true)}>
            <BookOpenText className="size-4" />
            高校库
          </Button>
          <Button variant="outline" size="sm" className="gap-2" onClick={() => setMailOpen(true)}>
            <Mail className="size-4" />
            邮件发送
          </Button>
        </div>
      </header>

      {showEmptyState ? (
        <EmptyState recentTasks={tasks.slice(0, 3)} onSelectTask={selectTask} onPromptClick={(prompt) => send(prompt)} />
      ) : (
        <ScrollArea className="flex-1 min-h-0">
          <div className="mx-auto max-w-3xl px-6 py-6 md:px-8 md:py-8">
            {displayMessages.map((msg) => <ChatMessage key={msg.id} message={msg} />)}
            {(composerState === "connecting" || composerState === "streaming") && (
              <div className="ml-11"><TypingIndicator /></div>
            )}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>
      )}

      <ChatInput onSend={send} onStop={stop} onRegenerate={regenerate} composerState={composerState} />

      <Dialog open={procOpen} onOpenChange={setProcOpen}>
        <DialogContent className="sm:max-w-md max-w-lg p-0 overflow-hidden">
          <DialogHeader className="px-5 py-4 border-b">
            <DialogTitle className="flex items-center gap-2">
              <Activity className="size-5 text-emerald-500 animate-pulse" />
              Agent 后台进程管理
            </DialogTitle>
            <DialogDescription>
              监控并管理正在后台执行抓取的 Agent 进程。人工关闭可防止内存溢出或 Token 额度急速消耗。
            </DialogDescription>
          </DialogHeader>
          <div className="p-5 max-h-[350px] overflow-y-auto space-y-3">
            {activeProcs.length === 0 && runningTaskIds.length === 0 ? (
              <div className="py-8 text-center text-xs text-muted-foreground flex flex-col items-center justify-center gap-2 border border-dashed rounded-lg">
                <Activity className="size-8 text-muted-foreground/30" />
                <span>暂无运行中的后台 Agent 进程</span>
                <span className="text-[10px] text-muted-foreground/60">所有爬取任务已结束，系统运行安全省电</span>
              </div>
            ) : activeProcs.length === 0 && runningTaskIds.length > 0 ? (
              runningTaskIds.map((id) => (
                <div key={id} className="flex items-center justify-between gap-4 p-3 border rounded-lg hover:bg-muted/10 transition-colors">
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-semibold truncate text-foreground">
                      {id === activeTaskId && activeTask ? activeTask.title : "Agent 任务启动中..."}
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-1 flex items-center gap-2">
                      <span className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-600 font-mono scale-90 origin-left">CONNECTING</span>
                      <span>启动时间: 刚刚</span>
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
                <div key={proc.task_id} className="flex items-center justify-between gap-4 p-3 border rounded-lg hover:bg-muted/10 transition-colors">
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-semibold truncate text-foreground">{proc.title}</div>
                    <div className="text-[10px] text-muted-foreground mt-1 flex items-center gap-2">
                      <span className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-600 font-mono scale-90 origin-left">RUNNING</span>
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
    </main>
  );
}
