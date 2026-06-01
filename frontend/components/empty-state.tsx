"use client";

import { motion } from "framer-motion";
import { MessageSquare, Globe, FileSpreadsheet, Search } from "lucide-react";
import type { Task } from "@/lib/types";

const suggestedPrompts = [
  {
    icon: Globe,
    text: "抓取南京大学计算机学院教师邮箱",
  },
  {
    icon: FileSpreadsheet,
    text: "导出北京大学教师邮箱为 CSV",
  },
  {
    icon: Search,
    text: "查找清华大学计算机系教师信息",
  },
  {
    icon: MessageSquare,
    text: "帮我获取浙大数学学院教师联系方式",
  },
];

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08,
      delayChildren: 0.1,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.4,
      ease: [0.22, 1, 0.36, 1] as const,
    },
  },
};

interface EmptyStateProps {
  recentTasks?: Task[];
  onSelectTask?: (task: Task) => void;
  onPromptClick?: (prompt: string) => void;
}

export function EmptyState({
  recentTasks,
  onSelectTask,
  onPromptClick,
}: EmptyStateProps) {
  return (
    <div className="relative flex flex-1 items-center justify-center overflow-hidden">
      {/* Ambient animated background — Framer Motion */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <motion.div
          className="absolute -left-20 -top-20 h-[400px] w-[400px] rounded-full bg-primary/[0.03] blur-3xl dark:bg-primary/[0.04]"
          animate={{
            borderRadius: [
              "60% 40% 30% 70% / 60% 30% 70% 40%",
              "30% 60% 70% 40% / 50% 60% 30% 60%",
              "60% 40% 30% 70% / 60% 30% 70% 40%",
            ],
            x: [0, 20, 0],
            y: [0, -10, 0],
          }}
          transition={{
            duration: 12,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
        <motion.div
          className="absolute -bottom-32 -right-16 h-[300px] w-[300px] rounded-full bg-primary/[0.02] blur-3xl dark:bg-primary/[0.03]"
          animate={{
            x: [0, -15, 0],
            y: [0, 10, 0],
            scale: [1, 1.05, 1],
          }}
          transition={{
            duration: 15,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
      </div>

      <motion.div
        className="relative z-10 flex w-full max-w-[560px] flex-col items-center px-6 py-12"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* Logo */}
        <motion.div
          variants={itemVariants}
          className="mb-6 flex items-center justify-center"
        >
          <img src="/logo.png" alt="UniEmail Agent" className="h-28 object-contain" />
        </motion.div>
        <motion.p
          variants={itemVariants}
          className="mb-8 text-center text-sm leading-relaxed text-muted-foreground"
        >
          AI 驱动的高校教师邮箱抓取助手，自动浏览官网、提取邮箱、导出 CSV/XLSX
        </motion.p>

        {/* Prompt cards */}
        <motion.div
          variants={itemVariants}
          className="mb-8 grid w-full grid-cols-2 gap-3"
        >
          {suggestedPrompts.map((prompt) => (
            <motion.button
              key={prompt.text}
              onClick={() => onPromptClick?.(prompt.text)}
              className="group flex flex-col items-start gap-2 rounded-[24px] border p-4 text-left transition-all duration-250 hover:-translate-y-[1px] hover:shadow-[0_2px_12px_rgba(0,0,0,0.04)] dark:hover:shadow-[0_2px_12px_rgba(0,0,0,0.2)]"
              style={{
                borderColor: "rgba(0,0,0,0.06)",
                transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)",
              }}
              whileHover={{ y: -1 }}
              whileTap={{ scale: 0.98 }}
            >
              <prompt.icon className="size-4 text-primary/70" />
              <span className="text-xs leading-relaxed text-foreground/70 group-hover:text-foreground">
                {prompt.text}
              </span>
            </motion.button>
          ))}
        </motion.div>

        {/* Recent tasks */}
        {recentTasks && recentTasks.length > 0 && (
          <motion.div
            variants={itemVariants}
            className="w-full"
          >
            <p className="mb-3 text-xs font-medium text-muted-foreground/60">
              最近任务
            </p>
            <div className="space-y-1">
              {recentTasks.slice(0, 3).map((task) => (
                <motion.button
                  key={task.id}
                  onClick={() => onSelectTask?.(task)}
                  className="flex w-full items-center gap-3 rounded-[24px] px-3 py-2 text-left text-sm text-muted-foreground/70 transition-colors hover:bg-muted/50 hover:text-foreground"
                  whileHover={{ x: 3 }}
                  transition={{ duration: 0.2 }}
                >
                  <span className="truncate flex-1">{task.title}</span>
                  <span className="shrink-0 text-xs text-muted-foreground/40">
                    {task.date}
                  </span>
                </motion.button>
              ))}
            </div>
          </motion.div>
        )}
      </motion.div>
    </div>
  );
}
