"use client";

import { motion } from "framer-motion";
import { Check } from "lucide-react";
type CrawlStageState = { stage: number; stage_name: string; progress_pct: number; timestamp: string; };

const STAGES = [
  { id: 1, label: "识别" },
  { id: 2, label: "探索" },
  { id: 3, label: "提取" },
  { id: 4, label: "整理" },
  { id: 5, label: "生成" },
];

interface StageStepperProps {
  stage: CrawlStageState | undefined;
}

export function StageStepper({ stage }: StageStepperProps) {
  const currentStage = stage?.stage ?? 0;

  return (
    <div className="flex items-center gap-0 w-full">
      {STAGES.map((s, i) => {
        const isCompleted = currentStage > s.id;
        const isCurrent = currentStage === s.id;
        const isFuture = currentStage < s.id;

        return (
          <div key={s.id} className="flex items-center flex-1 last:flex-none">
            {/* Step circle + label */}
            <div className="flex flex-col items-center gap-1">
              <div
                className={`flex size-7 items-center justify-center rounded-full text-xs font-semibold transition-all duration-300 ${
                  isCompleted
                    ? "bg-primary text-primary-foreground"
                    : isCurrent
                      ? "bg-primary/10 text-primary ring-2 ring-primary/30"
                      : "bg-muted text-muted-foreground/40"
                }`}
              >
                {isCompleted ? (
                  <Check className="size-3.5" />
                ) : (
                  <span>{s.id}</span>
                )}
              </div>
              <span
                className={`text-[10px] font-medium whitespace-nowrap transition-colors ${
                  isCurrent
                    ? "text-primary"
                    : isCompleted
                      ? "text-foreground"
                      : "text-muted-foreground/40"
                }`}
              >
                {s.label}
              </span>
            </div>

            {/* Connector line (not after last) */}
            {i < STAGES.length - 1 && (
              <div className="flex-1 mx-2 h-px relative">
                <div className="absolute inset-0 bg-border rounded-full" />
                <div
                  className={`absolute inset-y-0 left-0 rounded-full transition-all duration-500 ${
                    isCompleted ? "bg-primary" : "bg-transparent"
                  }`}
                  style={{
                    width: isCurrent
                      ? `${stage?.progress_pct ?? 0}%`
                      : isCompleted
                        ? "100%"
                        : "0%",
                  }}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
