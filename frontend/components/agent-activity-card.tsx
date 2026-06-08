"use client";

import { motion } from "framer-motion";
import type { CrawlStageState } from "@/lib/types";

const STAGE_LABELS: Record<number, string> = {
  1: "正在浏览高校官网...",
  2: "正在搜索学院页面...",
  3: "正在提取教师信息...",
  4: "正在整理数据...",
  5: "正在生成结果文件...",
};

interface AgentActivityCardProps {
  stage: CrawlStageState | undefined;
  university?: string;
}

export function AgentActivityCard({ stage, university }: AgentActivityCardProps) {
  if (!stage) return null;

  const label = STAGE_LABELS[stage.stage] || `阶段 ${stage.stage}: ${stage.stage_name}`;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
      className="ml-11 pt-2"
    >
      <div className="rounded-2xl rounded-tl-md border border-border/40 bg-card/50 backdrop-blur-sm overflow-hidden">
        {/* Mini browser chrome */}
        <div className="flex items-center gap-2 px-3 py-2 bg-muted/40 border-b border-border/30">
          {/* Traffic lights */}
          <div className="flex items-center gap-1">
            <div className="size-2.5 rounded-full bg-red-400/70" />
            <div className="size-2.5 rounded-full bg-amber-400/70" />
            <div className="size-2.5 rounded-full bg-green-400/70" />
          </div>
          {/* Address bar */}
          <div className="flex-1 flex items-center gap-1.5 rounded-md bg-background/80 px-2 py-1 text-[10px] text-muted-foreground truncate">
            <svg className="size-3 shrink-0 text-muted-foreground/50" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="2" y1="12" x2="22" y2="12" />
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
            </svg>
            <span className="truncate">
              {university || stage.stage_name || "加载中..."}
            </span>
          </div>
          <div className="size-3" />
        </div>

        {/* Content area */}
        <div className="px-4 py-3 space-y-2">
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5">
              <div className="size-2 rounded-full bg-primary animate-pulse" />
              <span className="text-xs font-medium text-foreground truncate">
                {label}
              </span>
            </div>
          </div>

          {/* Progress indicator */}
          <div className="flex items-center gap-2">
            <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
              <motion.div
                className="h-full rounded-full bg-primary"
                initial={{ width: 0 }}
                animate={{ width: `${stage.progress_pct}%` }}
                transition={{ duration: 0.5, ease: "easeOut" }}
              />
            </div>
            <span className="text-[10px] font-medium text-muted-foreground tabular-nums shrink-0">
              {Math.round(stage.progress_pct)}%
            </span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
