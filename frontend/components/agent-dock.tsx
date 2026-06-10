"use client";

import { useCallback, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BookOpenText, Bot, Loader2, MessageCircle, Search, Send, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/services/api";
import { useUIStore } from "@/stores/ui-store";

type Mode = "kb" | "chat";
type Source = {
  university?: string;
  name?: string;
  email?: string;
  department?: string;
  title?: string;
  homepage?: string;
  filename?: string;
};
type DockMessage = { role: "user" | "agent"; content: string; sources?: Source[] };

const quickPrompts: Record<Mode, string[]> = {
  kb: ["南京大学计算机学院教师邮箱", "哪些记录缺少邮箱", "统计南京大学邮箱覆盖情况"],
  chat: ["帮我写一封高校活动邀约邮件", "整理一份运营跟进清单", "如何核验邮件发送名单"],
};

const initialMessages: Record<Mode, DockMessage[]> = {
  kb: [
    {
      role: "agent",
      content:
        "我是**知识库 Agent**，会检索本地高校库里已爬取的 CSV/XLSX 表格，并结合 RAG 给出可核验回答。你可以输入高校、学院、教师姓名或邮箱。",
    },
  ],
  chat: [
    {
      role: "agent",
      content:
        "我是**对话 Agent**，支持 Markdown 回答，可用于运营文案、活动方案、邮件润色和通用问答。需要查教师数据时请切换到知识库 Agent。",
    },
  ],
};

function MarkdownMessage({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
        ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-4">{children}</ul>,
        ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-4">{children}</ol>,
        code: ({ children }) => <code className="rounded bg-muted px-1 py-0.5 font-mono text-[11px]">{children}</code>,
        a: ({ children, href }) => (
          <a className="text-primary underline-offset-2 hover:underline" href={href} target="_blank" rel="noreferrer">
            {children}
          </a>
        ),
        table: ({ children }) => <table className="my-2 w-full border-collapse text-[11px]">{children}</table>,
        th: ({ children }) => <th className="border px-2 py-1 text-left font-medium">{children}</th>,
        td: ({ children }) => <td className="border px-2 py-1">{children}</td>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

export function AgentDock() {
  const open = useUIStore((s) => s.agentDockOpen);
  const mode = useUIStore((s) => s.agentDockMode);
  const setOpen = useUIStore((s) => s.setAgentDockOpen);
  const setMode = useUIStore((s) => s.setAgentDockMode);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [kbMessages, setKbMessages] = useState<DockMessage[]>(initialMessages.kb);
  const [chatMessages, setChatMessages] = useState<DockMessage[]>(initialMessages.chat);

  const messages = mode === "kb" ? kbMessages : chatMessages;
  const setMessages = useCallback(
    (updater: DockMessage[] | ((prev: DockMessage[]) => DockMessage[])) => {
      if (mode === "kb") setKbMessages(updater);
      else setChatMessages(updater);
    },
    [mode],
  );

  const title = mode === "kb" ? "知识库 Agent" : "对话 Agent";
  const Icon = mode === "kb" ? BookOpenText : Bot;
  const placeholder = mode === "kb" ? "查询高校、学院、教师或邮箱" : "输入普通问题、文案或运营方案";
  const currentPrompts = useMemo(() => quickPrompts[mode], [mode]);

  const ask = async (text = input) => {
    const content = text.trim();
    if (!content || loading) return;
    setInput("");
    setLoading(true);
    setMessages((prev) => [...prev, { role: "user", content }]);
    try {
      if (mode === "kb") {
        const res = await api.askKnowledgeAgent(content);
        setMessages((prev) => [...prev, { role: "agent", content: res.answer, sources: res.sources as Source[] }]);
      } else {
        const res = await api.askChatAgent(content);
        setMessages((prev) => [...prev, { role: "agent", content: res.answer }]);
      }
    } catch {
      setMessages((prev) => [...prev, { role: "agent", content: "请求失败，请确认后端服务正在运行，稍后再试。" }]);
    } finally {
      setLoading(false);
    }
  };

  if (!open) {
    return (
      <div className="fixed bottom-5 left-5 z-40 flex flex-col gap-2">
        <Button size="sm" variant="outline" className="h-9 justify-start gap-2 rounded-xl bg-background/90 shadow-sm backdrop-blur" onClick={() => { setMode("kb"); setOpen(true); }}>
          <Search className="size-4" />
          查询
        </Button>
        <Button size="sm" variant="outline" className="h-9 justify-start gap-2 rounded-xl bg-background/90 shadow-sm backdrop-blur" onClick={() => { setMode("chat"); setOpen(true); }}>
          <MessageCircle className="size-4" />
          对话
        </Button>
      </div>
    );
  }

  return (
    <div className="fixed bottom-5 left-5 z-50 flex h-[540px] w-[400px] max-w-[calc(100vw-32px)] flex-col overflow-hidden rounded-2xl border bg-background shadow-2xl">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex size-8 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Icon className="size-4" />
          </div>
          <div>
            <div className="text-sm font-semibold">{title}</div>
            <div className="text-[11px] text-muted-foreground">江苏省人工智能学会运营助手</div>
          </div>
        </div>
        <Button variant="ghost" size="icon-sm" onClick={() => setOpen(false)}>
          <X className="size-4" />
        </Button>
      </div>

      <div className="flex gap-1 border-b px-3 py-2">
        <Button size="sm" variant={mode === "kb" ? "default" : "ghost"} className="h-7 flex-1 text-xs" onClick={() => { setInput(""); setMode("kb"); }}>
          知识库
        </Button>
        <Button size="sm" variant={mode === "chat" ? "default" : "ghost"} className="h-7 flex-1 text-xs" onClick={() => { setInput(""); setMode("chat"); }}>
          对话
        </Button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {messages.map((msg, idx) => (
          <div key={idx} className={msg.role === "user" ? "ml-10 rounded-xl bg-primary px-3 py-2 text-xs text-primary-foreground" : "mr-6 rounded-xl border bg-muted/30 px-3 py-2 text-xs text-foreground"}>
            <MarkdownMessage content={msg.content} />
            {msg.sources && msg.sources.length > 0 && (
              <div className="mt-2 space-y-1.5 border-t pt-2 text-[11px] text-muted-foreground">
                {msg.sources.slice(0, 6).map((source, i) => (
                  <div key={i} className="rounded-lg bg-background/70 px-2 py-1">
                    <div className="truncate font-medium text-foreground">{source.name || "-"} · {source.email || "无邮箱"}</div>
                    <div className="truncate">{source.university || ""} {source.department || "未标注院系"} {source.title ? `· ${source.title}` : ""}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="mr-6 flex items-center gap-2 rounded-xl border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            <Loader2 className="size-3 animate-spin" />
            正在生成回答
          </div>
        )}
      </div>

      <div className="border-t p-3">
        <div className="mb-2 flex flex-wrap gap-1.5">
          {currentPrompts.map((prompt) => (
            <button key={prompt} onClick={() => ask(prompt)} className="rounded-lg border px-2 py-1 text-[11px] text-muted-foreground hover:border-primary/30 hover:text-primary">
              {prompt}
            </button>
          ))}
        </div>
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                ask();
              }
            }}
            placeholder={placeholder}
            className="min-h-10 flex-1 resize-none rounded-xl border bg-background px-3 py-2 text-xs outline-none focus:border-primary/50"
          />
          <Button size="icon-sm" className="size-10 rounded-xl" disabled={loading || !input.trim()} onClick={() => ask()}>
            {loading ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
          </Button>
        </div>
      </div>
    </div>
  );
}
