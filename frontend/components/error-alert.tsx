"use client";

import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, AlertCircle, X } from "lucide-react";
import { useState } from "react";
import type { ErrorUserData } from "@/lib/types";

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
}

export function ErrorAlert({ errors }: ErrorAlertProps) {
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());

  const visible = errors.filter(
    (e, i) => !dismissedIds.has(`${e.timestamp}-${i}`)
  );

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
