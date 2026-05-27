"use client";

import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { User, Bot, Terminal, Download } from "lucide-react";
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
          <div className="min-w-0 rounded-[24px] rounded-br-md bg-primary px-4 py-2.5 text-sm leading-relaxed text-primary-foreground shadow-[0_1px_3px_rgba(16,163,127,0.15)] dark:shadow-none whitespace-pre-wrap">
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
            <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10">
              <User className="size-3.5 text-primary" />
            </div>
          </div>
        </div>
      </motion.div>
    );
  }

  if (message.role === "log") {
    return (
      <motion.div
        variants={messageVariants}
        initial="initial"
        animate="animate"
        className="py-1"
      >
        <div className="flex items-start gap-3">
          <div className="flex size-5 shrink-0 items-center justify-center rounded bg-muted">
            <Terminal className="size-2.5 text-muted-foreground" />
          </div>
          <div className="flex items-baseline gap-2">
            {message.timestamp && (
              <span className="shrink-0 font-mono text-xs text-[#9A9AA5] dark:text-[#6E6E80]">
                [{message.timestamp}]
              </span>
            )}
            <span className="font-mono text-sm text-muted-foreground">
              {message.content}
            </span>
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
            className="group inline-flex items-center gap-2 rounded-[24px] border border-primary/20 bg-primary/5 px-4 py-2.5 text-sm font-medium text-primary transition-all hover:-translate-y-[1px] hover:bg-primary/10 hover:border-primary/30"
            style={{ transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)" }}
          >
            <span className="shrink-0 rounded bg-primary/15 px-1.5 py-0.5 text-[10px] font-bold text-primary">
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

  return (
    <motion.div
      variants={messageVariants}
      initial="initial"
      animate="animate"
      className="group py-4"
    >
      <div className="flex items-start gap-4">
        <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10">
          <Bot className="size-3.5 text-primary" />
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
