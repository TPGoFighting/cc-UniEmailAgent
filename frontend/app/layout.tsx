import type { Metadata } from "next";
import { Sora, DM_Sans, JetBrains_Mono } from "next/font/google";
import { ThemeProvider } from "@/components/theme-provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Providers } from "@/providers/Providers";
import "./globals.css";

const sora = Sora({
  variable: "--font-sora",
  subsets: ["latin"],
  display: "swap",
});

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "江苏省人工智能学会高校通知系统",
  description: "AI 驱动的教师邮箱自动抓取工具",
  icons: [{ rel: "icon", url: "/icon.png", type: "image/png" }],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      className={`${sora.variable} ${dmSans.variable} ${jetbrainsMono.variable} h-full antialiased`}
      style={{ overflow: "hidden" }}
      suppressHydrationWarning
    >
      <body className="flex h-full flex-col overflow-hidden">
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          themes={["dark", "light", "system", "dracula", "nord", "monokai"]}
          enableSystem={false}
          disableTransitionOnChange
        >
          <Providers>
            <TooltipProvider>{children}</TooltipProvider>
          </Providers>
        </ThemeProvider>
      </body>
    </html>
  );
}
