import { create } from "zustand";
import type { Task } from "@/lib/types";

interface TaskStore {
  tasks: Task[];
  activeTaskId: string | null;

  setTasks: (tasks: Task[]) => void;
  addTask: (task: Task) => void;
  updateTask: (id: string, patch: Partial<Task>) => void;
  removeTask: (id: string) => void;
  setActiveTask: (id: string | null) => void;
  getActiveTask: () => Task | null;
}

export const useTaskStore = create<TaskStore>((set, get) => ({
  tasks: [],
  activeTaskId: null,

  setTasks: (tasks) => set({ tasks }),

  addTask: (task) =>
    set((s) => ({ tasks: [task, ...s.tasks] })),

  updateTask: (id, patch) =>
    set((s) => ({
      tasks: s.tasks.map((t) => (t.id === id ? { ...t, ...patch } : t)),
    })),

  removeTask: (id) =>
    set((s) => ({
      tasks: s.tasks.filter((t) => t.id !== id),
      activeTaskId: s.activeTaskId === id ? null : s.activeTaskId,
    })),

  setActiveTask: (id) => {
    if (id) {
      localStorage.setItem("activeTaskId", id);
    } else {
      localStorage.removeItem("activeTaskId");
    }
    set({ activeTaskId: id });
  },

  getActiveTask: () => {
    const state = get();
    if (!state.activeTaskId) return null;
    return state.tasks.find((t) => t.id === state.activeTaskId) || null;
  },
}));
