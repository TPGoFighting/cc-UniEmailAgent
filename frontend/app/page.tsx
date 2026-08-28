"use client";

import { Component, type ReactNode } from "react";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Sidebar } from "@/components/sidebar";
import { UniversityWorkspace } from "@/components/university-workspace";
import { MailWorkspace } from "@/components/mail-workspace";
import { UndoToast } from "@/components/undo-toast";
import { useUIStore } from "@/stores/ui-store";
import { motion, AnimatePresence } from "framer-motion";

// ── Error Boundary ──
class ErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-full flex-col items-center justify-center p-8 text-center">
          <h2 className="mb-2 text-xl font-bold text-red-600">页面渲染异常</h2>
          <p className="mb-4 text-muted-foreground">
            应用遇到了一个错误，请尝试刷新页面。
          </p>
          <details className="max-w-lg text-left text-sm text-muted-foreground">
            <summary className="cursor-pointer font-medium">错误详情</summary>
            <pre className="mt-2 overflow-auto rounded border bg-muted p-2 text-xs">
              {this.state.error?.message}
            </pre>
          </details>
          <button
            className="mt-4 rounded bg-primary px-4 py-2 text-primary-foreground hover:bg-primary/90"
            onClick={() => window.location.reload()}
          >
            刷新页面
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function HomePage() {
  const sidebarOpen = useUIStore((s) => s.sidebarOpen);
  const setSidebarOpen = useUIStore((s) => s.setSidebarOpen);

  return (
    <ErrorBoundary>
      <div className="flex h-full flex-col overflow-hidden bg-cyber-grid bg-ambient-glow dark:bg-cyber-grid dark:bg-ambient-glow">
        <div className="flex flex-1 min-h-0 overflow-hidden">
          <div className="hidden w-[260px] shrink-0 lg:block">
            <Sidebar />
          </div>

          <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
            <SheetContent side="left" className="w-[260px] p-0">
              <Sidebar />
            </SheetContent>
          </Sheet>

          <AnimatePresence mode="wait">
            <motion.div
              key="university-library"
              initial={{ opacity: 0, y: 15, filter: "blur(4px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              exit={{ opacity: 0, y: -15, filter: "blur(4px)" }}
              transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
              className="flex-1 min-h-0 overflow-hidden flex"
            >
              <UniversityWorkspace mode="page" />
            </motion.div>
          </AnimatePresence>
        </div>
        <MailWorkspace />
        <UndoToast />
      </div>
    </ErrorBoundary>
  );
}
