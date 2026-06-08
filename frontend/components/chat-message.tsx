"use client";

import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { User, Bot, Terminal, Download, Loader2, Bug, FileText } from "lucide-react";
import type { Message } from "@/lib/types";
import { MessageActions } from "@/components/message-actions";
import { TypingIndicator } from "@/components/typing-indicator";
import { useAgentChat } from "@/hooks/use-agent-chat";
import { api } from "@/services/api";
import { ShikiHighlight } from "@/components/shiki-highlight";

const messageVariants = {
  initial: { opacity: 0, y: 8 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.25, ease: [0.22, 1, 0.36, 1] as const },
  },
};

interface ChatMessageProps {
  message: Message;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const { copyMessage, editMessage, regenerate, deleteMessage } = useAgentChat();

  if (message.role === "user") {
    return (
      <motion.div
        variants={messageVariants}
        initial="initial"
        animate="animate"
        className="group flex justify-end py-4"
      >
        <div className="flex max-w-[80%] items-start gap-3">
          <div className="min-w-0 rounded-2xl rounded-br-md bg-gradient-to-br from-primary to-primary/90 px-4 py-2.5 text-sm leading-relaxed text-primary-foreground shadow-[0_2px_8px_rgba(34,211,238,0.2)] dark:shadow-[0_2px_12px_rgba(34,211,238,0.15)] whitespace-pre-wrap">
            {message.content}
          </div>
          <div className="flex shrink-0 items-center gap-1 self-end">
            <div className="opacity-0 transition-opacity duration-250 group-hover:opacity-100">
              <MessageActions
                role="user"
                content={message.content}
                onCopy={() => copyMessage(message.content)}
                onEdit={() => editMessage(message.id, message.content)}
                onDelete={() => deleteMessage(message.id)}
              />
            </div>
            <div className="flex size-7 shrink-0 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/20">
              <User className="size-3.5 text-primary" />
            </div>
          </div>
        </div>
      </motion.div>
    );
  }

  if (message.role === "progress") {
    return (
      <motion.div
        variants={messageVariants}
        initial="initial"
        animate="animate"
        className="py-2"
      >
        <div className="flex items-center gap-3 rounded-xl border border-border bg-muted/30 px-4 py-3">
          <Loader2 className="size-4 animate-spin text-primary" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-medium text-foreground">{message.content}</span>
              {message.step && message.total ? (
                <span className="shrink-0 text-xs text-muted-foreground">{message.step}/{message.total}</span>
              ) : null}
            </div>
            {message.timestamp ? (
              <span className="mt-1 block text-xs text-muted-foreground">{message.timestamp}</span>
            ) : null}
          </div>
        </div>
      </motion.div>
    );
  }

  if (message.role === "download") {
    const BACKEND_URL = api.getBackendUrl();
    const downloadUrl = message.url
      ? message.url.startsWith("http")
        ? message.url
        : `${BACKEND_URL}${message.url}`
      : `${BACKEND_URL}/api/download/${message.filename || ""}`;

    const ext = (message.filename || "").split(".").pop()?.toLowerCase() || "";
    const extLabel: Record<string, string> = {
      csv: "CSV", xlsx: "XLSX", md: "MD", html: "HTML", pdf: "PDF", docx: "DOCX",
    };

    return (
      <motion.div
        variants={messageVariants}
        initial="initial"
        animate="animate"
        className="py-2"
      >
        <div className="flex items-center gap-3">
          <div className="flex size-5 shrink-0 items-center justify-center rounded bg-primary/10">
            <Download className="size-2.5 text-primary" />
          </div>
          <a
            href={downloadUrl}
            target="_blank"
            rel="noreferrer"
            className="group inline-flex items-center gap-2 rounded-2xl border border-primary/20 bg-primary/[0.04] px-4 py-2.5 text-sm font-medium text-primary transition-all duration-250 hover:-translate-y-[0.5px] hover:bg-primary/[0.08] hover:border-primary/30 hover:shadow-[0_0_12px_rgba(34,211,238,0.1)]"
            style={{ transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)" }}
          >
            <span className="shrink-0 rounded-lg bg-primary/15 px-1.5 py-0.5 text-[10px] font-bold text-primary">
              {extLabel[ext] || ext.toUpperCase()}
            </span>
            <span>{message.content}</span>
            <span className="hidden group-hover:inline text-xs text-primary/60">
              ({message.filename})
            </span>
          </a>
        </div>
      </motion.div>
    );
  }

  if (message.role === "text" || message.role === "agent") {
    return (
      <motion.div
        variants={messageVariants}
        initial="initial"
        animate="animate"
        className="group py-4"
      >
        <div className="flex items-start gap-4">
          <div className="flex size-7 shrink-0 items-center justify-center rounded-xl overflow-hidden bg-primary/15 ring-1 ring-primary/20">
            <img src="/avatar.png" alt="Agent" className="size-full object-cover img-blend" />
          </div>
          <div className="min-w-0 flex-1 rounded-2xl rounded-tl-md border border-border/30 bg-card/50 px-5 py-3.5 backdrop-blur-sm">
            <div className="prose prose-sm dark:prose-invert max-w-none text-sm leading-relaxed text-foreground/85 [&_h2]:text-base [&_h2]:font-semibold [&_h3]:text-sm [&_table]:w-full [&_table]:overflow-auto [&_th]:border [&_th]:border-border [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:text-xs [&_th]:font-medium [&_td]:border [&_td]:border-border [&_td]:px-3 [&_td]:py-2 [&_td]:text-sm [&_table]:rounded-lg [&_pre]:rounded-xl [&_pre]:bg-muted [&_code]:rounded-md [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_blockquote]:border-l-2 [&_blockquote]:border-primary/30 [&_blockquote]:pl-4 [&_blockquote]:text-muted-foreground">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code: function Code({ className, children, ...props }: React.ComponentPropsWithoutRef<"code">) {
                    const match = /language-(\w+)/.exec(className || "");
                    const codeStr = String(children).replace(/\n$/, "");
                    if (match) {
                      return <ShikiHighlight code={codeStr} language={match[1]} />;
                    }
                    return (
                      <code className="rounded-md bg-muted px-1 py-0.5 text-xs font-mono" {...props}>
                        {children}
                      </code>
                    );
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          </div>
        </div>
        <div className="ml-11 mt-1 flex">
          <div className="opacity-0 transition-opacity duration-250 group-hover:opacity-100">
            <MessageActions
              role="agent"
              content={message.content}
              onCopy={() => copyMessage(message.content)}
              onRetry={regenerate}
              onDelete={() => deleteMessage(message.id)}
            />
          </div>
        </div>
      </motion.div>
    );
  }

  if (message.role === "file") {
    // 不渲染中间文件创建通知
    return null;
  }

  if (message.role === "log") {
    return (
      <motion.div
        variants={messageVariants}
        initial="initial"
        animate="animate"
        className="py-1"
      >
        <div className="flex items-start gap-2 pl-2">
          <Bug className="mt-1 size-3 shrink-0 text-muted-foreground/40" />
          <div className="min-w-0 flex-1 rounded-md bg-muted/30 px-3 py-1.5">
            <details className="group">
              <summary className="cursor-pointer text-[11px] font-mono text-muted-foreground/60 hover:text-muted-foreground/80 list-none flex items-center gap-1.5">
                <span className="text-[10px] transition-transform group-open:rotate-90">▶</span>
                <span className="truncate flex-1">
                  <code className="text-[11px] leading-relaxed text-muted-foreground/70 break-all font-mono">
                    {message.content?.length > 80
                      ? message.content.slice(0, 80) + "..."
                      : message.content}
                  </code>
                </span>
                {message.timestamp && (
                  <span className="shrink-0 text-[10px] text-muted-foreground/40">[{message.timestamp}]</span>
                )}
              </summary>
              <div className="mt-1 max-h-48 overflow-y-auto rounded bg-background/50 p-2">
                <pre className="text-[11px] leading-relaxed text-muted-foreground/70 whitespace-pre-wrap font-mono">
                  {message.content}
                </pre>
              </div>
            </details>
          </div>
        </div>
      </motion.div>
    );
  }

  // 默认：agent 消息气泡
  return (
    <motion.div
      variants={messageVariants}
      initial="initial"
      animate="animate"
      className="group py-4"
    >
      <div className="flex items-start gap-4">
        <div className="flex size-7 shrink-0 items-center justify-center rounded-full overflow-hidden bg-muted">
          <img src="/avatar.png" alt="Agent" className="size-full object-cover img-blend" />
        </div>
        <div className="min-w-0 flex-1 rounded-[24px] rounded-tl-md bg-muted/50 px-5 py-3.5">
          <div className="prose prose-sm dark:prose-invert max-w-none text-sm leading-relaxed text-foreground/85 [&_h2]:text-base [&_h2]:font-semibold [&_h3]:text-sm [&_table]:w-full [&_table]:overflow-auto [&_th]:border [&_th]:border-border [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:text-xs [&_th]:font-medium [&_td]:border [&_td]:border-border [&_td]:px-3 [&_td]:py-2 [&_td]:text-sm [&_table]:rounded-lg [&_pre]:rounded-xl [&_pre]:bg-muted [&_code]:rounded-md [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_blockquote]:border-l-2 [&_blockquote]:border-primary/30 [&_blockquote]:pl-4 [&_blockquote]:text-muted-foreground">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code: function Code({ className, children, ...props }: React.ComponentPropsWithoutRef<"code">) {
                  const match = /language-(\w+)/.exec(className || "");
                  const codeStr = String(children).replace(/\n$/, "");

                  if (match) {
                    return (
                      <ShikiHighlight code={codeStr} language={match[1]} />
                    );
                  }

                  // 内联代码
                  return (
                    <code
                      className="rounded-md bg-muted px-1 py-0.5 text-xs font-mono"
                      {...props}
                    >
                      {children}
                    </code>
                  );
                },
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
          {message.isStreaming && <TypingIndicator />}
        </div>
      </div>
      {/* 消息操作 — 在气泡下方 */}
      <div className="ml-11 mt-1 flex">
        <div className="opacity-0 transition-opacity duration-250 group-hover:opacity-100">
          <MessageActions
            role="agent"
            content={message.content}
            onCopy={() => copyMessage(message.content)}
            onRetry={regenerate}
            onDelete={() => deleteMessage(message.id)}
          />
        </div>
      </div>
    </motion.div>
  );
}