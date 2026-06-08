"use client";

import { useState, useEffect } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { useUIStore } from "@/stores/ui-store";
import { useTheme } from "next-themes";
import {
  Settings,
  Palette,
  Server,
  Download,
  Keyboard,
  Moon,
  Sun,
  Monitor,
} from "lucide-react";

const shortcuts = [
  { key: "Enter", label: "发送消息" },
  { key: "Shift + Enter", label: "换行" },
  { key: "Ctrl + Enter", label: "发送消息（备选）" },
  { key: "Ctrl + K", label: "聚焦搜索栏" },
  { key: "Ctrl + N", label: "新建任务" },
  { key: "Escape", label: "关闭侧边栏/弹窗" },
];

type SettingsTab = "general" | "api" | "export" | "shortcuts";

const tabs: { id: SettingsTab; label: string; icon: React.ReactNode }[] = [
  { id: "general", label: "通用", icon: <Settings className="size-4" /> },
  { id: "api", label: "API 配置", icon: <Server className="size-4" /> },
  { id: "export", label: "导出偏好", icon: <Download className="size-4" /> },
  { id: "shortcuts", label: "快捷键", icon: <Keyboard className="size-4" /> },
];

export function SettingsPanel() {
  const settingsOpen = useUIStore((s) => s.settingsOpen);
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen);
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [activeTab, setActiveTab] = useState<SettingsTab>("general");

  useEffect(() => setMounted(true), []);

  if (!mounted) return null;

  return (
    <Sheet open={settingsOpen} onOpenChange={setSettingsOpen}>
      <SheetContent side="right" className="w-[380px] sm:max-w-[420px] p-0 flex flex-col">
        <SheetHeader className="px-5 py-4 border-b border-border/30">
          <SheetTitle className="flex items-center gap-2">
            <Settings className="size-4 text-primary" />
            设置
          </SheetTitle>
          <SheetDescription>
            管理应用外观、连接和偏好
          </SheetDescription>
        </SheetHeader>

        {/* Tab navigation */}
        <div className="flex gap-1 px-4 pt-3 pb-1 border-b border-border/20">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                activeTab === tab.id
                  ? "bg-primary/15 text-primary"
                  : "text-muted-foreground/60 hover:text-muted-foreground hover:bg-muted/30"
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        <ScrollArea className="flex-1 px-5 py-4">
          {activeTab === "general" && (
            <div className="space-y-4">
              <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
                <Palette className="size-4 text-primary" />
                主题切换
              </h3>
              <div className="grid grid-cols-3 gap-2">
                <button
                  onClick={() => setTheme("dark")}
                  className={`flex flex-col items-center gap-2 rounded-xl border p-3 transition-all ${
                    theme === "dark"
                      ? "border-primary/40 bg-primary/10 ring-1 ring-primary/30"
                      : "border-border/30 hover:border-border/60 hover:bg-muted/20"
                  }`}
                >
                  <Moon className="size-5 text-primary" />
                  <span className="text-xs font-medium">深色</span>
                </button>
                <button
                  onClick={() => setTheme("light")}
                  className={`flex flex-col items-center gap-2 rounded-xl border p-3 transition-all ${
                    theme === "light"
                      ? "border-primary/40 bg-primary/10 ring-1 ring-primary/30"
                      : "border-border/30 hover:border-border/60 hover:bg-muted/20"
                  }`}
                >
                  <Sun className="size-5 text-amber-500" />
                  <span className="text-xs font-medium">浅色</span>
                </button>
                <button
                  onClick={() => setTheme("system")}
                  className={`flex flex-col items-center gap-2 rounded-xl border p-3 transition-all ${
                    theme === "system"
                      ? "border-primary/40 bg-primary/10 ring-1 ring-primary/30"
                      : "border-border/30 hover:border-border/60 hover:bg-muted/20"
                  }`}
                >
                  <Monitor className="size-5 text-muted-foreground" />
                  <span className="text-xs font-medium">系统</span>
                </button>
              </div>

              {/* Additional themes section */}
              <div className="mt-2">
                <p className="text-xs text-muted-foreground/60 mb-2">扩展主题</p>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { id: "dracula", label: "Dracula", color: "bg-purple-500" },
                    { id: "nord", label: "Nord", color: "bg-blue-400" },
                    { id: "monokai", label: "Monokai", color: "bg-green-500" },
                  ].map((t) => (
                    <button
                      key={t.id}
                      onClick={() => setTheme(t.id)}
                      className={`flex flex-col items-center gap-2 rounded-xl border p-3 transition-all ${
                        theme === t.id
                          ? "border-primary/40 bg-primary/10 ring-1 ring-primary/30"
                          : "border-border/30 hover:border-border/60 hover:bg-muted/20"
                      }`}
                    >
                      <div className={`size-5 rounded-full ${t.color}`} />
                      <span className="text-xs font-medium">{t.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeTab === "api" && (
            <div className="space-y-4">
              <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
                <Server className="size-4 text-primary" />
                API 配置
              </h3>
              <div className="rounded-xl border border-border/30 bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground/60 mb-2">后端服务地址</p>
                <p className="text-sm font-mono text-foreground/80">
                  {typeof window !== "undefined"
                    ? localStorage.getItem("backendUrl") ||
                      (window as any).__NEXT_DATA__?.props?.pageProps?.NEXT_PUBLIC_API_URL ||
                      "http://localhost:8000"
                    : "http://localhost:8000"}
                </p>
              </div>
              <p className="text-xs text-muted-foreground/40">
                如需修改后端地址，请在 .env.local 中设置 NEXT_PUBLIC_API_URL 环境变量后重启应用。
              </p>
            </div>
          )}

          {activeTab === "export" && (
            <div className="space-y-4">
              <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
                <Download className="size-4 text-primary" />
                导出偏好
              </h3>
              <p className="text-xs text-muted-foreground/60">
                导出格式和下载路径由后端配置决定。支持 CSV、XLSX、MD 等格式。
              </p>
              <div className="rounded-xl border border-border/30 bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">默认导出格式</p>
                <div className="mt-2 flex gap-2">
                  {["CSV", "XLSX", "MD"].map((fmt) => (
                    <span
                      key={fmt}
                      className="rounded-lg bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary"
                    >
                      {fmt}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeTab === "shortcuts" && (
            <div className="space-y-4">
              <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
                <Keyboard className="size-4 text-primary" />
                快捷键列表
              </h3>
              <div className="space-y-1">
                {shortcuts.map((s) => (
                  <div
                    key={s.key}
                    className="flex items-center justify-between rounded-lg px-3 py-2 text-sm hover:bg-muted/20 transition-colors"
                  >
                    <span className="text-muted-foreground">{s.label}</span>
                    <kbd className="rounded-md border border-border/40 bg-muted/40 px-2 py-0.5 text-[11px] font-mono text-foreground/70 shadow-sm">
                      {s.key}
                    </kbd>
                  </div>
                ))}
              </div>
            </div>
          )}
        </ScrollArea>

        <div className="px-5 py-3 border-t border-border/30 bg-muted/10 text-[10px] text-muted-foreground/40 text-center">
          UniEmail Agent v0.1.0
        </div>
      </SheetContent>
    </Sheet>
  );
}
