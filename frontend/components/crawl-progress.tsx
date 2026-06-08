"use client";

import { motion } from "framer-motion";
import { Check, Loader2, Clock } from "lucide-react";
import type { CollegeStage, StageState } from "@/lib/types";

const itemVariants = {
  initial: { opacity: 0, y: 8 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.25, ease: [0.22, 1, 0.36, 1] as const },
  },
};

interface CrawlProgressProps {
  stages: StageState | undefined;
}

export function CrawlProgress({ stages }: CrawlProgressProps) {
  if (!stages || stages.colleges.length === 0) return null;

  return (
    <div className="ml-11 space-y-2 pt-2">
      {stages.colleges.map((college, i) => (
        <CollegeCard key={college.name} college={college} index={i} />
      ))}
    </div>
  );
}

function CollegeCard({
  college,
  index,
}: {
  college: CollegeStage;
  index: number;
}) {
  const isDone = college.status === "done";
  const isActive = college.status === "active";
  const isPending = college.status === "pending";

  return (
    <motion.div
      variants={itemVariants}
      initial="initial"
      animate="animate"
      className="flex items-start gap-3"
    >
      {/* 左侧图标 */}
      <div className="flex size-7 shrink-0 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/20">
        {isDone ? (
          <Check className="size-3.5 text-primary" />
        ) : isActive ? (
          <Loader2 className="size-3.5 animate-spin text-primary" />
        ) : (
          <span className="text-[10px] font-semibold text-muted-foreground/40">
            {index + 1}
          </span>
        )}
      </div>

      {/* 卡片内容 */}
      <div
        className={`min-w-0 flex-1 rounded-2xl rounded-tl-md px-4 py-3 ${
          isDone
            ? "border border-border/40 bg-card/50"
            : isActive
              ? "border border-primary/20 bg-primary/[0.04]"
              : "border border-dashed border-border/20 bg-transparent opacity-50"
        }`}
      >
        <div className="flex items-center justify-between gap-2">
          <span
            className={`text-[13px] font-semibold ${
              isPending ? "text-muted-foreground/40" : "text-foreground"
            }`}
          >
            {college.name}
          </span>
          {isDone && college.elapsed_ms !== undefined && (
            <span className="shrink-0 text-[10px] text-muted-foreground/50">
              <Clock className="mr-0.5 inline size-2.5" />
              {formatMs(college.elapsed_ms)}
            </span>
          )}
        </div>

        {isDone ? (
          <div className="mt-1.5 flex items-center gap-3 text-[10px]">
            <span className="text-muted-foreground">
              教师 <strong className="text-foreground">{college.found ?? "?"}</strong>
            </span>
            <span className="text-muted-foreground">
              邮箱{" "}
              <strong className="text-primary">
                {college.valid_email ?? "?"}
              </strong>
            </span>
          </div>
        ) : isActive ? (
          <>
            <div className="mt-1.5 text-[11px] text-muted-foreground">
              {college.total_pages != null && college.extracted != null
                ? `正在访问教师详情页 ${college.extracted}/${college.total_pages}...`
                : "正在访问教师列表页..."}
            </div>
            {college.total_pages != null && college.extracted != null && (
              <div className="mt-2 h-1 overflow-hidden rounded-full bg-border">
                <div
                  className="h-full rounded-full bg-amber-500 transition-[width] duration-300"
                  style={{
                    width: `${college.total_pages > 0 ? (college.extracted / college.total_pages) * 100 : 0}%`,
                  }}
                />
              </div>
            )}
          </>
        ) : (
          <div className="mt-1.5 text-[11px] text-muted-foreground/40">
            等待中...
          </div>
        )}
      </div>
    </motion.div>
  );
}

function formatMs(ms: number): string {
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m${sec % 60}s`;
}
