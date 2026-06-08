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
  highlightUniversity: string | null;
  pendingInput: string | null;

  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setSearchQuery: (query: string) => void;
  setEditTarget: (target: EditTarget | null) => void;
  setUniversityOpen: (open: boolean) => void;
  setMailOpen: (open: boolean) => void;
  setHighlightUniversity: (name: string | null) => void;
  setPendingInput: (text: string | null) => void;
}

export const useUIStore = create<UIStore>((set) => ({
  sidebarOpen: false,
  searchQuery: "",
  editTarget: null,
  universityOpen: false,
  mailOpen: false,
  highlightUniversity: null,
  pendingInput: null,

  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setEditTarget: (target) => set({ editTarget: target }),
  setUniversityOpen: (open) => set({ universityOpen: open }),
  setMailOpen: (open) => set({ mailOpen: open }),
  setHighlightUniversity: (name) => set({ highlightUniversity: name }),
  setPendingInput: (text) => set({ pendingInput: text }),
}));
