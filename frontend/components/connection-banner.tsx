"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Wifi, WifiOff, X } from "lucide-react";
import { getWsManager } from "@/services/websocket";

type BannerState = "hidden" | "connected" | "disconnected" | "reconnecting";

export function ConnectionBanner() {
  const [state, setState] = useState<BannerState>("hidden");

  const checkConnection = useCallback(() => {
    const manager = getWsManager();
    if (manager.isConnected) return;
    // 有 taskId 但未连接 = 断开状态
    if (manager.currentTaskId) {
      setState("disconnected");
    }
  }, []);

  useEffect(() => {
    // 轮询 WS 状态
    const interval = setInterval(checkConnection, 3000);

    // 监听 online/offline 事件
    const handleOnline = () => {
      setState("connected");
      setTimeout(() => setState("hidden"), 2000);
    };
    const handleOffline = () => setState("disconnected");

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      clearInterval(interval);
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [checkConnection]);

  if (state === "hidden") return null;

  const isError = state === "disconnected" || state === "reconnecting";

  return (
    <AnimatePresence>
      <motion.div
        initial={{ height: 0, opacity: 0 }}
        animate={{ height: "auto", opacity: 1 }}
        exit={{ height: 0, opacity: 0 }}
        className={`flex items-center justify-center gap-2 px-4 py-2 text-xs font-medium ${
          isError
            ? "bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400"
            : "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400"
        }`}
      >
        {isError ? (
          <WifiOff className="size-3.5" />
        ) : (
          <Wifi className="size-3.5" />
        )}
        <span>
          {state === "connected" && "已连接"}
        </span>
        <button
          onClick={() => setState("hidden")}
          className="ml-2 rounded p-0.5 hover:bg-black/5 dark:hover:bg-white/10"
        >
          <X className="size-3" />
        </button>
      </motion.div>
    </AnimatePresence>
  );
}
