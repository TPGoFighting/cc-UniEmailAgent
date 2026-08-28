"use client";

import { motion } from "framer-motion";
import { MessageSquare, Globe, FileSpreadsheet, Search, ArrowRight } from "lucide-react";
import type { Task } from "@/lib/types";

const suggestedPrompts = [
  {
    icon: Globe,
    text: "抓取小红书关于‘AI大模型’的热门笔记与点赞数",
  },
  {
    icon: FileSpreadsheet,
    text: "提取懂车帝上比亚迪秦L的售价与续航配置",
  },
  {
    icon: Search,
    text: "爬取链家网建邺区最新二手房的小区均价",
  },
  {
    icon: MessageSquare,
    text: "每日监控 ProductHunt 榜单上排名前十的智能体",
  },
];

const rotatingTips = [
  "💡 试试说：「抓取小红书关于AI大模型的热门笔记」",
  "💡 试试说：「提取懂车帝上比亚迪秦L的售价与续航配置」",
  "💡 试试说：「每天定时监控 ProductHunt 上的 AI 智能体」",
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
      </div>

      <motion.div
        className="relative z-10 flex w-full max-w-[560px] flex-col items-center px-6 py-8"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* Premium Banner Image (Apple-Style Presentation Card) */}
        <motion.div
          variants={itemVariants}
          className="w-full mb-6 relative rounded-2xl overflow-hidden border border-border/40 shadow-2xl shadow-primary/5 aspect-[16/9]"
        >
          <img 
            src="/hero_banner.png" 
            alt="AI Workbench Hero" 
            className="w-full h-full object-cover select-none"
          />
          {/* Glass Overlay Text */}
          <div className="absolute inset-x-0 bottom-0 bg-background/60 backdrop-blur-md border-t border-border/20 p-4 flex justify-between items-center">
            <div>
              <h3 className="text-xs font-bold text-foreground">AI 全网信息采集工作台</h3>
              <p className="text-[10px] text-muted-foreground/80 mt-0.5">一站式帮您搞定数据抓取、API/RSS 订阅与 HTML 报表生成</p>
            </div>
            <div className="size-8 rounded-full bg-primary flex items-center justify-center text-white text-xs font-bold shadow-lg shadow-primary/20 shrink-0">
              Go
            </div>
          </div>
        </motion.div>

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
