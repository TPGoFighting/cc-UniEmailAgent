"use client";

import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Sidebar } from "@/components/sidebar";
import { ChatArea } from "@/components/chat-area";
import { EditMessageDialog } from "@/components/edit-message-dialog";
import { UniversityWorkspace } from "@/components/university-workspace";
import { MailWorkspace } from "@/components/mail-workspace";
import { useUIStore } from "@/stores/ui-store";

export default function HomePage() {
  const sidebarOpen = useUIStore((s) => s.sidebarOpen);
  const setSidebarOpen = useUIStore((s) => s.setSidebarOpen);

  return (
    <div className="flex h-full overflow-hidden">
      <div className="hidden w-[260px] shrink-0 lg:block">
        <Sidebar />
      </div>

      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent side="left" className="w-[260px] p-0">
          <Sidebar />
        </SheetContent>
      </Sheet>

      <ChatArea />
      <EditMessageDialog />
      <UniversityWorkspace />
      <MailWorkspace />
    </div>
  );
}
