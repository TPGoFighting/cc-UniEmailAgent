"use client";

import { Download, FileSpreadsheet, FileCode, FileImage, FileText, File as FileIcon } from "lucide-react";
import { api } from "@/services/api";

interface FileItem {
  filename: string;
  url?: string;
  size?: number;
}

interface FileCardProps {
  file: FileItem;
  label?: string;
  /** 当不传 url 时，用 taskId + filename 拼接下载地址 */
  taskId?: string;
}

const extIcons: Record<string, typeof FileText> = {
  csv: FileSpreadsheet,
  xlsx: FileSpreadsheet,
  xls: FileSpreadsheet,
  md: FileText,
  html: FileCode,
  pdf: FileImage,
  docx: FileText,
  doc: FileText,
  json: FileCode,
  xml: FileCode,
  txt: FileText,
};

const extColors: Record<string, string> = {
  csv: "text-emerald-500 bg-emerald-50 dark:bg-emerald-950/30 dark:text-emerald-400",
  xlsx: "text-green-600 bg-green-50 dark:bg-green-950/30 dark:text-green-400",
  xls: "text-green-600 bg-green-50 dark:bg-green-950/30 dark:text-green-400",
  md: "text-blue-500 bg-blue-50 dark:bg-blue-950/30 dark:text-blue-400",
  html: "text-orange-500 bg-orange-50 dark:bg-orange-950/30 dark:text-orange-400",
  pdf: "text-red-500 bg-red-50 dark:bg-red-950/30 dark:text-red-400",
  docx: "text-sky-600 bg-sky-50 dark:bg-sky-950/30 dark:text-sky-400",
  doc: "text-sky-600 bg-sky-50 dark:bg-sky-950/30 dark:text-sky-400",
  json: "text-purple-500 bg-purple-50 dark:bg-purple-950/30 dark:text-purple-400",
  xml: "text-purple-500 bg-purple-50 dark:bg-purple-950/30 dark:text-purple-400",
  txt: "text-muted-foreground bg-muted/50",
};

const extLabels: Record<string, string> = {
  csv: "CSV", xlsx: "XLSX", xls: "XLS", md: "MD",
  html: "HTML", pdf: "PDF", docx: "DOCX", doc: "DOC",
  json: "JSON", xml: "XML", txt: "TXT",
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getExt(filename: string): string {
  return filename.split(".").pop()?.toLowerCase() || "";
}

export function FileCard({ file, label, taskId }: FileCardProps) {
  const ext = getExt(file.filename);
  const Icon = extIcons[ext] || FileIcon;
  const colorClass = extColors[ext] || "text-muted-foreground bg-muted/50";
  const extLabel = extLabels[ext] || ext.toUpperCase();

  // 构建下载 URL
  const downloadUrl = file.url
    ? file.url.startsWith("http")
      ? file.url
      : `${api.getBackendUrl()}${file.url}`
    : taskId
      ? `${api.getBackendUrl()}/api/download/${taskId}/${file.filename}`
      : `${api.getBackendUrl()}/api/download/${file.filename}`;

  return (
    <a
      href={downloadUrl}
      target="_blank"
      rel="noreferrer"
      className="group inline-flex items-center gap-3 rounded-xl border border-border/30 bg-card/50 px-4 py-2.5 transition-all duration-250 hover:-translate-y-[0.5px] hover:border-primary/20 hover:bg-card hover:shadow-[0_2px_12px_rgba(0,0,0,0.04)] dark:shadow-[0_2px_12px_rgba(0,0,0,0.15)]"
      style={{ transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)" }}
    >
      {/* 文件类型图标 */}
      <div className={`flex size-9 shrink-0 items-center justify-center rounded-xl ${colorClass}`}>
        <Icon className="size-4.5" />
      </div>

      {/* 文件信息 */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-foreground">
            {label || file.filename}
          </span>
          <span className="shrink-0 rounded-md border border-border/30 bg-muted/50 px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
            {extLabel}
          </span>
        </div>
        {file.size !== undefined && (
          <p className="mt-0.5 text-[11px] text-muted-foreground/70">
            {formatSize(file.size)}
          </p>
        )}
      </div>

      {/* 下载按钮 */}
      <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary opacity-0 transition-all duration-250 group-hover:opacity-100 group-hover:bg-primary/15">
        <Download className="size-4" />
      </div>
    </a>
  );
}
