"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Globe, Loader2, ChevronDown, ChevronUp } from "lucide-react";
import { StageStepper } from "@/components/stage-stepper";
import { LiveStatsCounter } from "@/components/live-stats-counter";
// 兼容旧 props 类型
type CrawlStageLike = { stage: number; stage_name: string; progress_pct: number; timestamp: string; };
type CrawlStatsData = { teachers_found: number; emails_extracted: number; departments_done: number; department_names: string[]; timestamp: string; };

const panelVariants = {
  initial: { opacity: 0, y: 12 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.3, ease: [0.22, 1, 0.36, 1] as const },
  },
};

const expandVariants = {
  collapsed: { height: 0, opacity: 0, overflow: "hidden" as const },
  expanded: {
    height: "auto" as const,
    opacity: 1,
    overflow: "visible" as const,
    transition: { duration: 0.25, ease: [0.22, 1, 0.36, 1] as const },
  },
};

interface CrawlProgressPanelProps {
  stage: CrawlStageLike | undefined;
  stats: CrawlStatsData | undefined;
  university?: string;
  operationText?: string;
}

export function CrawlProgressPanel({
  stage,
  stats,
  university,
  operationText,
}: CrawlProgressPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Only show panel when there's at least one data source
  if (!stage && !stats && !university) return null;

  const progressPct = stage?.progress_pct ?? 0;
  const stageName = stage?.stage_name ?? operationText ?? "";

  return (
    <motion.div
      variants={panelVariants}
      initial="initial"
      animate="animate"
      className="ml-11 space-y-0 pt-2"
    >
      <div className="rounded-2xl rounded-tl-md border border-border/40 bg-card/50 px-4 py-3 backdrop-blur-sm">
        {/* Compact header — always visible */}
        <div
          className="flex items-center gap-2 cursor-pointer select-none"
          onClick={() => setIsExpanded((v) => !v)}
        >
          <div className="flex size-6 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/20 shrink-0">
            <Globe className="size-3 text-primary" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2">
              {university && (
                <span className="text-sm font-semibold text-foreground truncate">
                  {university}
                </span>
              )}
              {stageName && (
                <span className="text-[11px] text-muted-foreground truncate">
                  {stageName}
                </span>
              )}
            </div>
            {/* Compact progress bar */}
            <div className="flex items-center gap-2 mt-1">
              <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full rounded-full bg-primary transition-all duration-500 ease-out"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
              <span className="text-[10px] font-medium text-muted-foreground tabular-nums shrink-0">
                {Math.round(progressPct)}%
              </span>
            </div>
          </div>
          <Loader2 className="size-4 animate-spin text-muted-foreground/50 shrink-0" />
          <button
            className="flex size-5 items-center justify-center rounded-md text-muted-foreground/50 hover:text-muted-foreground hover:bg-muted/50 transition-colors shrink-0"
            aria-label={isExpanded ? "收起详情" : "展开详情"}
          >
            {isExpanded ? (
              <ChevronUp className="size-3.5" />
            ) : (
              <ChevronDown className="size-3.5" />
            )}
          </button>
        </div>

        {/* Expandable detail area */}
        <AnimatePresence initial={false}>
          {isExpanded && (
            <motion.div
              key="detail"
              variants={expandVariants}
              initial="collapsed"
              animate="expanded"
              exit="collapsed"
            >
              <div className="pt-3 space-y-3">
                <StageStepper stage={stage} />
                <LiveStatsCounter stats={stats} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
