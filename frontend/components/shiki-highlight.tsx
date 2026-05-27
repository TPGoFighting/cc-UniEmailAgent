"use client";

import { useEffect, useState, useRef } from "react";
import { createHighlighter, type Highlighter } from "shiki";

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
  const mountedRef = useRef(true);

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
      <pre className="overflow-x-auto rounded-xl bg-muted p-4 text-sm">
        <code>{code}</code>
      </pre>
    );
  }

  return (
    <div
      className="overflow-x-auto rounded-xl text-sm [&_pre]:!bg-transparent [&_pre]:!p-0"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
