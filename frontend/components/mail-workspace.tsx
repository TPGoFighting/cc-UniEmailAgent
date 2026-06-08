"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/services/api";
import { useUIStore } from "@/stores/ui-store";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";

export function MailWorkspace() {
  const open = useUIStore((s) => s.mailOpen);
  const setOpen = useUIStore((s) => s.setMailOpen);
  const [rows, setRows] = useState<Record<string, string>[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [selectedRows, setSelectedRows] = useState<number[]>([]);
  const [subject, setSubject] = useState("邀请沟通：{{学校}}-{{姓名}}");
  const [body, setBody] = useState("您好 {{姓名}}，\n\n我们想 and 您就 {{学校}} {{学院}} 的工作做进一步沟通。");
  const [smtp, setSmtp] = useState({ user: "", password: "", host: "", port: 465, secure: true, fromName: "" });
  const [smtpSessionId, setSmtpSessionId] = useState("");
  const [preview, setPreview] = useState<any>(null);
  const [status, setStatus] = useState("");

  // 新增数据源过滤与联动状态
  const [schools, setSchools] = useState<any[]>([]);
  const [selectedSchoolName, setSelectedSchoolName] = useState<string>("");
  const [records, setRecords] = useState<any[]>([]);
  const [selectedRecord, setSelectedRecord] = useState<any | null>(null);
  const [departments, setDepartments] = useState<string[]>([]);
  const [selectedDept, setSelectedDept] = useState<string>("");
  const [tableQuery, setTableQuery] = useState<string>("");
  const [validOnly, setValidOnly] = useState<boolean>(false);

  const targetRows = useMemo(() => rows.filter((_, idx) => selectedRows.includes(idx)), [rows, selectedRows]);

  // 1. 初始化拉取有数据的高校
  useEffect(() => {
    if (!open) return;
    api.getUniversities({ tier: "全部" }).then((data: any) => {
      const allUnis = data.groups.flatMap((g: any) => g.cities.flatMap((c: any) => c.universities));
      const activeUnis = allUnis.filter((u: any) => u.records && u.records.table_count > 0);
      setSchools(activeUnis);
      if (activeUnis.length > 0 && !selectedSchoolName) {
        setSelectedSchoolName(activeUnis[0].name);
      }
    }).catch(() => {});
  }, [open]);

  // 2. 高校变更时拉取对应的文件列表
  useEffect(() => {
    if (!selectedSchoolName) {
      setRecords([]);
      setSelectedRecord(null);
      return;
    }
    api.getUniversityRecords(selectedSchoolName).then((data: any) => {
      const recs = (data.records || []).filter((r: any) => r.previewable);
      setRecords(recs);
      if (recs.length > 0) {
        setSelectedRecord(recs[0]);
      } else {
        setSelectedRecord(null);
      }
      setSelectedDept("");
      setTableQuery("");
      setValidOnly(false);
    }).catch(() => {});
  }, [selectedSchoolName]);

  // 3. 文件/过滤条件发生变更时重新拉取表格数据
  useEffect(() => {
    if (!selectedSchoolName || !selectedRecord) {
      setRows([]);
      setColumns([]);
      setSelectedRows([]);
      setDepartments([]);
      return;
    }
    api.getUniversityTable(selectedSchoolName, {
      task_id: selectedRecord.task_id,
      file: selectedRecord.filename,
      q: tableQuery,
      department: selectedDept,
      valid_only: validOnly,
      limit: 300, // 发送上限拉大到 300 条
    }).then((tbl) => {
      const r = (tbl.rows || []) as Record<string, string>[];
      setRows(r);
      setColumns(tbl.columns || []);
      setDepartments(tbl.departments || []);
      setSelectedRows(r.map((_, idx) => idx));
    }).catch(() => {});
  }, [selectedSchoolName, selectedRecord, selectedDept, tableQuery, validOnly]);

  const detect = async () => {
    const data: any = await api.detectSmtp(smtp.user);
    setSmtp((s) => ({ ...s, ...data.config }));
  };

  const verify = async () => {
    try {
      const data: any = await api.verifySmtp(smtp);
      setSmtpSessionId(data.smtpSessionId);
      setStatus("SMTP 验证通过");
    } catch (err: any) {
      setStatus(`SMTP 验证失败: ${err.message || "请检查配置"}`);
    }
  };

  const previewMail = async () => {
    if (targetRows.length === 0) {
      setStatus("请至少选中一个收件人进行预览");
      return;
    }
    try {
      const data = await api.previewMail({ rows: targetRows, subjectTemplate: subject, bodyTemplate: body, limit: 10 });
      setPreview(data);
      setStatus(`已生成 ${data.previews?.length || 0} 封预览`);
    } catch (err: any) {
      setStatus(`生成预览失败: ${err.message || "模板存在语法错误"}`);
    }
  };

  const send = async () => {
    if (targetRows.length === 0) {
      setStatus("没有勾选有效的发送对象");
      return;
    }

    let highVolumeConfirmed = false;
    if (targetRows.length > 50) {
      const confirmSend = window.confirm(`预计发送 ${targetRows.length} 封邮件，已超过大批量发送阈值 (50封)，是否确认继续发送？`);
      if (!confirmSend) {
        setStatus("用户取消了批量发送");
        return;
      }
      highVolumeConfirmed = true;
    }

    try {
      const data: any = await api.sendMail({
        rows: targetRows,
        subjectTemplate: subject,
        bodyTemplate: body,
        smtpSessionId,
        settings: { maxRows: targetRows.length, testMode: false },
        previewConfirmed: true,
        confirmed: true,
        highVolumeConfirmed,
      });
      setStatus(`发送任务已启动：${data.jobId}`);
    } catch (err: any) {
      setStatus(`发信任务启动失败: ${err.message || "连接服务器错误"}`);
    }
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent side="right" className="w-[min(1180px,96vw)] max-w-none sm:max-w-none data-[side=right]:sm:max-w-none gap-0 p-0 overflow-hidden">
        <div className="flex h-full flex-col overflow-hidden">
          <SheetHeader className="border-b px-5 py-4">
            <SheetTitle>邮件发送</SheetTitle>
            <SheetDescription>先选学校和教师，再验证 SMTP、预览内容，最后发送。</SheetDescription>
          </SheetHeader>
          <div className="grid flex-1 min-h-0 grid-cols-[1fr_420px] overflow-hidden">
            <div className="min-h-0 min-w-0 border-r p-4 flex flex-col h-full overflow-hidden">
              <div className="space-y-3 shrink-0">
                <div className="grid grid-cols-3 gap-3">
                  <div className="col-span-1">
                    <Input placeholder="SMTP 用户" value={smtp.user} onChange={(e) => setSmtp((s) => ({ ...s, user: e.target.value }))} onBlur={detect} />
                  </div>
                  <div className="col-span-1">
                    <Input type="password" placeholder="SMTP 授权码" value={smtp.password} onChange={(e) => setSmtp((s) => ({ ...s, password: e.target.value }))} />
                  </div>
                  <div className="col-span-1">
                    <Input placeholder="发件人名称" value={smtp.fromName} onChange={(e) => setSmtp((s) => ({ ...s, fromName: e.target.value }))} />
                  </div>
                  <div className="col-span-1">
                    <Input placeholder="SMTP Host" value={smtp.host} onChange={(e) => setSmtp((s) => ({ ...s, host: e.target.value }))} />
                  </div>
                  <div className="col-span-1">
                    <Input type="number" placeholder="端口 (默认465)" value={smtp.port || ""} onChange={(e) => setSmtp((s) => ({ ...s, port: parseInt(e.target.value) || 0 }))} />
                  </div>
                  <div className="col-span-1 flex items-center pl-2 h-9">
                    <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer select-none">
                      <input type="checkbox" checked={smtp.secure} onChange={(e) => setSmtp((s) => ({ ...s, secure: e.target.checked }))} className="rounded border-gray-300 text-primary focus:ring-primary size-3.5" />
                      <span>使用 SSL/TLS</span>
                    </label>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button onClick={verify}>验证 SMTP</Button>
                  <Button variant="outline" onClick={previewMail}>预览邮件</Button>
                  <Button onClick={send} disabled={!smtpSessionId}>发送</Button>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Input placeholder="主题模板" value={subject} onChange={(e) => setSubject(e.target.value)} />
                  <Input placeholder="正文模板" value={body} onChange={(e) => setBody(e.target.value)} />
                </div>
                <div className="rounded-lg border px-3 py-2 text-sm text-muted-foreground">{status || "等待验证和预览"}</div>
              </div>
              <div className="mt-4 rounded-lg border flex-1 min-h-0 flex flex-col bg-background">
                <div className="border-b px-3 py-2 text-sm font-medium flex items-center justify-between">
                  <span>收件人选择</span>
                  <span className="text-xs text-muted-foreground">已选 {selectedRows.length} / {rows.length} 人</span>
                </div>

                {/* 三级级联联动选择器面板 */}
                <div className="p-3 border-b bg-muted/20 space-y-2 text-xs">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <label className="font-medium text-muted-foreground">选择高校</label>
                      <select className="h-8 w-full rounded-md border bg-background px-2" value={selectedSchoolName} onChange={(e) => setSelectedSchoolName(e.target.value)}>
                        <option value="">-- 选择有抓取结果的高校 --</option>
                        {schools.map((u) => (
                          <option key={u.name} value={u.name}>
                            {u.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label className="font-medium text-muted-foreground">抓取数据文件</label>
                      <select className="h-8 w-full rounded-md border bg-background px-2" value={selectedRecord ? `${selectedRecord.task_id}:${selectedRecord.filename}` : ""} onChange={(e) => {
                        const val = e.target.value;
                        if (!val) {
                          setSelectedRecord(null);
                        } else {
                          const [tid, fname] = val.split(":");
                          const rec = records.find(r => r.task_id === tid && r.filename === fname);
                          setSelectedRecord(rec || null);
                        }
                      }} disabled={!selectedSchoolName || records.length === 0}>
                        {records.map((r) => (
                          <option key={`${r.task_id}:${r.filename}`} value={`${r.task_id}:${r.filename}`}>
                            {r.filename} ({r.row_count} 行)
                          </option>
                        ))}
                        {records.length === 0 && <option value="">-- 无可用文件 --</option>}
                      </select>
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-2 items-center">
                    <div className="space-y-1 col-span-1">
                      <label className="font-medium text-muted-foreground">院系筛选</label>
                      <select className="h-8 w-full rounded-md border bg-background px-2" value={selectedDept} onChange={(e) => setSelectedDept(e.target.value)} disabled={!selectedSchoolName || !selectedRecord}>
                        <option value="">全部院系</option>
                        {departments.map((d) => <option key={d} value={d}>{d}</option>)}
                      </select>
                    </div>
                    <div className="space-y-1 col-span-1">
                      <label className="font-medium text-muted-foreground">搜索姓名/邮箱</label>
                      <Input value={tableQuery} onChange={(e) => setTableQuery(e.target.value)} placeholder="搜索..." className="h-8 text-xs bg-background" disabled={!selectedSchoolName || !selectedRecord} />
                    </div>
                    <div className="flex items-center col-span-1 pl-2 h-8 mt-5">
                      <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer select-none">
                        <input type="checkbox" checked={validOnly} onChange={(e) => setValidOnly(e.target.checked)} className="rounded border-gray-300 text-primary focus:ring-primary size-3.5" disabled={!selectedSchoolName || !selectedRecord} />
                        <span>仅限有效邮箱</span>
                      </label>
                    </div>
                  </div>
                </div>

                <div className="flex-1 overflow-auto rounded-lg border bg-background min-h-0 [&::-webkit-scrollbar]:h-2 [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-muted-foreground/25 hover:[&::-webkit-scrollbar-thumb]:bg-muted-foreground/40 [&::-webkit-scrollbar-track]:bg-transparent">
                  <table className="w-full min-w-max text-left text-xs table-auto">
                    <thead className="sticky top-0 bg-muted/95 backdrop-blur-sm z-10">
                      <tr className="border-b">
                        <th className="px-3 py-2 w-12 text-center bg-muted">
                          <input type="checkbox" checked={rows.length > 0 && selectedRows.length === rows.length} onChange={(e) => {
                            if (e.target.checked) {
                              setSelectedRows(rows.map((_, idx) => idx));
                            } else {
                              setSelectedRows([]);
                            }
                          }} disabled={rows.length === 0} />
                        </th>
                        {columns.map((c) => <th key={c} className="px-3 py-2 font-medium bg-muted text-muted-foreground">{c}</th>)}
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {rows.map((row, idx) => (
                        <tr key={idx} className="hover:bg-muted/30">
                          <td className="px-3 py-2 text-center">
                            <input type="checkbox" checked={selectedRows.includes(idx)} onChange={(e) => setSelectedRows((curr) => e.target.checked ? [...curr, idx] : curr.filter((n) => n !== idx))} />
                          </td>
                          {columns.map((c) => <td key={c} className="px-3 py-2 text-foreground">{row[c] || ""}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            <div className="min-h-0 p-4">
              <div className="mb-3 text-sm font-medium">预览</div>
              <ScrollArea className="h-[calc(100vh-220px)]">
                <div className="space-y-3">
                  {(preview?.previews || []).map((item: any, idx: number) => (
                    <div key={idx} className="rounded-lg border p-3 text-sm">
                      <div className="font-medium">{item.email}</div>
                      <div className="mt-1 text-muted-foreground">{item.subject}</div>
                      <div className="mt-2 whitespace-pre-wrap text-xs text-muted-foreground">{item.body}</div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
