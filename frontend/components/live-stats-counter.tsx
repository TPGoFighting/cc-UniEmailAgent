"use client";

import { motion } from "framer-motion";
import { Users, Mail, Building2, Sparkles } from "lucide-react";
import type { CrawlStatsData } from "@/lib/types";

const statVariants = {
  initial: { opacity: 0, y: 6 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.2, ease: [0.22, 1, 0.36, 1] as const },
  },
};

interface LiveStatsCounterProps {
  stats: CrawlStatsData | undefined;
}

export function LiveStatsCounter({ stats }: LiveStatsCounterProps) {
  if (!stats) return null;

  const { teachers_found, emails_extracted, departments_done, department_names } = stats;
  const recentDepartments = department_names?.slice(-3) || [];

  const items = [
    { icon: <Users className="size-4" />, label: "教师", value: teachers_found, color: "text-primary" },
    { icon: <Mail className="size-4" />, label: "邮箱", value: emails_extracted, color: "text-primary" },
    { icon: <Building2 className="size-4" />, label: "学院", value: departments_done, color: "text-accent" },
  ];

  return (
    <motion.div
      variants={statVariants}
      initial="initial"
      animate="animate"
      className="space-y-3"
    >
      {/* Stat counters */}
      <div className="grid grid-cols-3 gap-2">
        {items.map((item) => (
          <div
            key={item.label}
            className="rounded-xl border border-border/30 bg-card px-3 py-2 text-center"
          >
            <div className="flex items-center justify-center gap-1 text-muted-foreground mb-0.5">
              {item.icon}
            </div>
            <div className={`text-lg font-bold ${item.color}`}>
              <span key={item.value} className="stat-pop inline-block">
                {item.value.toLocaleString()}
              </span>
            </div>
            <div className="text-[10px] text-muted-foreground">{item.label}</div>
          </div>
        ))}
      </div>

      {/* Recent discoveries */}
      {recentDepartments.length > 0 && (
        <div className="rounded-xl border border-border/30 bg-card/50 px-3 py-2">
          <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground mb-1.5">
            <Sparkles className="size-3" />
            <span>最近发现</span>
          </div>
          <div className="flex flex-wrap gap-1">
            {recentDepartments.map((name) => (
              <span
                key={name}
                className="inline-flex items-center rounded-full border border-border bg-background px-2 py-0.5 text-[10px] text-foreground"
              >
                {name}
              </span>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}
