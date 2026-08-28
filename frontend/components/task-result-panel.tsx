"use client";

import { motion } from "framer-motion";
import { Check, Users, Mail, Building2, Clock, AlertTriangle, ExternalLink, ClipboardCopy } from "lucide-react";
import { useState, useEffect } from "react";
import { FileCard } from "@/components/file-card";
import { Button } from "@/components/ui/button";
import { useUIStore } from "@/stores/ui-store";
import { useChatStore } from "@/stores/chat-store";
import { useTaskStore } from "@/stores/task-store";
import { api } from "@/services/api";
import type { TaskSummary } from "@/lib/types";

export function TaskResultPanel() {
  const [summary, setSummary] = useState<TaskSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [copiedPreview, setCopiedPreview] = useState(false);
  const setUniversityOpen = useUIStore((s) => s.setUniversityOpen);
  const setHighlightUniversity = useUIStore((s) => s.setHighlightUniversity);
  const activeTaskId = useTaskStore((s) => s.activeTaskId);
  const parallelCrawl = activeTaskId ? useChatStore((s) => s.parallelCrawlMap[activeTaskId]) : undefined;

  // 获取任务摘要
  useEffect(() => {
    if (activeTaskId) {
      api.getTaskSummary(activeTaskId).then(setSummary).catch(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [activeTaskId]);

  const isLoaded = summary || !loading;

  if (!isLoaded && !parallelCrawl) return null;

  const university = "";
  const totalTeachers = summary?.total_teachers || 0;
  const totalEmails = summary?.valid_emails || 0;
  const coverage = summary?.coverage;
  const colleges = summary?.colleges || parallelCrawl?.workers || [];
  const previewRows = summary?.preview_rows || [];
  const files = summary?.files || [];

  const metrics = [
    ...(totalTeachers > 0 ? [{ icon: <Users className="size-4" />, label: "教师总数", value: totalTeachers.toLocaleString() }] : []),
    ...(totalEmails > 0 ? [{ icon: <Mail className="size-4" />, label: "有效邮箱", value: totalEmails.toLocaleString() }] : []),
    ...(coverage !== undefined ? [{ icon: <Check className="size-4" />, label: "覆盖率", value: `${coverage}%` }] : []),
    ...(colleges.length > 0 ? [{ icon: <Building2 className="size-4" />, label: "覆盖学院", value: colleges.length.toString() }] : []),
  ];

  if (metrics.length === 0 && !files.length && !previewRows.length) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 40, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 300, damping: 25, mass: 0.8 }}
      className="ml-11 space-y-4 pt-2"
    >
      <div className="rounded-2xl rounded-tl-md border border-border/40 bg-card/50 px-5 py-4 backdrop-blur-sm">
        <div className="flex items-center gap-2 mb-4">
          <div className="flex size-7 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/20">
            <Check className="size-3.5 text-primary" />
          </div>
          <span className="text-sm font-semibold text-foreground">任务完成</span>
          {university && <span className="text-xs text-muted-foreground">— {university}</span>}
        </div>

        {metrics.length > 0 && (
          <div className="grid gap-3 mb-4" style={{ gridTemplateColumns: `repeat(${Math.min(metrics.length, 4)}, 1fr)` }}>
            {metrics.map((m) => (
              <div key={m.label} className="rounded-xl border border-border/30 bg-card px-3 py-2.5 text-center">
                <div className="flex items-center justify-center gap-1 text-muted-foreground mb-1">{m.icon}</div>
                <div className="text-base font-bold text-foreground truncate">{m.value}</div>
                <div className="text-[10px] text-muted-foreground">{m.label}</div>
              </div>
            ))}
          </div>
        )}

        {previewRows.length > 0 && (
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-medium text-muted-foreground">数据预览</div>
              <button
                onClick={() => {
                  const csv = "姓名,邮箱,学院\n" + previewRows.map((r) => `"${r.name || ''}","${r.email || ''}","${r.department || ''}"`).join("\n");
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

        {files.length > 0 && (
          <div>
            <div className="text-xs font-medium text-muted-foreground mb-2">结果文件</div>
            <div className="flex flex-wrap gap-2">
              {files.map((f: { filename: string; url?: string; size?: number }) => (
                <FileCard key={f.filename} file={{ filename: f.filename, url: f.url, size: f.size }} />
              ))}
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}
