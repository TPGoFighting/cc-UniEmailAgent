"use client";

import { useTheme } from "next-themes";
import {
  Moon,
  Sun,
  Monitor,
  Palette,
  Check,
} from "lucide-react";
import { useEffect, useState } from "react";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";

const themes = [
  { id: "dark", label: "深色", icon: Moon, color: "text-primary" },
  { id: "light", label: "浅色", icon: Sun, color: "text-amber-500" },
  { id: "system", label: "系统", icon: Monitor, color: "text-muted-foreground" },
  { id: "dracula", label: "Dracula", icon: Palette, color: "text-purple-400" },
  { id: "nord", label: "Nord", icon: Palette, color: "text-blue-400" },
  { id: "monokai", label: "Monokai", icon: Palette, color: "text-green-400" },
];

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return <div className="size-8" />;
  }

  const current = themes.find((t) => t.id === theme) || themes[0];
  const CurrentIcon = current.icon;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex size-8 items-center justify-center rounded-xl text-muted-foreground transition-colors duration-250 hover:bg-primary/[0.06] hover:text-primary outline-none">
        <CurrentIcon className={`size-4 ${current.color}`} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-36">
        {themes.map((t) => {
          const Icon = t.icon;
          return (
            <DropdownMenuItem
              key={t.id}
              onClick={() => setTheme(t.id)}
              className="flex items-center gap-2"
            >
              <Icon className={`size-4 ${t.color}`} />
              <span className="flex-1 text-sm">{t.label}</span>
              {theme === t.id && (
                <Check className="size-3.5 text-primary" />
              )}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
