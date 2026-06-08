"use client";

import { motion } from "framer-motion";
import { Check, Users, Mail, Building2, Clock, AlertTriangle, ExternalLink, ClipboardCopy } from "lucide-react";
import { useState } from "react";
import { FileCard } from "@/components/file-card";
import { Button } from "@/components/ui/button";
import type { CrawlSummaryData, TaskSummary, QualityEvalData } from "@/lib/types";

interface TaskResultPanelProps {
  crawlSummary: CrawlSummaryData | undefined;
  taskSummary: TaskSummary | undefined;
  qualityEval: QualityEvalData | undefined;
  traceUrl: string | undefined;
}

function ScoreRing({ score }: { score: number }) {
  // >= 80 绿色, >= 60 黄色, < 60 红色
  const color = score >= 80 ? "#22D3EE" : score >= 60 ? "#F59E0B" : "#FB7185";
  const bgColor = score >= 80 ? "rgba(34,211,238,0.12)" : score >= 60 ? "rgba(245,158,11,0.12)" : "rgba(251,113,133,0.12)";
  const radius = 28;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width="72" height="72" className="-rotate-90">
        <circle cx="36" cy="36" r={radius} fill="none" stroke={bgColor} strokeWidth="5" />
        <circle
          cx="36" cy="36" r={radius} fill="none" stroke={color} strokeWidth="5"
          strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 0.8s cubic-bezier(0.22, 1, 0.36, 1)" }}
        />
      </svg>
      <span className="absolute text-xl font-bold" style={{ color }}>{score}</span>
    </div>
  );
}

export function TaskResultPanel({ crawlSummary, taskSummary, qualityEval, traceUrl }: TaskResultPanelProps) {
  // Need at least one data source
  if (!crawlSummary && !taskSummary) return null;

  const [copiedPreview, setCopiedPreview] = useState(false);

  const university = crawlSummary?.university || "";
  const totalTeachers = crawlSummary?.total_teachers ?? taskSummary?.total_teachers ?? 0;
  const totalEmails = crawlSummary?.total_emails ?? taskSummary?.valid_emails ?? 0;
  const duration = crawlSummary?.duration || "";
  const coverage = taskSummary?.coverage;
  const colleges = taskSummary?.colleges || [];
  const previewRows = taskSummary?.preview_rows || [];
  // Merge files from both sources
  const crawlFiles = crawlSummary?.files || [];
  const taskFiles = taskSummary?.files || [];
  const allFiles = [...crawlFiles, ...taskFiles].filter(
    (f, i, arr) => f.filename && arr.findIndex((x) => x.filename === f.filename) === i
  );

  const metrics = [
    { icon: <Users className="size-4" />, label: "教师总数", value: totalTeachers > 0 ? totalTeachers.toLocaleString() : "—" },
    { icon: <Mail className="size-4" />, label: "邮箱", value: totalEmails > 0 ? totalEmails.toLocaleString() : "—" },
    ...(coverage !== undefined
      ? [{ icon: <Check className="size-4" />, label: "覆盖率", value: `${coverage}%` as string }]
      : []),
    ...(duration
      ? [{ icon: <Clock className="size-4" />, label: "耗时", value: duration }]
      : []),
    ...(colleges.length > 0
      ? [{ icon: <Building2 className="size-4" />, label: "覆盖学院", value: colleges.length.toString() }]
      : []),
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 40, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 300, damping: 25, mass: 0.8 }}
      className="ml-11 space-y-4 pt-2"
    >
      <div className="rounded-2xl rounded-tl-md border border-border/40 bg-card/50 px-5 py-4 backdrop-blur-sm">
        {/* Title + Trace link */}
        <div className="flex items-center gap-2 mb-4">
          <div className="flex size-7 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/20">
            <Check className="size-3.5 text-primary" />
          </div>
          <span className="text-sm font-semibold text-foreground">
            任务完成
          </span>
          {university && (
            <span className="text-xs text-muted-foreground">
              — {university}
            </span>
          )}
          {/* Trace 链接 — 放在右上角 */}
          {traceUrl && (
            <a href={traceUrl} target="_blank" rel="noreferrer" className="ml-auto">
              <Button variant="outline" size="sm" className="h-7 gap-1 text-[11px] rounded-lg border-border/40" type="button">
                <ExternalLink className="size-3" />
                LangSmith Trace
              </Button>
            </a>
          )}
        </div>

        {/* Metrics grid */}
        {metrics.length > 0 && (
          <div
            className="grid gap-3 mb-4"
            style={{
              gridTemplateColumns: `repeat(${Math.min(metrics.length, 4)}, 1fr)`,
            }}
          >
            {metrics.map((m) => (
              <div
                key={m.label}
                className="rounded-xl border border-border/30 bg-card px-3 py-2.5 text-center"
              >
                <div className="flex items-center justify-center gap-1 text-muted-foreground mb-1">
                  {m.icon}
                </div>
                <div className="text-base font-bold text-foreground truncate">
                  {m.value}
                </div>
                <div className="text-[10px] text-muted-foreground">{m.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* College distribution */}
        {colleges.length > 0 && (
          <div className="mb-4">
            <div className="text-xs font-medium text-muted-foreground mb-2">学院分布</div>
            <div className="flex flex-wrap gap-1.5">
              {colleges.slice(0, 8).map((c) => (
                <span
                  key={c.name}
                  className="inline-flex items-center gap-1 rounded-lg border border-border/30 bg-card px-2.5 py-1 text-[11px] text-foreground"
                >
                  {c.name}
                  <span className="text-primary font-medium">{c.count}</span>
                </span>
              ))}
              {colleges.length > 8 && (
                <span className="inline-flex items-center rounded-lg border border-border/30 bg-muted/50 px-2.5 py-1 text-[11px] text-muted-foreground">
                  +{colleges.length - 8} 更多
                </span>
              )}
            </div>
          </div>
        )}

        {/* Preview rows */}
        {previewRows.length > 0 && (
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-medium text-muted-foreground">数据预览</div>
              <button
                onClick={() => {
                  const header = "姓名,邮箱,学院\n";
                  const csv = header + previewRows.map(r => `"${r.name || ""}","${r.email || ""}","${r.department || ""}"`).join("\n");
                  navigator.clipboard.writeText(csv).then(() => {
                    setCopiedPreview(true);
                    setTimeout(() => setCopiedPreview(false), 2000);
                  }).catch(() => {});
                }}
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
              >
                <ClipboardCopy className="size-3" />
                {copiedPreview ? "已复制" : "复制为 CSV"}
              </button>
            </div>
            <div className="overflow-hidden rounded-xl border border-border/30">
              <table className="w-full text-left text-[11px]">
                <thead>
                  <tr className="border-b border-border/30 bg-muted/30">
                    <th className="px-3 py-2 font-medium text-muted-foreground">姓名</th>
                    <th className="px-3 py-2 font-medium text-muted-foreground">邮箱</th>
                    <th className="px-3 py-2 font-medium text-muted-foreground">学院</th>
                  </tr>
                </thead>
                <tbody>
                  {previewRows.map((row, i) => (
                    <tr key={i} className="border-b border-border/20 last:border-0">
                      <td className="px-3 py-1.5 text-foreground">{row.name || "—"}</td>
                      <td className="px-3 py-1.5 font-mono text-primary">{row.email || "—"}</td>
                      <td className="px-3 py-1.5 text-muted-foreground">{row.department || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Download buttons — 使用 FileCard */}
        {allFiles.length > 0 && (
          <div>
            <div className="text-xs font-medium text-muted-foreground mb-2">结果文件</div>
            <div className="flex flex-wrap gap-2">
              {allFiles.map((f: { filename: string; url?: string; size?: number }) => (
                <FileCard key={f.filename} file={{ filename: f.filename, url: f.url, size: f.size }} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── 质量评分卡 ── */}
      {qualityEval && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15, type: "spring", stiffness: 300, damping: 25 }}
          className="rounded-2xl rounded-tl-md border border-border/40 bg-card/50 px-5 py-4 backdrop-blur-sm"
        >
          <div className="flex items-center gap-2 mb-4">
            <div className="flex size-7 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/20">
              <ActivityIcon className="size-3.5 text-primary" />
            </div>
            <span className="text-sm font-semibold text-foreground">质量评估</span>
          </div>

          <div className="flex items-start gap-5">
            {/* 左侧：圆形评分 */}
            <ScoreRing score={qualityEval.quality_score} />

            {/* 右侧：详细指标 */}
            <div className="flex-1 space-y-3 min-w-0">
              {/* 邮箱覆盖率横条 */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[11px] text-muted-foreground">邮箱覆盖率</span>
                  <span className="text-[11px] font-medium text-foreground">
                    {(qualityEval.email_rate * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{
                      width: `${Math.min(qualityEval.email_rate * 100, 100)}%`,
                      backgroundColor: qualityEval.email_rate >= 0.7 ? "#22D3EE" : qualityEval.email_rate >= 0.3 ? "#F59E0B" : "#FB7185",
                    }}
                  />
                </div>
              </div>

              {/* 通过状态 */}
              <div className="text-[11px]">
                <span className="text-muted-foreground">评估结果：</span>
                <span className={qualityEval.passed ? "text-primary font-medium" : "text-destructive font-medium"}>
                  {qualityEval.passed ? "通过 ✓" : "未通过 ✗"}
                </span>
              </div>
            </div>
          </div>

          {/* Warnings 列表 */}
          {qualityEval.warnings.length > 0 && (
            <div className="mt-4">
              <div className="text-xs font-medium text-muted-foreground mb-2">注意事项</div>
              <div className="space-y-1.5">
                {qualityEval.warnings.map((w, i) => (
                  <div key={i} className="flex items-start gap-1.5 text-[11px] text-amber-400">
                    <AlertTriangle className="size-3 mt-0.5 shrink-0" />
                    <span>{w}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Colleges found 标签 */}
          {qualityEval.colleges_found.length > 0 && (
            <div className="mt-3">
              <div className="text-xs font-medium text-muted-foreground mb-2">
                已覆盖学院 ({qualityEval.colleges_found.length})
              </div>
              <div className="flex flex-wrap gap-1.5">
                {qualityEval.colleges_found.slice(0, 10).map((c) => (
                  <span
                    key={c}
                    className="inline-flex items-center rounded-lg border border-border/30 bg-card px-2.5 py-1 text-[11px] text-foreground"
                  >
                    {c}
                  </span>
                ))}
                {qualityEval.colleges_found.length > 10 && (
                  <span className="inline-flex items-center rounded-lg border border-border/30 bg-muted/50 px-2.5 py-1 text-[11px] text-muted-foreground">
                    +{qualityEval.colleges_found.length - 10} 更多
                  </span>
                )}
              </div>
            </div>
          )}
        </motion.div>
      )}
    </motion.div>
  );
}

/** 用 Activity 图标（因为已经有了相关 import） */
function ActivityIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  );
}
