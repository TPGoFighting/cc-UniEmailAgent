"use client";

import { useEffect, useState, useRef } from "react";
import { createHighlighter, type Highlighter } from "shiki";
import { Copy, Check } from "lucide-react";

// 只加载需要的主题和语言
let highlighterPromise: Promise<Highlighter> | null = null;

function getHighlighter(): Promise<Highlighter> {
  if (!highlighterPromise) {
    highlighterPromise = createHighlighter({
      themes: ["vitesse-light", "vitesse-dark"],
      langs: [
        "bash",
        "json",
        "csv",
        "python",
        "typescript",
        "javascript",
        "html",
        "css",
        "sql",
        "text",
        "markdown",
        "shell",
        "yaml",
        "xml",
      ],
    });
  }
  return highlighterPromise;
}

interface ShikiHighlightProps {
  code: string;
  language: string;
}

export function ShikiHighlight({ code, language }: ShikiHighlightProps) {
  const [html, setHtml] = useState<string | null>(null);
  const [isDark, setIsDark] = useState(false);
  const [copied, setCopied] = useState(false);
  const mountedRef = useRef(true);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback: select text
      const textarea = document.createElement('textarea');
      textarea.value = code;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  useEffect(() => {
    mountedRef.current = true;

    // 检测当前主题
    const checkTheme = () => {
      setIsDark(document.documentElement.classList.contains("dark"));
    };
    checkTheme();
    const observer = new MutationObserver(checkTheme);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });

    // 异步高亮
    const lang = language || "text";
    getHighlighter()
      .then((highlighter) => {
        if (!mountedRef.current) return;
        const theme = isDark ? "vitesse-dark" : "vitesse-light";
        const highlighted = highlighter.codeToHtml(code, {
          lang,
          theme,
        });
        setHtml(highlighted);
      })
      .catch(() => {
        // 降级：直接显示源码
        if (mountedRef.current) {
          setHtml(null);
        }
      });

    return () => {
      mountedRef.current = false;
      observer.disconnect();
    };
  }, [code, language, isDark]);

  if (!html) {
    // 降级渲染：纯文本
    return (
      <div className="group relative overflow-x-auto rounded-xl bg-muted">
        <pre className="p-4 text-sm">
          <code>{code}</code>
        </pre>
        <button
          onClick={handleCopy}
          className="absolute right-2 top-2 flex size-7 items-center justify-center rounded-md bg-background/80 opacity-0 transition-opacity duration-250 group-hover:opacity-100 hover:bg-background"
          aria-label="复制代码"
        >
          {copied ? <Check className="size-3.5 text-green-500" /> : <Copy className="size-3.5 text-muted-foreground" />}
        </button>
      </div>
    );
  }

  return (
    <div className="group relative">
      <div
        className="overflow-x-auto rounded-xl text-sm [&_pre]:!bg-transparent [&_pre]:!p-0"
        dangerouslySetInnerHTML={{ __html: html }}
      />
      <button
        onClick={handleCopy}
        className="absolute right-2 top-2 flex size-7 items-center justify-center rounded-md bg-background/80 opacity-0 transition-opacity duration-250 group-hover:opacity-100 hover:bg-background"
        aria-label="复制代码"
      >
        {copied ? <Check className="size-3.5 text-green-500" /> : <Copy className="size-3.5 text-muted-foreground" />}
      </button>
    </div>
  );
}
