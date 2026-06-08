"use client";

import { useEffect, useRef } from "react";

export function useNotification() {
  const permissionRef = useRef<NotificationPermission>("default");

  useEffect(() => {
    if ("Notification" in window) {
      permissionRef.current = Notification.permission;
    }
  }, []);

  const requestPermission = async () => {
    if (!("Notification" in window)) return false;
    if (permissionRef.current === "granted") return true;
    const result = await Notification.requestPermission();
    permissionRef.current = result;
    return result === "granted";
  };

  const notify = (title: string, options?: { body?: string; icon?: string }) => {
    if (!("Notification" in window)) return;
    if (permissionRef.current !== "granted") return;
    // 仅在用户不在当前标签页时发送
    if (!document.hidden) return;
    new Notification(title, { ...options, icon: options?.icon || "/logo.png" });
  };

  /** 任务完成时调用 */
  const notifyComplete = (taskTitle: string) => {
    notify("任务完成", { body: `"${taskTitle}" 已执行完毕` });
  };

  /** 任务失败时调用 */
  const notifyError = (taskTitle: string, errorMsg?: string) => {
    notify("任务失败", { body: errorMsg ? `"${taskTitle}": ${errorMsg}` : `"${taskTitle}" 执行出错` });
  };

  return { requestPermission, notify, notifyComplete, notifyError };
}
