"use client";

import { motion } from "framer-motion";
import { Check, Users, Mail, Clock, Download, FileText, University } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/services/api";
import type { CrawlSummaryData } from "@/lib/types";

const cardVariants = {
  initial: { opacity: 0, y: 12 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.3, ease: [0.22, 1, 0.36, 1] as const },
  },
};

interface ResultSummaryCardProps {
  summary: CrawlSummaryData | undefined;
}

export function ResultSummaryCard({ summary }: ResultSummaryCardProps) {
  if (!summary) return null;

  const { university, total_teachers, total_emails, duration, files } = summary;

  const metrics = [
    { icon: <University className="size-4" />, label: "大学", value: university },
    { icon: <Users className="size-4" />, label: "教师总数", value: total_teachers.toLocaleString() },
    { icon: <Mail className="size-4" />, label: "邮箱数", value: total_emails.toLocaleString() },
    { icon: <Clock className="size-4" />, label: "耗时", value: duration },
  ];

  return (
    <motion.div
      variants={cardVariants}
      initial="initial"
      animate="animate"
      className="ml-11 space-y-4 pt-2"
    >
      <div className="rounded-2xl rounded-tl-md border border-border/40 bg-card/50 px-5 py-4 backdrop-blur-sm">
        {/* Title */}
        <div className="flex items-center gap-2 mb-4">
          <div className="flex size-7 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/20">
            <Check className="size-3.5 text-primary" />
          </div>
          <span className="text-sm font-semibold text-foreground">
            爬取完成
          </span>
          {university && (
            <span className="text-xs text-muted-foreground">
              — {university}
            </span>
          )}
        </div>

        {/* Metrics grid */}
        <div className="grid grid-cols-4 gap-3 mb-4">
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

        {/* Download buttons */}
        {files.length > 0 && (
          <div>
            <div className="text-xs font-medium text-muted-foreground mb-2">
              结果文件
            </div>
            <div className="flex flex-wrap gap-2">
              {files.map((f) => {
                const ext = f.filename.split(".").pop()?.toLowerCase() || "";
                const extLabel: Record<string, string> = {
                  csv: "CSV",
                  xlsx: "XLSX",
                  md: "MD",
                  html: "HTML",
                  pdf: "PDF",
                  docx: "DOCX",
                };
                return (
                  <a
                    key={f.filename}
                    href={`${api.getBackendUrl()}${f.url}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 gap-1.5 text-xs rounded-xl border-border/40 bg-card/50"
                      type="button"
                    >
                      <Download className="size-3" />
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
