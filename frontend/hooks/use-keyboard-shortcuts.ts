"use client";

import { useEffect } from "react";
import { useUIStore } from "@/stores/ui-store";
import { useTaskStore } from "@/stores/task-store";
import { useChatStore } from "@/stores/chat-store";
import { useAgentChat } from "@/hooks/use-agent-chat";

export function useKeyboardShortcuts() {
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const setSidebarOpen = useUIStore((s) => s.setSidebarOpen);
  const editTarget = useUIStore((s) => s.editTarget);
  const setEditTarget = useUIStore((s) => s.setEditTarget);
  const universityOpen = useUIStore((s) => s.universityOpen);
  const setUniversityOpen = useUIStore((s) => s.setUniversityOpen);
  const mailOpen = useUIStore((s) => s.mailOpen);
  const setMailOpen = useUIStore((s) => s.setMailOpen);

  const { newTask } = useAgentChat();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger shortcuts when typing in an input/textarea
      const target = e.target as HTMLElement;
      const isInput =
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable;

      // Escape: close modals/panels
      if (e.key === "Escape") {
        if (editTarget) {
          setEditTarget(null);
          e.preventDefault();
          return;
        }
        if (universityOpen) {
          setUniversityOpen(false);
          e.preventDefault();
          return;
        }
        if (mailOpen) {
          setMailOpen(false);
          e.preventDefault();
          return;
        }
        // Close sidebar on mobile (when sheet version is open)
        setSidebarOpen(false);
        e.preventDefault();
        return;
      }

      // Ctrl+K: focus search bar — only works on desktop sidebar
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        const searchInput = document.querySelector<HTMLInputElement>(
          'input[placeholder*="搜索"]'
        );
        if (searchInput) {
          searchInput.focus();
        }
        return;
      }

      // Ctrl+N: new task
      if (e.key === "n" && (e.metaKey || e.ctrlKey) && !isInput) {
        e.preventDefault();
        newTask();
        return;
      }

      // Ctrl+Enter: send message — handled in chat-input.tsx alongside Enter
      // (This is handled inline in the textarea's onKeyDown, so we skip it here)
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    toggleSidebar,
    setSidebarOpen,
    editTarget,
    setEditTarget,
    universityOpen,
    setUniversityOpen,
    mailOpen,
    setMailOpen,
    newTask,
  ]);
}
