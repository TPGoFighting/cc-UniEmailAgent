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
    <div className="relative mx-3 mb-2">
      <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground/50" />
      <input
        value={value}
        onChange={handleChange}
        placeholder="搜索历史..."
        className="w-full rounded-[24px] border border-transparent bg-black/[0.03] py-2 pl-9 pr-8 text-sm text-foreground placeholder:text-muted-foreground/50 outline-none transition-colors focus:border-border focus:bg-transparent dark:bg-white/[0.05] dark:focus:bg-transparent"
      />
      {value && (
        <button
          onClick={handleClear}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-full p-0.5 text-muted-foreground/50 hover:text-muted-foreground"
        >
          <X className="size-3" />
        </button>
      )}
    </div>
  );
}
