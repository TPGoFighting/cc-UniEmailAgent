import { create } from "zustand";

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

  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setSearchQuery: (query: string) => void;
  setEditTarget: (target: EditTarget | null) => void;
  setUniversityOpen: (open: boolean) => void;
  setMailOpen: (open: boolean) => void;
}

export const useUIStore = create<UIStore>((set) => ({
  sidebarOpen: false,
  searchQuery: "",
  editTarget: null,
  universityOpen: false,
  mailOpen: false,

  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setEditTarget: (target) => set({ editTarget: target }),
  setUniversityOpen: (open) => set({ universityOpen: open }),
  setMailOpen: (open) => set({ mailOpen: open }),
}));
