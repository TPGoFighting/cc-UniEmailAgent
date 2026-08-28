"use client";

import { motion } from "framer-motion";
import { Check, Loader2, XCircle, Clock, Users, Mail, Building2, AlertTriangle } from "lucide-react";
import type { ParallelCrawlState, WorkerProgress } from "@/lib/types";

interface ParallelCrawlPanelProps {
  crawlState: ParallelCrawlState;
}

export function ParallelCrawlPanel({ crawlState }: ParallelCrawlPanelProps) {
  const { university, workers } = crawlState;
  const doneCount = workers.filter((w) => w.status === "done").length;
  const errorCount = workers.filter((w) => w.status === "error").length;
  const totalFound = workers.reduce((sum, w) => sum + (w.found || 0), 0);
  const totalEmails = workers.reduce((sum, w) => sum + (w.emails || 0), 0);

  if (workers.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className="ml-11 space-y-3 pt-4"
    >
      {/* 标题 + 汇总 */}
      <div className="rounded-2xl rounded-tl-md border border-border/40 bg-card/50 px-5 py-4 backdrop-blur-sm">
        <div className="flex items-center gap-2 mb-3">
          <div className="flex size-7 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/20">
            {errorCount > 0 ? (
              <AlertTriangle className="size-3.5 text-amber-500" />
            ) : (
              <Check className="size-3.5 text-primary" />
            )}
          </div>
          <span className="text-sm font-semibold text-foreground">
            并行采集完成
          </span>
          {university && (
            <span className="text-xs text-muted-foreground">— {university}</span>
          )}
        </div>

        {/* 统计 */}
        <div className="grid grid-cols-4 gap-2 mb-4">
          <StatCard icon={<Building2 className="size-3.5" />} label="学院" value={workers.length} sub={doneCount === workers.length ? "全部完成" : `${doneCount}/${workers.length}`} />
          <StatCard icon={<Users className="size-3.5" />} label="教师" value={totalFound} />
          <StatCard icon={<Mail className="size-3.5" />} label="邮箱" value={totalEmails} />
          <StatCard icon={<Clock className="size-3.5" />} label="失败" value={errorCount} highlight={errorCount > 0} />
        </div>

        {/* Worker 列表 */}
        <div className="space-y-1.5">
          {workers.map((worker) => (
            <WorkerCard key={worker.name} worker={worker} />
          ))}
        </div>
      </div>
    </motion.div>
  );
}

function StatCard({
  icon,
  label,
  value,
  sub,
  highlight,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div className={`rounded-xl border ${highlight ? "border-red-200 bg-red-50/30 dark:border-red-800 dark:bg-red-950/20" : "border-border/30 bg-card"} px-3 py-2 text-center`}>
      <div className="flex items-center justify-center gap-1 text-muted-foreground mb-0.5">
        {icon}
      </div>
      <div className={`text-base font-bold ${highlight ? "text-red-500" : "text-foreground"}`}>
        {value}
      </div>
      <div className="text-[10px] text-muted-foreground">
        {label}
        {sub && <span className="block text-[9px] opacity-60">{sub}</span>}
      </div>
    </div>
  );
}

function WorkerCard({ worker }: { worker: WorkerProgress }) {
  return (
    <div
      className={`flex items-center gap-3 rounded-xl border px-3.5 py-2.5 transition-colors ${
        worker.status === "error"
          ? "border-red-200 bg-red-50/20 dark:border-red-800 dark:bg-red-950/10"
          : worker.status === "done"
            ? "border-border/30 bg-card/30"
            : worker.status === "running"
              ? "border-primary/20 bg-primary/[0.03]"
              : "border-dashed border-border/20 bg-transparent opacity-50"
      }`}
    >
      {/* 状态指示器 */}
      <div className="flex size-6 shrink-0 items-center justify-center">
        {worker.status === "done" ? (
          <div className="flex size-5 items-center justify-center rounded-full bg-primary/15">
            <Check className="size-3 text-primary" />
          </div>
        ) : worker.status === "error" ? (
          <XCircle className="size-5 text-red-400" />
        ) : worker.status === "running" ? (
          <Loader2 className="size-4 animate-spin text-primary" />
        ) : (
          <div className="size-2 rounded-full bg-muted-foreground/20" />
        )}
      </div>

      {/* Worker 内容 */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold text-foreground truncate">
            {worker.name}
          </span>
          {worker.status === "done" && (
            <div className="flex items-center gap-2 text-[10px] text-muted-foreground shrink-0">
              {worker.found != null && <span>教师 {worker.found}</span>}
              {worker.emails != null && <span>邮箱 {worker.emails}</span>}
            </div>
          )}
        </div>
        {worker.status === "error" && worker.error && (
          <p className="mt-0.5 text-[10px] text-red-400 truncate">{worker.error}</p>
        )}
      </div>
    </div>
  );
}
