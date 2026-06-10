import { create } from "zustand";
import { persist } from "zustand/middleware";

interface EditTarget {
  messageId: string;
  content: string;
}

interface UIStore {
  sidebarOpen: boolean;
  searchQuery: string;
  editTarget: EditTarget | null;
  universityOpen: boolean;
  mailOpen: boolean;
  settingsOpen: boolean;
  agentDockOpen: boolean;
  agentDockMode: "kb" | "chat";
  highlightUniversity: string | null;
  pendingInput: string | null;

  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setSearchQuery: (query: string) => void;
  setEditTarget: (target: EditTarget | null) => void;
  setUniversityOpen: (open: boolean) => void;
  setMailOpen: (open: boolean) => void;
  setSettingsOpen: (open: boolean) => void;
  setAgentDockOpen: (open: boolean) => void;
  setAgentDockMode: (mode: "kb" | "chat") => void;
  setHighlightUniversity: (name: string | null) => void;
  setPendingInput: (text: string | null) => void;
}

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({
      sidebarOpen: false,
      searchQuery: "",
      editTarget: null,
      universityOpen: false,
      mailOpen: false,
      settingsOpen: false,
      agentDockOpen: false,
      agentDockMode: "kb",
      highlightUniversity: null,
      pendingInput: null,

      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      setSearchQuery: (query) => set({ searchQuery: query }),
      setEditTarget: (target) => set({ editTarget: target }),
      setUniversityOpen: (open) => set({ universityOpen: open }),
      setMailOpen: (open) => set({ mailOpen: open }),
      setSettingsOpen: (open) => set({ settingsOpen: open }),
      setAgentDockOpen: (open) => set({ agentDockOpen: open }),
      setAgentDockMode: (mode) => set({ agentDockMode: mode, agentDockOpen: true }),
      setHighlightUniversity: (name) => set({ highlightUniversity: name }),
      setPendingInput: (text) => set({ pendingInput: text }),
    }),
    {
      name: "uniemail-ui",
      partialize: (state) => ({
        sidebarOpen: state.sidebarOpen,
      }),
    }
  )
);
