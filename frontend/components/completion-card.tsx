"use client";

import { motion } from "framer-motion";
import { Check, Users, Mail, Building2, Download, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/services/api";
import type { TaskSummary } from "@/lib/types";

const cardVariants = {
  initial: { opacity: 0, y: 12 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.3, ease: [0.22, 1, 0.36, 1] as const },
  },
};

interface CompletionCardProps {
  summary: TaskSummary;
}

export function CompletionCard({ summary }: CompletionCardProps) {
  const { total_teachers, valid_emails, coverage, colleges, preview_rows, files } = summary;

  const metrics = [
    { icon: <Users className="size-4" />, label: "教师总数", value: total_teachers },
    { icon: <Mail className="size-4" />, label: "有效邮箱", value: valid_emails },
    { icon: <Check className="size-4" />, label: "覆盖率", value: `${coverage}%` },
    { icon: <Building2 className="size-4" />, label: "覆盖学院", value: colleges.length },
  ];

  return (
    <motion.div variants={cardVariants} initial="initial" animate="animate" className="ml-11 space-y-4 pt-2">
      <div className="rounded-2xl rounded-tl-md border border-border/40 bg-card/50 px-5 py-4 backdrop-blur-sm">
        {/* 标题 */}
        <div className="flex items-center gap-2 mb-4">
          <div className="flex size-7 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/20">
            <Check className="size-3.5 text-primary" />
          </div>
          <span className="text-sm font-semibold text-foreground">任务完成</span>
        </div>

        {/* 4 指标 */}
        {total_teachers > 0 && (
          <div className="grid grid-cols-4 gap-3 mb-4">
            {metrics.map((m) => (
              <div key={m.label} className="rounded-xl border border-border/30 bg-card px-3 py-2.5 text-center">
                <div className="flex items-center justify-center gap-1 text-muted-foreground mb-1">
                  {m.icon}
                </div>
                <div className="text-lg font-bold text-foreground">{m.value}</div>
                <div className="text-[10px] text-muted-foreground">{m.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* 学院分解 */}
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

        {/* 预览行 */}
        {preview_rows.length > 0 && (
          <div className="mb-4">
            <div className="text-xs font-medium text-muted-foreground mb-2">数据预览</div>
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
                  {preview_rows.map((row, i) => (
                    <tr key={i} className="border-b border-border/20 last:border-0">
                      <td className="px-3 py-1.5 text-foreground">{row.name || "-"}</td>
                      <td className="px-3 py-1.5 font-mono text-primary">{row.email || "-"}</td>
                      <td className="px-3 py-1.5 text-muted-foreground">{row.department || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 下载文件 */}
        {files.length > 0 && (
          <div>
            <div className="text-xs font-medium text-muted-foreground mb-2">结果文件</div>
            <div className="flex flex-wrap gap-2">
              {files.map((f) => {
                const ext = f.filename.split(".").pop()?.toLowerCase() || "";
                const extLabel: Record<string, string> = {
                  csv: "CSV", xlsx: "XLSX", md: "MD", html: "HTML", pdf: "PDF", docx: "DOCX",
                };
                return (
                  <a key={f.filename} href={`${api.getBackendUrl()}${f.url}`} target="_blank" rel="noreferrer">
                    <Button variant="outline" size="sm" className="h-8 gap-1.5 text-xs rounded-xl border-border/40 bg-card/50" type="button">
                      <FileText className="size-3" />
                      {extLabel[ext] || ext.toUpperCase()}
                    </Button>
                  </a>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}
