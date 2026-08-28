"use client";

import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, AlertCircle, X, Copy, RotateCcw } from "lucide-react";
import { useState } from "react";
type ErrorUserData = { message: string; severity: "warning" | "error"; timestamp: string; };

const alertVariants = {
  initial: { opacity: 0, x: -8, height: 0 },
  animate: {
    opacity: 1,
    x: 0,
    height: "auto",
    transition: { duration: 0.2, ease: [0.22, 1, 0.36, 1] as const },
  },
  exit: {
    opacity: 0,
    x: -8,
    height: 0,
    transition: { duration: 0.15 },
  },
};

interface ErrorAlertProps {
  errors: ErrorUserData[];
  /** 可选：重试回调，传递后显示重试按钮 */
  onRetry?: () => void;
}

export function ErrorAlert({ errors, onRetry }: ErrorAlertProps) {
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const visible = errors.filter(
    (e, i) => !dismissedIds.has(`${e.timestamp}-${i}`)
  );

  const handleCopy = async (text: string, id: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      // fallback
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    }
  };

  if (visible.length === 0) return null;

  return (
    <div className="ml-11 space-y-2 pt-2">
      <AnimatePresence>
        {visible.map((err, i) => {
          const isError = err.severity === "error";
          const key = `${err.timestamp}-${i}`;
          return (
            <motion.div
              key={key}
              variants={alertVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              className={`flex items-start gap-2.5 rounded-xl border px-4 py-3 ${
                isError
                  ? "border-red-200 bg-red-50/60 dark:border-red-900 dark:bg-red-950/20"
                  : "border-amber-200 bg-amber-50/60 dark:border-amber-900 dark:bg-amber-950/20"
              }`}
            >
              <div className="mt-0.5 shrink-0">
                {isError ? (
                  <AlertCircle className="size-4 text-red-500" />
                ) : (
                  <AlertTriangle className="size-4 text-amber-500" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p
                  className={`text-xs ${
                    isError ? "text-red-700 dark:text-red-400" : "text-amber-700 dark:text-amber-400"
                  }`}
                >
                  {err.message}
                </p>
                {/* 操作按钮 */}
                <div className="mt-2 flex items-center gap-1.5">
                  <button
                    onClick={() => handleCopy(err.message, key)}
                    className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium transition-colors hover:bg-white/40 dark:hover:bg-white/5"
                    style={{ color: isError ? "rgb(239 68 68)" : "rgb(217 119 6)" }}
                  >
                    {copiedId === key ? (
                      <>已复制</>
                    ) : (
                      <><Copy className="size-3" /> 复制</>
                    )}
                  </button>
                  {onRetry && (
                    <button
                      onClick={onRetry}
                      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium transition-colors hover:bg-white/40 dark:hover:bg-white/5"
                      style={{ color: "rgb(99 102 241)" }}
                    >
                      <RotateCcw className="size-3" /> 重试
                    </button>
                  )}
                </div>
              </div>
              <button
                onClick={() =>
                  setDismissedIds((prev) => new Set(prev).add(key))
                }
                className="shrink-0 rounded-md p-0.5 text-muted-foreground/50 hover:text-muted-foreground transition-colors"
              >
                <X className="size-3.5" />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
