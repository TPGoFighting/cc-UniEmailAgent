"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Check, X, ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";

const STORAGE_KEY = "uniemail_onboarding_done";

interface Step {
  title: string;
  description: string;
}

const STEPS: Step[] = [
  {
    title: "步骤 1/3：输入任务",
    description:
      "在底部的输入框中输入你的需求，例如「抓取南京大学计算机学院教师邮箱」。AI Agent 会自动操作浏览器完成爬取。",
  },
  {
    title: "步骤 2/3：查看进度",
    description:
      "任务开始后，实时面板会展示爬取进度、已发现的教师和邮箱数量，让你随时掌握任务状态。",
  },
  {
    title: "步骤 3/3：探索功能",
    description:
      "顶部按钮栏可以打开高校库（查看已抓取的教师数据）和邮件发送面板（群发邮件给教师）。",
  },
];

export function OnboardingTour() {
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);
  const [dontShowAgain, setDontShowAgain] = useState(false);

  useEffect(() => {
    const done = localStorage.getItem(STORAGE_KEY);
    if (!done) {
      // 延迟显示，等页面渲染完毕
      const timer = setTimeout(() => setVisible(true), 800);
      return () => clearTimeout(timer);
    }
  }, []);

  const finish = useCallback(() => {
    if (dontShowAgain) {
      localStorage.setItem(STORAGE_KEY, "true");
    }
    setVisible(false);
  }, [dontShowAgain]);

  const next = useCallback(() => {
    if (step < STEPS.length - 1) {
      setStep((s) => s + 1);
    } else {
      finish();
    }
  }, [step, finish]);

  const skip = useCallback(() => {
    finish();
  }, [finish]);

  if (!visible) return null;

  const current = STEPS[step];

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 20 }}
        className="fixed bottom-28 left-1/2 -translate-x-1/2 z-[9999] w-[440px] max-w-[90vw]"
      >
        <div className="rounded-2xl border border-border bg-background p-5 shadow-2xl">
          {/* 步骤指示器 */}
          <div className="flex items-center gap-1.5 mb-3">
            {STEPS.map((_, i) => (
              <div
                key={i}
                className={`h-1 rounded-full transition-all duration-300 ${
                  i === step ? "w-6 bg-primary" : i < step ? "w-3 bg-primary/40" : "w-3 bg-muted-foreground/20"
                }`}
              />
            ))}
          </div>

          <h3 className="text-sm font-semibold text-foreground mb-1.5">{current.title}</h3>
          <p className="text-xs text-muted-foreground leading-relaxed">{current.description}</p>

          {/* 不再显示 */}
          <label className="flex items-center gap-2 mt-3 cursor-pointer group">
            <input
              type="checkbox"
              checked={dontShowAgain}
              onChange={(e) => setDontShowAgain(e.target.checked)}
              className="size-3.5 rounded border-muted-foreground/30 text-primary focus:ring-primary/30"
            />
            <span className="text-[11px] text-muted-foreground/60 group-hover:text-muted-foreground transition-colors">
              不再显示引导
            </span>
          </label>

          <div className="flex items-center justify-between mt-3">
            <button
              onClick={skip}
              className="text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors flex items-center gap-1"
            >
              <X className="size-3" />
              跳过引导
            </button>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground/50">
                {step + 1} / {STEPS.length}
              </span>
              <Button size="sm" onClick={next} className="gap-1.5">
                {step === STEPS.length - 1 ? (
                  <>
                    <Check className="size-3.5" />
                    完成
                  </>
                ) : (
                  <>
                    下一步
                    <ArrowRight className="size-3.5" />
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

/** 浮动帮助按钮 — 用于重新显示引导 */
export function OnboardingFloatingButton() {
  const handleReset = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    window.location.reload();
  }, []);

  return (
    <button
      onClick={handleReset}
      className="fixed bottom-6 left-6 z-[9998] flex size-9 items-center justify-center rounded-full bg-muted/80 text-muted-foreground shadow-lg backdrop-blur-sm border border-border/50 hover:bg-muted hover:text-foreground transition-all duration-250"
      style={{ transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1)" }}
      title="重新查看引导"
    >
      <span className="text-sm leading-none">❓</span>
    </button>
  );
}
