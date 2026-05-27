"use client";

import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Sidebar } from "@/components/sidebar";
import { ChatArea } from "@/components/chat-area";
import { EditMessageDialog } from "@/components/edit-message-dialog";
import { useUIStore } from "@/stores/ui-store";

export default function HomePage() {
  const sidebarOpen = useUIStore((s) => s.sidebarOpen);
  const setSidebarOpen = useUIStore((s) => s.setSidebarOpen);

  return (
    <div className="flex h-full overflow-hidden">
      {/* 桌面端固定侧边栏 */}
      <div className="hidden w-[260px] shrink-0 lg:block">
        <Sidebar />
      </div>

      {/* 移动端 Sheet 侧边栏 */}
      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent side="left" className="w-[260px] p-0">
          <Sidebar />
        </SheetContent>
      </Sheet>

      {/* 聊天主区域（自主管理状态，不需要 props） */}
      <ChatArea />

      {/* 编辑消息弹窗 */}
      <EditMessageDialog />
    </div>
  );
}
