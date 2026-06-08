"use client";

import { motion } from "framer-motion";
import { MessageSquare, Globe, FileSpreadsheet, Search, ArrowRight } from "lucide-react";
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

const rotatingTips = [
  "💡 试试说：「帮我抓取南京大学计算机学院教师邮箱」",
  "💡 试试说：「导出北京大学已抓取的数据」",
  "💡 试试说：「补充清华大学计算机系缺失的邮箱」",
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
  activeTaskId?: string | null;
  /** 是否在 localStorage 中有上次未完成的任务 */
  hasUnfinishedTask?: boolean;
}

export function EmptyState({
  recentTasks,
  onSelectTask,
  onPromptClick,
  activeTaskId,
  hasUnfinishedTask,
}: EmptyStateProps) {
  // 从 localStorage 读取上次未完成的任务 ID
  const savedTaskId = typeof window !== "undefined" ? localStorage.getItem("activeTaskId") : null;
  const showContinueCard = hasUnfinishedTask && savedTaskId && activeTaskId;

  return (
    <div className="relative flex flex-1 items-center justify-center overflow-hidden">
      {/* Ambient animated background — Cyber Academia */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        {/* Primary cyan glow */}
        <motion.div
          className="absolute -left-20 -top-20 h-[500px] w-[500px] rounded-full bg-primary/[0.04] blur-3xl"
          animate={{
            x: [0, 25, -10, 0],
            y: [0, -15, 10, 0],
            scale: [1, 1.05, 0.98, 1],
          }}
          transition={{
            duration: 18,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
        {/* Secondary indigo glow */}
        <motion.div
          className="absolute -bottom-40 -right-20 h-[400px] w-[400px] rounded-full bg-accent/[0.03] blur-3xl"
          animate={{
            x: [0, -20, 10, 0],
            y: [0, 15, -5, 0],
            scale: [1, 1.08, 0.95, 1],
          }}
          transition={{
            duration: 22,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
        {/* Subtle third glow */}
        <motion.div
          className="absolute top-1/3 right-1/4 h-[300px] w-[300px] rounded-full bg-primary/[0.02] blur-3xl"
          animate={{
            x: [0, 10, -15, 0],
            y: [0, -10, 5, 0],
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
          <img src="/logo.png" alt="UniEmail Agent" className="h-28 object-contain img-blend" />
        </motion.div>
        <motion.p
          variants={itemVariants}
          className="mb-8 text-center text-sm leading-relaxed text-muted-foreground"
        >
          AI 驱动的高校通知系统，自动浏览官网抓取高校通知信息
        </motion.p>

        {/* 上下文恢复卡片 — 继续上次任务 */}
        {showContinueCard && (
          <motion.div
            variants={itemVariants}
            className="mb-6 w-full"
          >
            <div className="rounded-2xl border border-primary/20 bg-primary/[0.04] px-5 py-4 backdrop-blur-sm">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-semibold text-foreground mb-1">📋 继续上次任务</div>
                  <p className="text-xs text-muted-foreground">检测到您有未完成的任务，点击继续</p>
                </div>
                <button
                  onClick={() => {
                    // 找到该任务并选中
                    if (onSelectTask && recentTasks) {
                      const saved = recentTasks.find((t) => t.id === savedTaskId);
                      if (saved) onSelectTask(saved);
                    }
                  }}
                  className="flex shrink-0 items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-xs font-medium text-primary-foreground shadow-[0_0_12px_rgba(34,211,238,0.2)] hover:shadow-[0_0_16px_rgba(34,211,238,0.35)] transition-all duration-250"
                >
                  继续
                  <ArrowRight className="size-3.5" />
                </button>
              </div>
            </div>
          </motion.div>
        )}

        {/* Prompt cards */}
        <motion.div
          variants={itemVariants}
          className="mb-8 grid w-full grid-cols-2 gap-3"
        >
          {suggestedPrompts.map((prompt) => (
            <motion.button
              key={prompt.text}
              onClick={() => onPromptClick?.(prompt.text)}
              className="group flex flex-col items-start gap-2 rounded-2xl border border-border/40 bg-card/30 p-4 text-left transition-all duration-250 hover:-translate-y-[0.5px] hover:bg-card/60 hover:border-primary/20 hover:shadow-[0_0_16px_rgba(34,211,238,0.06)]"
              style={{
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

        {/* 动态引导轮播 — 纯 CSS 动画 */}
        <motion.div
          variants={itemVariants}
          className="mb-8 w-full text-center"
        >
          <div className="relative h-5 overflow-hidden">
            {rotatingTips.map((tip, index) => (
              <span
                key={index}
                className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap text-xs text-muted-foreground/70"
                style={{
                  animation: `carousel-${index} 15s infinite`,
                }}
              >
                {tip}
              </span>
            ))}
          </div>
          <style>{`
            ${rotatingTips.map((_, i) => `
              @keyframes carousel-${i} {
                0%, ${(i * 100) / rotatingTips.length - (100 / rotatingTips.length / 3)}% {
                  opacity: 0;
                  transform: translate(-50%, 8px);
                }
                ${(i * 100) / rotatingTips.length}% {
                  opacity: 1;
                  transform: translate(-50%, 0);
                }
                ${((i + 1) * 100) / rotatingTips.length - (100 / rotatingTips.length / 3)}% {
                  opacity: 1;
                  transform: translate(-50%, 0);
                }
                ${((i + 1) * 100) / rotatingTips.length}% {
                  opacity: 0;
                  transform: translate(-50%, -8px);
                }
                100% {
                  opacity: 0;
                  transform: translate(-50%, -8px);
                }
              }
            `).join('\n')}
          `}</style>
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
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm text-muted-foreground/60 transition-colors hover:bg-primary/[0.04] hover:text-foreground"
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
