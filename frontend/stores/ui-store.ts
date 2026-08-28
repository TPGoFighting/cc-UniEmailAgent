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
  highlightUniversity: string | null;
  pendingInput: string | null;
  activeTab: "collector";

  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setSearchQuery: (query: string) => void;
  setEditTarget: (target: EditTarget | null) => void;
  setUniversityOpen: (open: boolean) => void;
  setMailOpen: (open: boolean) => void;
  setHighlightUniversity: (name: string | null) => void;
  setPendingInput: (text: string | null) => void;
  setActiveTab: (tab: "collector") => void;
}

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({
      sidebarOpen: false,
      searchQuery: "",
      editTarget: null,
      universityOpen: false,
      mailOpen: false,
      highlightUniversity: null,
      pendingInput: null,
      activeTab: "collector",

      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      setSearchQuery: (query) => set({ searchQuery: query }),
      setEditTarget: (target) => set({ editTarget: target }),
      setUniversityOpen: (open) => set({ universityOpen: open }),
      setMailOpen: (open) => set({ mailOpen: open }),
      setHighlightUniversity: (name) => set({ highlightUniversity: name }),
      setPendingInput: (text) => set({ pendingInput: text }),
      setActiveTab: (tab) => set({ activeTab: tab }),
    }),
    {
      name: "uniemail-ui",
      partialize: (state) => ({
        sidebarOpen: state.sidebarOpen,
        activeTab: state.activeTab,
      }),
    }
  )
);
