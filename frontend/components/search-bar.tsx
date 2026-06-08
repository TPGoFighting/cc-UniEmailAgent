"use client";

import { useState, useRef, useEffect, type ChangeEvent } from "react";
import { Search, X } from "lucide-react";

interface SearchBarProps {
  onSearch: (query: string) => void;
}

export function SearchBar({ onSearch }: SearchBarProps) {
  const [value, setValue] = useState("");
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value;
    setValue(v);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => onSearch(v), 300);
  };

  const handleClear = () => {
    setValue("");
    onSearch("");
  };

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  return (
    <div className="relative mx-4 mb-2">
      <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground/40" />
      <input
        value={value}
        onChange={handleChange}
        placeholder="搜索历史..."
        className="w-full rounded-xl border border-border/30 bg-primary/[0.02] py-2 pl-9 pr-8 text-sm text-foreground placeholder:text-muted-foreground/40 outline-none transition-all duration-250 focus:border-primary/30 focus:bg-primary/[0.04] focus:shadow-[0_0_12px_rgba(34,211,238,0.06)]"
      />
      {value && (
        <button
          onClick={handleClear}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-full p-0.5 text-muted-foreground/40 hover:text-muted-foreground transition-colors"
        >
          <X className="size-3" />
        </button>
      )}
    </div>
  );
}
