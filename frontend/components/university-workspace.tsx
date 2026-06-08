"use client";

import { useEffect, useMemo, useState, useRef } from "react";
import { api } from "@/services/api";
import { useUIStore } from "@/stores/ui-store";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Download, Pencil, Plus, X, Check, Loader2, Trash2, Ellipsis, RefreshCw, Globe, ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuCheckboxItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import type { University, UniversityGroup, UniversityRecord } from "@/lib/types";

const tiers = ["全部", "985", "211", "双一流", "普通本科", "专科"] as const;

const EXPORT_FORMATS = [
  { key: "xlsx", label: "XLSX" },
  { key: "csv", label: "CSV" },
  { key: "md", label: "MD" },
  { key: "html", label: "HTML" },
  { key: "pdf", label: "PDF" },
  { key: "docx", label: "DOCX" },
];

function coverageColor(ratio: number): string {
  if (ratio >= 0.7) return 'hsl(142, 76%, 36%)';
  if (ratio >= 0.4) return 'hsl(38, 92%, 50%)';
  return 'hsl(0, 84%, 60%)';
}

export function UniversityWorkspace() {
  const open = useUIStore((s) => s.universityOpen);
  const setOpen = useUIStore((s) => s.setUniversityOpen);
  const setPendingInput = useUIStore((s) => s.setPendingInput);
  const highlightUniversity = useUIStore((s) => s.highlightUniversity);
  const setHighlightUniversity = useUIStore((s) => s.setHighlightUniversity);
  const [query, setQuery] = useState("");
  const [province, setProvince] = useState("");
  const [city, setCity] = useState("");
  const [tier, setTier] = useState<(typeof tiers)[number]>("全部");
  const [groups, setGroups] = useState<UniversityGroup[]>([]);
  const [provinces, setProvinces] = useState<string[]>([]);
  const [selected, setSelected] = useState<University | null>(null);
  const [onlyWithData, setOnlyWithData] = useState(false);
  const [displayLimit, setDisplayLimit] = useState(100);

  // 版本记录列表 & 当前选中索引
  const [records, setRecords] = useState<UniversityRecord[]>([]);
  const [recordIndex, setRecordIndex] = useState(0);
  const selectedRecord = records[recordIndex] || null;

  // 表格过滤/分页状态
  const [tableQuery, setTableQuery] = useState("");
  const [tableDept, setTableDept] = useState("");
  const [validOnly, setValidOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [availableDepts, setAvailableDepts] = useState<string[]>([]);
  const [pageSize, setPageSize] = useState(50);
  const [visibleColumns, setVisibleColumns] = useState<string[]>([]);

  const [table, setTable] = useState<{ columns: string[]; rows: Record<string, string>[]; total: number }>({ columns: [], rows: [], total: 0 });

  // 导出状态
  const [exporting, setExporting] = useState<string | null>(null);

  // 表格编辑状态
  const [editingRowIndex, setEditingRowIndex] = useState<number | null>(null);
  const [editValues, setEditValues] = useState<Record<string, string>>({});
  const [addingRow, setAddingRow] = useState(false);
  const [newRowValues, setNewRowValues] = useState<Record<string, string>>({});

  // 面板无极缩放
  const [leftWidth, setLeftWidth] = useState(280);
  const [dragging, setDragging] = useState<boolean>(false);
  const sheetContentRef = useRef<HTMLDivElement>(null);

  // 拖拽调宽鼠标事件
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!dragging || !sheetContentRef.current) return;
      const rect = sheetContentRef.current.getBoundingClientRect();
      setLeftWidth(Math.max(180, Math.min(500, e.clientX - rect.left)));
    };
    const handleMouseUp = () => setDragging(false);
    if (dragging) {
      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    }
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [dragging]);

  // 同步滚动
  const topScrollRef = useRef<HTMLDivElement>(null);
  const tableScrollRef = useRef<HTMLDivElement>(null);
  const [tableScrollWidth, setTableScrollWidth] = useState(0);

  const displayColumns = useMemo(() => table.columns.filter(c => c !== "_index"), [table.columns]);

  const handleTopScroll = () => {
    if (topScrollRef.current && tableScrollRef.current) {
      tableScrollRef.current.scrollLeft = topScrollRef.current.scrollLeft;
    }
  };

  const handleTableScroll = () => {
    if (topScrollRef.current && tableScrollRef.current) {
      topScrollRef.current.scrollLeft = tableScrollRef.current.scrollLeft;
    }
  };

  // 当 displayColumns 变化时初始化 visibleColumns
  useEffect(() => {
    if (displayColumns.length > 0 && visibleColumns.length === 0) {
      setVisibleColumns(displayColumns);
    }
  }, [displayColumns]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (tableScrollRef.current) setTableScrollWidth(tableScrollRef.current.scrollWidth);
      if (topScrollRef.current) topScrollRef.current.scrollLeft = 0;
      if (tableScrollRef.current) tableScrollRef.current.scrollLeft = 0;
    }, 100);
    return () => clearTimeout(timer);
  }, [table.rows]);

  useEffect(() => {
    const handleResize = () => {
      if (tableScrollRef.current) setTableScrollWidth(tableScrollRef.current.scrollWidth);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // 加载高校列表
  useEffect(() => {
    if (!open) return;
    api.getUniversities({ province, tier, q: query }).then((data: any) => {
      setGroups(data.groups || []);
      setProvinces(data.provinces || []);
      const first = data.groups?.[0]?.cities?.[0]?.universities?.[0] || null;
      if (first && !selected) setSelected(first);
    }).catch(() => {});
  }, [open, province, tier, query]);

  // 高亮跳转：当 highlightUniversity 设置时，选中对应大学
  useEffect(() => {
    if (!highlightUniversity || !open) return;
    const target = flatUniversities.find((u) => u.name === highlightUniversity);
    if (target) {
      setSelected(target);
      // 清除高亮标记
      const timer = setTimeout(() => setHighlightUniversity(null), 2000);
      return () => clearTimeout(timer);
    }
  }, [highlightUniversity, open]);

  // 快捷操作：从高校库跳转到聊天
  const handleQuickCrawl = (uniName: string, mode: "incremental" | "full") => {
    const prefix = mode === "incremental" ? "补充" : "重新全量抓取";
    setPendingInput(`${prefix}${uniName}教师邮箱`);
    setOpen(false);
  };

  // 加载高校最佳文件记录（自动选择数据最多的表格）
  useEffect(() => {
    if (!selected) {
      setRecords([]);
      setRecordIndex(0);
      setTable({ columns: [], rows: [], total: 0 });
      setAvailableDepts([]);
      return;
    }
    api.getUniversityRecords(selected.name).then((data: any) => {
      const recs = data.records || [];
      setRecords(recs);
      setRecordIndex(0);
      setTableQuery("");
      setTableDept("");
      setValidOnly(false);
      setPage(1);
    }).catch(() => {});
  }, [selected]);

  // 加载表格数据
  useEffect(() => {
    if (!selected || !selectedRecord) {
      setTable({ columns: [], rows: [], total: 0 });
      setAvailableDepts([]);
      return;
    }
    api.getUniversityTable(selected.name, {
      task_id: selectedRecord.task_id,
      file: selectedRecord.filename,
      limit: pageSize,
      offset: (page - 1) * pageSize,
      q: tableQuery,
      department: tableDept,
      valid_only: validOnly,
    }).then((tbl) => {
      setTable({
        columns: tbl.columns || [],
        rows: (tbl.rows || []) as Record<string, string>[],
        total: tbl.total || 0,
      });
      setAvailableDepts(tbl.departments || []);
      setEditingRowIndex(null);
      setAddingRow(false);
    }).catch(() => {});
  }, [selected, selectedRecord, tableQuery, tableDept, validOnly, page, pageSize]);

  const handleQueryChange = (val: string) => { setTableQuery(val); setPage(1); };
  const handleDeptChange = (val: string) => { setTableDept(val); setPage(1); };
  const handleValidOnlyChange = (val: boolean) => { setValidOnly(val); setPage(1); };
  const handleProvinceChange = (newProv: string) => { setProvince(newProv); setCity(""); };

  const availableCities = useMemo(() => {
    if (!province) return [];
    const group = groups.find((g) => g.province === province);
    if (!group) return [];
    return group.cities.map((c) => c.city);
  }, [province, groups]);

  const flatUniversities = useMemo(() => {
    let list = groups.flatMap((g) => g.cities.flatMap((c) => c.universities));
    if (city) list = list.filter((u) => u.city === city);
    if (onlyWithData) list = list.filter((u) => u.has_data);
    return list;
  }, [groups, city, onlyWithData]);

  // ── 导出 ──
  const handleExport = async (format: string) => {
    if (!selected || !selectedRecord) return;
    setExporting(format);
    try {
      const res = await api.exportUniversityTable(selected.name, selectedRecord.task_id, selectedRecord.filename, [format]);
      if (res.ok && res.files?.[format]) {
        // 使用 fetch + Blob 下载，避免中文路径在 window.open 中出错
        const url = api.getBackendUrl() + res.files[format];
        const blobRes = await fetch(url);
        if (blobRes.ok) {
          const blob = await blobRes.blob();
          const blobUrl = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = blobUrl;
          a.download = `${selected.name}_教师邮箱.${format}`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(blobUrl);
        } else {
          // fallback: window.open
          window.open(url, "_blank");
        }
      }
    } catch { /* ignore */ }
    setExporting(null);
  };

  // ── 表格行 CRUD ──

  const handleEditStart = (row: Record<string, string>) => {
    const idx = parseInt(row._index || "0", 10);
    setEditingRowIndex(idx);
    const vals: Record<string, string> = {};
    for (const col of displayColumns) vals[col] = row[col] || "";
    setEditValues(vals);
  };

  const handleEditCancel = () => { setEditingRowIndex(null); setEditValues({}); };

  const handleEditSave = async () => {
    if (!selected || !selectedRecord || editingRowIndex === null) return;
    try {
      await api.updateTableRow(selected.name, selectedRecord.task_id, selectedRecord.filename, editingRowIndex, editValues);
      await reloadTable();
      setEditingRowIndex(null); setEditValues({});
    } catch { /* ignore */ }
  };

  const handleDeleteRow = async (row: Record<string, string>) => {
    if (!selected || !selectedRecord) return;
    if (!confirm("确定删除该行？")) return;
    const idx = parseInt(row._index || "0", 10);
    try {
      await api.deleteTableRow(selected.name, selectedRecord.task_id, selectedRecord.filename, idx);
      await reloadTable();
    } catch { /* ignore */ }
  };

  const handleAddRowStart = () => {
    const vals: Record<string, string> = {};
    for (const col of displayColumns) vals[col] = "";
    setNewRowValues(vals);
    setAddingRow(true);
  };

  const handleAddRowCancel = () => { setAddingRow(false); setNewRowValues({}); };

  const handleAddRowSave = async () => {
    if (!selected || !selectedRecord) return;
    try {
      await api.addTableRow(selected.name, selectedRecord.task_id, selectedRecord.filename, newRowValues);
      setAddingRow(false); setNewRowValues({});
      const tbl = await api.getUniversityTable(selected.name, {
        task_id: selectedRecord.task_id, file: selectedRecord.filename,
        limit: pageSize, offset: 0, q: tableQuery, department: tableDept, valid_only: validOnly,
      });
      setTable({
        columns: tbl.columns || [],
        rows: (tbl.rows || []) as Record<string, string>[],
        total: tbl.total || 0,
      });
      setPage(Math.ceil((tbl.total) / pageSize) || 1);
    } catch { /* ignore */ }
  };

  const reloadTable = async () => {
    if (!selected || !selectedRecord) return;
    const tbl = await api.getUniversityTable(selected.name, {
      task_id: selectedRecord.task_id, file: selectedRecord.filename,
      limit: pageSize, offset: (page - 1) * pageSize, q: tableQuery, department: tableDept, valid_only: validOnly,
    });
    setTable({
      columns: tbl.columns || [],
      rows: (tbl.rows || []) as Record<string, string>[],
      total: tbl.total || 0,
    });
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent side="right" className="w-[min(1100px,96vw)] max-w-none sm:max-w-none data-[side=right]:sm:max-w-none gap-0 p-0 overflow-hidden" style={{overflow: 'hidden'}}>
        <div ref={sheetContentRef} className="flex h-full flex-col overflow-hidden">
          <SheetHeader className="border-b px-5 py-4">
            <SheetTitle>高校库</SheetTitle>
            <SheetDescription>按省市、985/211/双一流/普通本科筛选，查看各高校已抓取的教师邮箱数据，支持导出多种格式。</SheetDescription>
          </SheetHeader>

          <div className="flex flex-1 min-h-0">
            {/* ── 左侧：高校导航 ── */}
            <div style={{ width: `${leftWidth}px` }} className="shrink-0 flex flex-col h-full min-h-0 overflow-hidden">
              <div className="p-4 pb-0 space-y-3">
                <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索学校" />
                <div className="grid grid-cols-2 gap-2">
                  <select className="h-9 rounded-md border bg-background px-2 text-xs" value={province} onChange={(e) => handleProvinceChange(e.target.value)}>
                    <option value="">省/直辖市</option>
                    {provinces.map((p) => <option key={p} value={p}>{p}</option>)}
                  </select>
                  <select className="h-9 rounded-md border bg-background px-2 text-xs" value={city} onChange={(e) => setCity(e.target.value)} disabled={!province}>
                    <option value="">城市</option>
                    {availableCities.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div className="flex flex-wrap gap-2">
                  {tiers.map((t) => (
                    <Button key={t} size="sm" variant={tier === t ? "default" : "outline"} onClick={() => setTier(t)}>{t}</Button>
                  ))}
                </div>
                <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer select-none mt-2">
                  <input type="checkbox" checked={onlyWithData} onChange={(e) => setOnlyWithData(e.target.checked)}
                    className="rounded border-gray-300 text-primary focus:ring-primary size-3.5" />
                  仅显示有数据的高校
                </label>
              </div>
              <ScrollArea className="flex-1 mt-4 px-4 min-h-0" style={{minHeight: 0, height: 'auto'}}>
                <div className="space-y-1 pr-2">
                  {flatUniversities.length === 0 ? (
                    <div className="py-8 text-center text-xs text-muted-foreground">无匹配高校</div>
                  ) : (
                    <>
                    {flatUniversities.slice(0, displayLimit).map((u) => (
                      <div key={u.name || u.province || "unknown-"+Math.random().toString(36).slice(2,6)} className={`group relative rounded-lg border ${selected?.name === u.name ? "border-primary bg-primary/5" : (highlightUniversity === u.name ? "border-primary ring-2 ring-primary/30" : "border-transparent hover:bg-muted/50")}`}>
                        <button onClick={() => setSelected(u)} className="w-full px-3 py-2 text-left text-sm">
                          <div className="font-medium flex items-center gap-1.5">
                            {u.name}
                            {u.has_data && <span className="text-green-600 shrink-0 text-xs leading-none">✓</span>}
                          </div>
                          <div className="text-xs text-muted-foreground">{u.province} · {u.city} · {u.tags.join(" / ")}</div>
                          {(u as any).records?.row_count > 0 && (
                            <div className="flex items-center gap-1 mt-1">
                              <div className="h-1.5 flex-1 rounded-full bg-muted overflow-hidden">
                                <div className="h-full rounded-full" style={{
                                  width: `${Math.min(100, Math.round(((u as any).records?.valid_email_count || 0) / ((u as any).records?.row_count || 1) * 100))}%`,
                                  backgroundColor: coverageColor(((u as any).records?.valid_email_count || 0) / ((u as any).records?.row_count || 1))
                                }} />
                              </div>
                              <span className="text-[10px] text-muted-foreground shrink-0">
                                {Math.round(((u as any).records?.valid_email_count || 0) / ((u as any).records?.row_count || 1) * 100)}%
                              </span>
                            </div>
                          )}
                        </button>
                        {/* ⋮ 快捷操作菜单 */}
                        <DropdownMenu>
                          <DropdownMenuTrigger className="absolute right-1.5 top-1.5 rounded-md p-1 text-muted-foreground/50 hover:bg-muted hover:text-muted-foreground transition-colors">
                            <Ellipsis className="size-3.5" />
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-40">
                            <DropdownMenuItem
                              onClick={() => handleQuickCrawl(u.name, "incremental")}
                              className="gap-2 text-xs"
                            >
                              <RefreshCw className="size-3" />
                              补充缺失数据
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => handleQuickCrawl(u.name, "full")}
                              className="gap-2 text-xs"
                            >
                              <Globe className="size-3" />
                              重新全量抓取
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    ))}
                    {displayLimit < flatUniversities.length && (
                      <button onClick={() => setDisplayLimit(d => d + 200)} className="w-full py-2 text-xs text-muted-foreground hover:text-primary transition-colors">
                        显示更多（{flatUniversities.length - displayLimit} 所）
                      </button>
                    )}
                    </>
                  )}
                </div>
              </ScrollArea>
            </div>

            {/* ── 拖拽手柄 ── */}
            <div
              className="relative w-1.5 shrink-0 cursor-col-resize bg-transparent hover:bg-primary/10 active:bg-primary/20 transition-colors before:absolute before:inset-y-0 before:left-1/2 before:w-px before:-translate-x-1/2 before:bg-border"
              onMouseDown={() => setDragging(true)}
            />

            {/* ── 右侧：学校详情 + 表格预览 + 导出 ── */}
            <div className="flex-1 min-w-0 p-4 flex flex-col h-full overflow-hidden">
              {selected ? (
                <>
                  {/* 学校信息 + 统计 + 格式导出 */}
                  <div className="shrink-0 space-y-3">
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="text-lg font-semibold flex items-center gap-2">
                          {selected.name}
                          {selected.has_data && <span className="text-green-600 text-xs">✓ 已抓取</span>}
                        </div>
                        <div className="text-xs text-muted-foreground mt-0.5">{selected.province} · {selected.city} · {selected.tags.join(" / ")}</div>
                      </div>
                    </div>
                    <div className="grid grid-cols-4 gap-3 text-sm">
                      <div className="rounded-lg border p-3"><div className="text-muted-foreground text-xs">文件</div><div className="mt-1 font-semibold">{records.length}</div></div>
                      <div className="rounded-lg border p-3"><div className="text-muted-foreground text-xs">表格</div><div className="mt-1 font-semibold">{selectedRecord ? 1 : 0}</div></div>
                      <div className="rounded-lg border p-3"><div className="text-muted-foreground text-xs">行数</div><div className="mt-1 font-semibold">{selectedRecord?.row_count || 0}</div></div>
                      <div className="rounded-lg border p-3"><div className="text-muted-foreground text-xs">有效邮箱</div><div className="mt-1 font-semibold">{selectedRecord?.valid_email_count || 0}</div></div>
                    </div>
                    {/* 导出按钮组 */}
                    {selectedRecord && (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-xs text-muted-foreground mr-1">导出：</span>
                        {EXPORT_FORMATS.map((fmt) => (
                          <Button
                            key={fmt.key}
                            size="sm"
                            variant="outline"
                            className="h-7 px-2.5 text-xs"
                            onClick={() => handleExport(fmt.key)}
                            disabled={exporting === fmt.key}
                          >
                            {exporting === fmt.key ? (
                              <Loader2 className="size-3 mr-1 animate-spin" />
                            ) : (
                              <Download className="size-3 mr-1" />
                            )}
                            {fmt.label}
                          </Button>
                        ))}
                        {exporting && <span className="text-xs text-muted-foreground ml-1">正在生成 {exporting.toUpperCase()}...</span>}
                      </div>
                    )}
                  </div>

                  {/* 表格预览 */}
                  <div className="mt-4 flex-1 flex flex-col min-h-0 min-w-0">
                    {selectedRecord ? (
                      <div className="flex flex-col flex-1 min-h-0">
                        {/* 版本 Tab 选择器 */}
                        {records.length > 0 && (
                          <div className="flex items-center gap-2 mb-2">
                            <span className="text-xs text-muted-foreground shrink-0">版本：</span>
                            <div className="flex gap-1 overflow-x-auto">
                              {records.map((rec, i) => (
                                <button
                                  key={rec.task_id + rec.filename}
                                  onClick={() => { setRecordIndex(i); setPage(1); }}
                                  className={`px-2.5 py-1 text-xs rounded-md whitespace-nowrap transition-colors ${
                                    i === recordIndex
                                      ? 'bg-primary text-primary-foreground'
                                      : 'bg-muted hover:bg-muted/80 text-muted-foreground'
                                  }`}
                                >
                                  {rec.filename?.replace(/\.[^.]+$/, '') || `版本 ${i + 1}`}
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                        {/* 控制栏 */}
                        <div className="mb-3 space-y-2 rounded-lg border bg-muted/30 p-2.5 shrink-0">
                          <Input value={tableQuery} onChange={(e) => handleQueryChange(e.target.value)} placeholder="搜索姓名/邮箱" className="h-8 text-xs bg-background" />
                          <div className="flex items-center justify-between gap-2">
                            <select className="h-8 flex-1 min-w-0 rounded-md border bg-background px-2 text-xs" value={tableDept} onChange={(e) => handleDeptChange(e.target.value)}>
                              <option value="">全部院系</option>
                              {availableDepts.map((d) => <option key={d} value={d}>{d}</option>)}
                            </select>
                            <div className="flex items-center gap-2">
                              <label className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground cursor-pointer select-none">
                                <input type="checkbox" checked={validOnly} onChange={(e) => handleValidOnlyChange(e.target.checked)} className="rounded border-gray-300 text-primary focus:ring-primary size-3.5" />
                                <span>仅看有效邮箱</span>
                              </label>
                              {displayColumns.length > 0 && (
                                <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={handleAddRowStart}>
                                  <Plus className="size-3 mr-1" />添加行
                                </Button>
                              )}
                              <DropdownMenu>
                                <DropdownMenuTrigger className="inline-flex shrink-0 items-center justify-center border border-border bg-background bg-clip-padding text-sm font-medium whitespace-nowrap transition-all outline-none select-none h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-[0.8rem] hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-3.5">
                                    列 <ChevronDown className="size-3 ml-1" />
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end" className="w-44">
                                  {displayColumns.map((col) => (
                                    <DropdownMenuCheckboxItem
                                      key={col}
                                      checked={visibleColumns.includes(col)}
                                      onCheckedChange={(checked) => {
                                        setVisibleColumns(prev =>
                                          checked ? [...prev, col] : prev.filter(c => c !== col)
                                        );
                                      }}
                                    >
                                      {col}
                                    </DropdownMenuCheckboxItem>
                                  ))}
                                </DropdownMenuContent>
                              </DropdownMenu>
                            </div>
                          </div>
                        </div>

                        {/* 顶部同步横向滚动条 */}
                        <div
                          ref={topScrollRef}
                          onScroll={handleTopScroll}
                          className="w-full overflow-x-auto overflow-y-hidden h-2.5 shrink-0 bg-transparent mb-1.5 [&::-webkit-scrollbar]:h-2 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-muted-foreground/25 hover:[&::-webkit-scrollbar-thumb]:bg-muted-foreground/40 [&::-webkit-scrollbar-track]:bg-transparent"
                        >
                          <div style={{ width: `${tableScrollWidth}px` }} className="h-px" />
                        </div>

                        {/* 表格滚动区 */}
                        <div
                          ref={tableScrollRef}
                          onScroll={handleTableScroll}
                          className="flex-1 overflow-auto rounded-lg border bg-background [&::-webkit-scrollbar]:h-2 [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-muted-foreground/25 hover:[&::-webkit-scrollbar-thumb]:bg-muted-foreground/40 [&::-webkit-scrollbar-track]:bg-transparent"
                        >
                          <table className="w-full min-w-max text-left text-xs table-auto">
                            <thead className="sticky top-0 bg-muted/95 backdrop-blur-sm z-10">
                              <tr className="border-b">
                                {visibleColumns.map((col) => (
                                  <th key={col} className="px-3 py-2 font-medium bg-muted text-muted-foreground whitespace-nowrap">{col}</th>
                                ))}
                                <th className="px-3 py-2 font-medium bg-muted text-muted-foreground w-16">操作</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y">
                              {addingRow && (
                                <tr className="bg-primary/5">
                                  {visibleColumns.map((col) => (
                                    <td key={col} className="px-1 py-1">
                                      <Input
                                        value={newRowValues[col] || ""}
                                        onChange={(e) => setNewRowValues(v => ({ ...v, [col]: e.target.value }))}
                                        className="h-7 text-xs" placeholder={col}
                                      />
                                    </td>
                                  ))}
                                  <td className="px-1 py-1">
                                    <div className="flex items-center gap-0.5">
                                      <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-green-600" onClick={handleAddRowSave}><Check className="size-3.5" /></Button>
                                      <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={handleAddRowCancel}><X className="size-3.5" /></Button>
                                    </div>
                                  </td>
                                </tr>
                              )}
                              {table.rows.map((row, idx) => {
                                const rowIdx = parseInt(row._index || "0", 10);
                                const isEditing = editingRowIndex === rowIdx;
                                return (
                                  <tr key={`${rowIdx}-${idx}`} className="hover:bg-muted/30">
                                    {visibleColumns.map((col) => (
                                      <td key={col} className="px-3 py-2 align-top text-foreground max-w-[200px] overflow-hidden text-ellipsis">
                                        {isEditing ? (
                                          <Input
                                            value={editValues[col] || ""}
                                            onChange={(e) => setEditValues(v => ({ ...v, [col]: e.target.value }))}
                                            className="h-7 text-xs"
                                          />
                                        ) : (row[col] || "")}
                                      </td>
                                    ))}
                                    <td className="px-3 py-2 align-top">
                                      {isEditing ? (
                                        <div className="flex items-center gap-0.5">
                                          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-green-600" onClick={handleEditSave} title="保存"><Check className="size-3.5" /></Button>
                                          <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={handleEditCancel} title="取消"><X className="size-3.5" /></Button>
                                        </div>
                                      ) : (
                                        <div className="flex items-center gap-0.5">
                                          <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => handleEditStart(row)} title="编辑"><Pencil className="size-3" /></Button>
                                          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-destructive" onClick={() => handleDeleteRow(row)} title="删除"><Trash2 className="size-3" /></Button>
                                        </div>
                                      )}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>

                        {/* 分页 */}
                        <div className="mt-3 flex items-center justify-between text-xs shrink-0">
                          <div className="flex items-center gap-2">
                            <Button size="sm" variant="outline" className="h-7 px-2" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</Button>
                            <select className="h-7 rounded-md border bg-background px-2 text-xs" value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
                              <option value="20">20条/页</option>
                              <option value="50">50条/页</option>
                              <option value="100">100条/页</option>
                              <option value="200">200条/页</option>
                            </select>
                          </div>
                          <span className="text-muted-foreground">
                            第 {page} 页 / 共 {Math.ceil(table.total / pageSize) || 1} 页
                            {selectedRecord && ` · ${selectedRecord.filename}`}
                          </span>
                          <Button size="sm" variant="outline" className="h-7 px-2" disabled={page >= Math.ceil(table.total / pageSize)} onClick={() => setPage(p => p + 1)}>下一页</Button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-1 items-center justify-center text-xs text-muted-foreground border border-dashed rounded-lg">
                        {selected.records.table_count === 0
                          ? "该高校暂无抓取数据，请先通过 Agent 爬取教师邮箱"
                          : "请等待数据加载..."}
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="flex flex-1 items-center justify-center text-xs text-muted-foreground border border-dashed rounded-lg">
                  请从左侧选择一所高校
                </div>
              )}
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
