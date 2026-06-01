"use client";

import { useEffect, useMemo, useState, useRef } from "react";
import { api } from "@/services/api";
import { useUIStore } from "@/stores/ui-store";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Download, Trash2, Pencil, Plus, X, Check, Upload, Sparkles, Loader2 } from "lucide-react";
import type { University, UniversityGroup, UniversityRecord } from "@/lib/types";

const tiers = ["全部", "985", "211", "双一流", "普通本科"] as const;

export function UniversityWorkspace() {
  const open = useUIStore((s) => s.universityOpen);
  const setOpen = useUIStore((s) => s.setUniversityOpen);
  const [query, setQuery] = useState("");
  const [province, setProvince] = useState("");
  const [city, setCity] = useState("");
  const [tier, setTier] = useState<(typeof tiers)[number]>("全部");
  const [groups, setGroups] = useState<UniversityGroup[]>([]);
  const [provinces, setProvinces] = useState<string[]>([]);
  const [selected, setSelected] = useState<University | null>(null);
  const [records, setRecords] = useState<UniversityRecord[]>([]);
  const [selectedRecord, setSelectedRecord] = useState<UniversityRecord | null>(null);

  // 表格过滤/分页状态
  const [tableQuery, setTableQuery] = useState("");
  const [tableDept, setTableDept] = useState("");
  const [validOnly, setValidOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [availableDepts, setAvailableDepts] = useState<string[]>([]);
  const pageSize = 50;

  const [table, setTable] = useState<{ columns: string[]; rows: Record<string, string>[]; total: number }>({ columns: [], rows: [], total: 0 });

  // 文件重命名状态
  const [renamingFile, setRenamingFile] = useState<{ task_id: string; filename: string } | null>(null);
  const [renameValue, setRenameValue] = useState("");

  // 表格编辑状态
  const [editingRowIndex, setEditingRowIndex] = useState<number | null>(null);
  const [editValues, setEditValues] = useState<Record<string, string>>({});
  const [addingRow, setAddingRow] = useState(false);
  const [newRowValues, setNewRowValues] = useState<Record<string, string>>({});

  // 一键清洗状态
  const [cleaning, setCleaning] = useState(false);
  const [cleanProgress, setCleanProgress] = useState("");
  const [cleanResult, setCleanResult] = useState<Record<string, any> | null>(null);

  // 面板无极缩放
  const [leftWidth, setLeftWidth] = useState(280);
  const [filesWidth, setFilesWidth] = useState(380);
  const [dragging, setDragging] = useState<"left" | "files" | null>(null);
  const sheetContentRef = useRef<HTMLDivElement>(null);
  const rightPanelRef = useRef<HTMLDivElement>(null);

  // 拖拽调宽鼠标事件
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!dragging || !sheetContentRef.current) return;
      if (dragging === "left") {
        const rect = sheetContentRef.current.getBoundingClientRect();
        setLeftWidth(Math.max(180, Math.min(500, e.clientX - rect.left)));
      } else if (dragging === "files" && rightPanelRef.current) {
        const rect = rightPanelRef.current.getBoundingClientRect();
        setFilesWidth(Math.max(240, Math.min(700, e.clientX - rect.left)));
      }
    };
    const handleMouseUp = () => setDragging(null);
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

  // 文件上传
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 同步滚动
  const topScrollRef = useRef<HTMLDivElement>(null);
  const tableScrollRef = useRef<HTMLDivElement>(null);
  const [tableScrollWidth, setTableScrollWidth] = useState(0);

  // 排除 _index 列的显示列
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

  // 测量表格实际滚动宽度并重置滚动位置
  useEffect(() => {
    const timer = setTimeout(() => {
      if (tableScrollRef.current) {
        setTableScrollWidth(tableScrollRef.current.scrollWidth);
      }
      if (topScrollRef.current) topScrollRef.current.scrollLeft = 0;
      if (tableScrollRef.current) tableScrollRef.current.scrollLeft = 0;
    }, 100);
    return () => clearTimeout(timer);
  }, [table.rows]);

  useEffect(() => {
    const handleResize = () => {
      if (tableScrollRef.current) {
        setTableScrollWidth(tableScrollRef.current.scrollWidth);
      }
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

  // 加载高校文件记录
  useEffect(() => {
    if (!selected) {
      setRecords([]);
      setSelectedRecord(null);
      return;
    }
    api.getUniversityRecords(selected.name).then((data: any) => {
      const recs = data.records || [];
      setRecords(recs);
      const first = recs.find((r: UniversityRecord) => r.previewable);
      setSelectedRecord(first || null);
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
      // 切换数据时重置编辑状态
      setEditingRowIndex(null);
      setAddingRow(false);
    }).catch(() => {});
  }, [selected, selectedRecord, tableQuery, tableDept, validOnly, page]);

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
    return list;
  }, [groups, city]);

  // ── 来源文件 CRUD ──

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selected) return;
    try {
      await api.uploadUniversityFile(selected.name, file);
      const data = await api.getUniversityRecords(selected.name);
      setRecords(data.records || []);
    } catch { /* ignore */ }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleFileDelete = async (task_id: string, filename: string) => {
    if (!selected) return;
    if (!confirm(`确定删除文件「${filename}」？`)) return;
    try {
      await api.deleteUniversityFile(selected.name, task_id, filename);
      const data = await api.getUniversityRecords(selected.name);
      setRecords(data.records || []);
    } catch { /* ignore */ }
  };

  const handleFileRenameStart = (task_id: string, filename: string) => {
    setRenamingFile({ task_id, filename });
    setRenameValue(filename);
  };

  const handleFileRenameConfirm = async () => {
    if (!selected || !renamingFile || !renameValue.trim()) return;
    try {
      await api.renameUniversityFile(selected.name, renamingFile.task_id, renamingFile.filename, renameValue.trim());
      setRenamingFile(null);
      setRenameValue("");
      const data = await api.getUniversityRecords(selected.name);
      setRecords(data.records || []);
    } catch { /* ignore */ }
  };

  const handleFileRenameCancel = () => {
    setRenamingFile(null);
    setRenameValue("");
  };

  // ── 一键清洗 ──
  const handleClean = async () => {
    if (!selected || cleaning) return;
    setCleaning(true);
    setCleanProgress("正在扫描高校表格文件...");
    setCleanResult(null);
    try {
      const res = await api.cleanUniversityTables(selected.name);
      if (res.ok) {
        setCleanProgress("");
        setCleanResult(res);
        // 刷新文件列表
        const data = await api.getUniversityRecords(selected.name);
        setRecords(data.records || []);
      } else {
        setCleanProgress("");
        setCleanResult({ error: res.error });
      }
    } catch (err) {
      setCleanProgress("");
      setCleanResult({ error: `请求失败: ${err instanceof Error ? err.message : "未知错误"}` });
    } finally {
      setCleaning(false);
    }
  };

  // ── 表格行 CRUD ──

  const handleEditStart = (row: Record<string, string>) => {
    const idx = parseInt(row._index || "0", 10);
    setEditingRowIndex(idx);
    const vals: Record<string, string> = {};
    for (const col of displayColumns) {
      vals[col] = row[col] || "";
    }
    setEditValues(vals);
  };

  const handleEditCancel = () => {
    setEditingRowIndex(null);
    setEditValues({});
  };

  const handleEditSave = async () => {
    if (!selected || !selectedRecord || editingRowIndex === null) return;
    try {
      await api.updateTableRow(selected.name, selectedRecord.task_id, selectedRecord.filename, editingRowIndex, editValues);
      await reloadTable();
      setEditingRowIndex(null);
      setEditValues({});
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
    for (const col of displayColumns) {
      vals[col] = "";
    }
    setNewRowValues(vals);
    setAddingRow(true);
  };

  const handleAddRowCancel = () => {
    setAddingRow(false);
    setNewRowValues({});
  };

  const handleAddRowSave = async () => {
    if (!selected || !selectedRecord) return;
    try {
      await api.addTableRow(selected.name, selectedRecord.task_id, selectedRecord.filename, newRowValues);
      setAddingRow(false);
      setNewRowValues({});
      // 跳转到最后一页查看新行
      const tbl = await api.getUniversityTable(selected.name, {
        task_id: selectedRecord.task_id,
        file: selectedRecord.filename,
        limit: pageSize,
        offset: 0,
        q: tableQuery,
        department: tableDept,
        valid_only: validOnly,
      });
      setTable({
        columns: tbl.columns || [],
        rows: (tbl.rows || []) as Record<string, string>[],
        total: tbl.total || 0,
      });
      const lastPage = Math.ceil((tbl.total) / pageSize);
      setPage(lastPage || 1);
    } catch { /* ignore */ }
  };

  const reloadTable = async () => {
    if (!selected || !selectedRecord) return;
    const tbl = await api.getUniversityTable(selected.name, {
      task_id: selectedRecord.task_id,
      file: selectedRecord.filename,
      limit: pageSize,
      offset: (page - 1) * pageSize,
      q: tableQuery,
      department: tableDept,
      valid_only: validOnly,
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
            <SheetDescription>按省市、985/211/双一流/普通本科筛选，并查看已抓取结果。</SheetDescription>
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
              </div>
              <ScrollArea className="flex-1 mt-4 px-4 min-h-0" style={{minHeight: 0, height: 'auto'}}>
                <div className="space-y-1 pr-2">
                  {flatUniversities.length === 0 ? (
                    <div className="py-8 text-center text-xs text-muted-foreground">无匹配高校</div>
                  ) : (
                    flatUniversities.map((u) => (
                      <button key={u.name} onClick={() => setSelected(u)} className={`w-full rounded-lg border px-3 py-2 text-left text-sm ${selected?.name === u.name ? "border-primary bg-primary/5" : "border-transparent hover:bg-muted/50"}`}>
                        <div className="font-medium">{u.name}</div>
                        <div className="text-xs text-muted-foreground">{u.province} · {u.city} · {u.tags.join(" / ")}</div>
                      </button>
                    ))
                  )}
                </div>
              </ScrollArea>
            </div>

            {/* ── 拖拽手柄 1 ── */}
            <div
              className="relative w-1.5 shrink-0 cursor-col-resize bg-transparent hover:bg-primary/10 active:bg-primary/20 transition-colors before:absolute before:inset-y-0 before:left-1/2 before:w-px before:-translate-x-1/2 before:bg-border"
              onMouseDown={() => setDragging("left")}
            />

            {/* ── 右侧：详情 + 文件 + 表格预览 ── */}
            <div ref={rightPanelRef} className="flex flex-1 min-w-0 overflow-hidden">
              {/* 右子列 1：学校详情 + 可滚动的来源文件 */}
              <div style={{ width: `${filesWidth}px` }} className="shrink-0 p-4 flex flex-col h-full overflow-hidden">
                {selected ? (
                  <>
                    {/* 固定头部：校名 + 统计 */}
                    <div className="shrink-0 space-y-4">
                      <div>
                        <div className="text-lg font-semibold">{selected.name}</div>
                        <div className="mt-1 text-sm text-muted-foreground">{selected.province} · {selected.city} · {selected.tags.join(" / ")}</div>
                      </div>
                      <div className="grid grid-cols-4 gap-3 text-sm">
                        <div className="rounded-lg border p-3"><div className="text-muted-foreground text-xs">文件</div><div className="mt-1 font-semibold">{selected.records.file_count}</div></div>
                        <div className="rounded-lg border p-3"><div className="text-muted-foreground text-xs">表格</div><div className="mt-1 font-semibold">{selected.records.table_count}</div></div>
                        <div className="rounded-lg border p-3"><div className="text-muted-foreground text-xs">行数</div><div className="mt-1 font-semibold">{selected.records.row_count}</div></div>
                        <div className="rounded-lg border p-3"><div className="text-muted-foreground text-xs">有效邮箱</div><div className="mt-1 font-semibold">{selected.records.valid_email_count}</div></div>
                      </div>
                    </div>

                    {/* 清洗进度/结果提示 */}
                    {cleanProgress && (
                      <div className="mt-3 flex items-center gap-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-xs text-primary">
                        <Loader2 className="size-3 animate-spin" />
                        <span>{cleanProgress}</span>
                      </div>
                    )}
                    {cleanResult && !cleanProgress && (
                      <div className="mt-3 space-y-1 rounded-lg border bg-muted/30 px-3 py-2 text-xs">
                        <div className="font-medium text-green-600">✅ 清洗完成</div>
                        {cleanResult.error ? (
                          <div className="text-destructive">{cleanResult.error}</div>
                        ) : cleanResult.stats ? (
                          <div className="text-muted-foreground space-y-0.5">
                            <div>去重前: {cleanResult.stats.total_before} → 去重后: {cleanResult.stats.total_after}</div>
                            <div>按邮箱去重: {cleanResult.stats.deduped} 条 | 非法姓名: {cleanResult.stats.bad_name} 条 | 公共邮箱: {cleanResult.stats.admin_removed} 条</div>
                            {cleanResult.files && Object.keys(cleanResult.files).length > 0 ? (
                              <div className="mt-2 space-y-0.5">
                                <div className="font-medium">已生成汇总文件：</div>
                                {Object.entries(cleanResult.files as Record<string, string>).map(([ext, url]) => (
                                  <a key={ext} href={api.getBackendUrl() + url} target="_blank" className="block text-primary hover:underline">
                                    📥 {cleanResult.summary_filename}.{ext}
                                  </a>
                                ))}
                              </div>
                            ) : null}
                            <div className="text-muted-foreground mt-1">来源: {cleanResult.source_file_count} 个文件</div>
                          </div>
                        ) : null}
                        <button className="mt-1 text-primary hover:underline" onClick={() => setCleanResult(null)}>关闭</button>
                      </div>
                    )}

                    {/* 来源文件：可滚动区域 */}
                    <div className="mt-4 flex-1 min-h-0 flex flex-col overflow-hidden rounded-lg border bg-background">
                      <div className="flex items-center justify-between border-b px-3 py-2 shrink-0">
                        <span className="text-sm font-medium">来源文件</span>
                        <div className="flex gap-1">
                          <input type="file" ref={fileInputRef} onChange={handleFileUpload} className="hidden" />
                          <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={() => fileInputRef.current?.click()}>
                            <Upload className="size-3 mr-1" />上传
                          </Button>
                          <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={handleClean} disabled={cleaning}>
                            {cleaning ? <Loader2 className="size-3 mr-1 animate-spin" /> : <Sparkles className="size-3 mr-1" />}
                            {cleaning ? "清洗中..." : "一键清洗"}
                          </Button>
                        </div>
                      </div>
                      <div className="flex-1 overflow-y-auto min-h-0">
                        <div className="divide-y">
                          {records.length === 0 ? (
                            <div className="px-3 py-6 text-center text-xs text-muted-foreground">暂无文件</div>
                          ) : records.map((r) => {
                            const BACKEND_URL = api.getBackendUrl();
                            const downloadUrl = r.url.startsWith("http") ? r.url : `${BACKEND_URL}${r.url}`;
                            const isRenaming = renamingFile?.task_id === r.task_id && renamingFile?.filename === r.filename;
                            const isActive = selectedRecord?.filename === r.filename && selectedRecord?.task_id === r.task_id;
                            return (
                              <div key={`${r.task_id}-${r.filename}`} className={`flex items-center justify-between gap-2 px-3 py-2 text-sm ${isActive ? "bg-primary/5" : ""}`}>
                                <div className="min-w-0 flex-1">
                                  {isRenaming ? (
                                    <div className="flex items-center gap-1">
                                      <Input
                                        value={renameValue}
                                        onChange={(e) => setRenameValue(e.target.value)}
                                        className="h-7 text-xs"
                                        autoFocus
                                        onKeyDown={(e) => {
                                          if (e.key === "Enter") handleFileRenameConfirm();
                                          if (e.key === "Escape") handleFileRenameCancel();
                                        }}
                                      />
                                      <Button size="sm" variant="ghost" className="h-6 w-6 p-0 shrink-0" onClick={handleFileRenameConfirm}><Check className="size-3" /></Button>
                                      <Button size="sm" variant="ghost" className="h-6 w-6 p-0 shrink-0" onClick={handleFileRenameCancel}><X className="size-3" /></Button>
                                    </div>
                                  ) : (
                                    <div className="truncate font-medium text-xs" title={r.filename}>{r.filename}</div>
                                  )}
                                  <div className="text-[10px] text-muted-foreground mt-0.5">{r.updated_at} · {r.row_count} 行 · {r.valid_email_count} 邮箱</div>
                                </div>
                                <div className="flex shrink-0 items-center gap-0.5">
                                  {r.previewable ? (
                                    <Button
                                      size="sm"
                                      className="h-7 px-2 text-xs"
                                      variant={isActive ? "default" : "outline"}
                                      onClick={() => {
                                        setSelectedRecord(r);
                                        setTableQuery(""); setTableDept(""); setValidOnly(false); setPage(1);
                                      }}
                                    >
                                      预览
                                    </Button>
                                  ) : null}
                                  <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => handleFileRenameStart(r.task_id, r.filename)} title="重命名"><Pencil className="size-3" /></Button>
                                  <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive" onClick={() => handleFileDelete(r.task_id, r.filename)} title="删除"><Trash2 className="size-3" /></Button>
                                  <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => window.open(downloadUrl, "_blank")} title="下载"><Download className="size-3.5" /></Button>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  </>
                ) : null}
              </div>

              {/* ── 拖拽手柄 2 ── */}
              <div
                className="relative w-1.5 shrink-0 cursor-col-resize bg-transparent hover:bg-primary/10 active:bg-primary/20 transition-colors before:absolute before:inset-y-0 before:left-1/2 before:w-px before:-translate-x-1/2 before:bg-border"
                onMouseDown={() => setDragging("files")}
              />

              {/* 右子列 2：表格预览 + CRUD */}
              <div className="flex-1 min-w-0 p-4 flex flex-col h-full overflow-hidden">
                <div className="mb-3 flex items-center justify-between shrink-0">
                  <div>
                    <div className="text-sm font-medium">表格预览</div>
                    <div className="text-xs text-muted-foreground">共 {table.total} 行</div>
                  </div>
                  {selectedRecord && displayColumns.length > 0 && (
                    <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={handleAddRowStart}>
                      <Plus className="size-3 mr-1" />添加行
                    </Button>
                  )}
                </div>

                {selectedRecord ? (
                  <div className="flex flex-col flex-1 min-h-0 min-w-0">
                    {/* 控制栏 */}
                    <div className="mb-3 space-y-2 rounded-lg border bg-muted/30 p-2.5 shrink-0">
                      <Input value={tableQuery} onChange={(e) => handleQueryChange(e.target.value)} placeholder="搜索姓名/邮箱" className="h-8 text-xs bg-background" />
                      <div className="flex items-center justify-between gap-2">
                        <select className="h-8 flex-1 min-w-0 rounded-md border bg-background px-2 text-xs" value={tableDept} onChange={(e) => handleDeptChange(e.target.value)}>
                          <option value="">全部院系</option>
                          {availableDepts.map((d) => <option key={d} value={d}>{d}</option>)}
                        </select>
                        <label className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground cursor-pointer select-none">
                          <input type="checkbox" checked={validOnly} onChange={(e) => handleValidOnlyChange(e.target.checked)} className="rounded border-gray-300 text-primary focus:ring-primary size-3.5" />
                          <span>仅看有效邮箱</span>
                        </label>
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
                            {displayColumns.map((col) => (
                              <th key={col} className="px-3 py-2 font-medium bg-muted text-muted-foreground whitespace-nowrap">{col}</th>
                            ))}
                            <th className="px-3 py-2 font-medium bg-muted text-muted-foreground w-16">操作</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y">
                          {/* 新增行输入行 */}
                          {addingRow && (
                            <tr className="bg-primary/5">
                              {displayColumns.map((col) => (
                                <td key={col} className="px-1 py-1">
                                  <Input
                                    value={newRowValues[col] || ""}
                                    onChange={(e) => setNewRowValues(v => ({ ...v, [col]: e.target.value }))}
                                    className="h-7 text-xs"
                                    placeholder={col}
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
                          {/* 数据行 */}
                          {table.rows.map((row, idx) => {
                            const rowIdx = parseInt(row._index || "0", 10);
                            const isEditing = editingRowIndex === rowIdx;
                            return (
                              <tr key={`${rowIdx}-${idx}`} className="hover:bg-muted/30">
                                {displayColumns.map((col) => (
                                  <td key={col} className="px-3 py-2 align-top text-foreground max-w-[200px] overflow-hidden text-ellipsis">
                                    {isEditing ? (
                                      <Input
                                        value={editValues[col] || ""}
                                        onChange={(e) => setEditValues(v => ({ ...v, [col]: e.target.value }))}
                                        className="h-7 text-xs"
                                      />
                                    ) : (
                                      row[col] || ""
                                    )}
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
                      <Button size="sm" variant="outline" className="h-7 px-2" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</Button>
                      <span className="text-muted-foreground">第 {page} 页 / 共 {Math.ceil(table.total / pageSize) || 1} 页</span>
                      <Button size="sm" variant="outline" className="h-7 px-2" disabled={page >= Math.ceil(table.total / pageSize)} onClick={() => setPage(p => p + 1)}>下一页</Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-1 items-center justify-center text-xs text-muted-foreground border border-dashed rounded-lg">
                    请选择文件查看数据预览
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
