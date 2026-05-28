"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/services/api";
import { useUIStore } from "@/stores/ui-store";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { University, UniversityGroup, UniversityRecord } from "@/lib/types";

const tiers = ["全部", "985", "211", "双一流", "普通本科"] as const;

export function UniversityWorkspace() {
  const open = useUIStore((s) => s.universityOpen);
  const setOpen = useUIStore((s) => s.setUniversityOpen);
  const [query, setQuery] = useState("");
  const [province, setProvince] = useState("");
  const [tier, setTier] = useState<(typeof tiers)[number]>("全部");
  const [groups, setGroups] = useState<UniversityGroup[]>([]);
  const [provinces, setProvinces] = useState<string[]>([]);
  const [selected, setSelected] = useState<University | null>(null);
  const [records, setRecords] = useState<UniversityRecord[]>([]);
  const [table, setTable] = useState<{ columns: string[]; rows: Record<string, string>[]; total: number }>({ columns: [], rows: [], total: 0 });

  useEffect(() => {
    if (!open) return;
    api.getUniversities({ province, tier, q: query }).then((data: any) => {
      setGroups(data.groups || []);
      setProvinces(data.provinces || []);
      const first = data.groups?.[0]?.cities?.[0]?.universities?.[0] || null;
      if (first && !selected) setSelected(first);
    }).catch(() => {});
  }, [open, province, tier, query]);

  useEffect(() => {
    if (!selected) return;
    api.getUniversityRecords(selected.name).then((data: any) => {
      setRecords(data.records || []);
      const first = (data.records || []).find((r: UniversityRecord) => r.previewable);
      if (first) {
        api.getUniversityTable(selected.name, { task_id: first.task_id, file: first.filename, limit: 80 }).then((tbl) => setTable({ columns: tbl.columns || [], rows: (tbl.rows || []) as Record<string, string>[], total: tbl.total || 0 })).catch(() => {});
      }
    }).catch(() => {});
  }, [selected]);

  const flatUniversities = useMemo(() => groups.flatMap((g) => g.cities.flatMap((c) => c.universities)), [groups]);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent side="right" className="w-[min(1100px,96vw)] max-w-none p-0">
        <div className="flex h-full flex-col">
          <SheetHeader className="border-b px-5 py-4">
            <SheetTitle>高校库</SheetTitle>
            <SheetDescription>按省市、985/211/双一流/普通本科筛选，并查看已抓取结果。</SheetDescription>
          </SheetHeader>
          <div className="grid flex-1 min-h-0 grid-cols-[280px_1fr]">
            <div className="border-r p-4">
              <div className="space-y-3">
                <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索学校" />
                <select className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={province} onChange={(e) => setProvince(e.target.value)}>
                  <option value="">全部省市</option>
                  {provinces.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
                <div className="flex flex-wrap gap-2">
                  {tiers.map((t) => (
                    <Button key={t} size="sm" variant={tier === t ? "default" : "outline"} onClick={() => setTier(t)}>{t}</Button>
                  ))}
                </div>
              </div>
              <ScrollArea className="mt-4 h-[calc(100vh-200px)]">
                <div className="space-y-1 pr-2">
                  {flatUniversities.map((u) => (
                    <button key={u.name} onClick={() => setSelected(u)} className={`w-full rounded-lg border px-3 py-2 text-left text-sm ${selected?.name === u.name ? "border-primary bg-primary/5" : "border-transparent hover:bg-muted/50"}`}>
                      <div className="font-medium">{u.name}</div>
                      <div className="text-xs text-muted-foreground">{u.province} · {u.city} · {u.tags.join(" / ")}</div>
                    </button>
                  ))}
                </div>
              </ScrollArea>
            </div>
            <div className="grid min-h-0 grid-cols-[1fr_420px]">
              <div className="min-h-0 border-r p-4">
                {selected ? (
                  <div className="space-y-4">
                    <div>
                      <div className="text-lg font-semibold">{selected.name}</div>
                      <div className="mt-1 text-sm text-muted-foreground">{selected.province} · {selected.city} · {selected.tags.join(" / ")}</div>
                    </div>
                    <div className="grid grid-cols-4 gap-3 text-sm">
                      <div className="rounded-lg border p-3"><div className="text-muted-foreground">文件</div><div className="mt-1 font-semibold">{selected.records.file_count}</div></div>
                      <div className="rounded-lg border p-3"><div className="text-muted-foreground">表格</div><div className="mt-1 font-semibold">{selected.records.table_count}</div></div>
                      <div className="rounded-lg border p-3"><div className="text-muted-foreground">行数</div><div className="mt-1 font-semibold">{selected.records.row_count}</div></div>
                      <div className="rounded-lg border p-3"><div className="text-muted-foreground">有效邮箱</div><div className="mt-1 font-semibold">{selected.records.valid_email_count}</div></div>
                    </div>
                    <div className="rounded-lg border">
                      <div className="border-b px-3 py-2 text-sm font-medium">来源文件</div>
                      <div className="divide-y">
                        {records.map((r) => (
                          <div key={`${r.task_id}-${r.filename}`} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                            <div className="min-w-0">
                              <div className="truncate font-medium">{r.filename}</div>
                              <div className="text-xs text-muted-foreground">{r.updated_at} · {r.row_count} 行 · {r.valid_email_count} 个有效邮箱</div>
                            </div>
                            {r.previewable ? <Button size="sm" variant="outline" onClick={() => api.getUniversityTable(selected.name, { task_id: r.task_id, file: r.filename, limit: 80 }).then((tbl) => setTable({ columns: tbl.columns || [], rows: (tbl.rows || []) as Record<string, string>[], total: tbl.total || 0 }))}>预览</Button> : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
              <div className="min-h-0 p-4">
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium">表格预览</div>
                    <div className="text-xs text-muted-foreground">共 {table.total} 行</div>
                  </div>
                </div>
                <ScrollArea className="h-[calc(100vh-220px)] rounded-lg border">
                  <table className="w-full text-left text-xs">
                    <thead className="sticky top-0 bg-background">
                      <tr>
                        {table.columns.map((col) => <th key={col} className="border-b px-3 py-2 font-medium">{col}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {table.rows.map((row, idx) => (
                        <tr key={idx} className="border-b last:border-b-0">
                          {table.columns.map((col) => <td key={col} className="max-w-[220px] border-b px-3 py-2 align-top">{row[col] || ""}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </ScrollArea>
              </div>
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
