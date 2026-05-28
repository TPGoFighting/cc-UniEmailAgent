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
  const [body, setBody] = useState("您好 {{姓名}}，\n\n我们想和您就 {{学校}} {{学院}} 的工作做进一步沟通。");
  const [smtp, setSmtp] = useState({ user: "", password: "", host: "", port: 465, secure: true, fromName: "" });
  const [smtpSessionId, setSmtpSessionId] = useState("");
  const [preview, setPreview] = useState<any>(null);
  const [status, setStatus] = useState("");

  const targetRows = useMemo(() => rows.filter((_, idx) => selectedRows.includes(idx)), [rows, selectedRows]);

  useEffect(() => {
    if (!open) return;
    api.getUniversities({ tier: "985" }).then(() => {}).catch(() => {});
  }, [open]);

  const loadSchoolTable = async (school: string, taskId?: string, file?: string) => {
    const tbl = await api.getUniversityTable(school, { task_id: taskId, file, limit: 200 });
    setRows((tbl.rows || []) as Record<string, string>[]);
    setColumns(tbl.columns || []);
    setSelectedRows((tbl.rows || []).map((_, idx) => idx));
  };

  const detect = async () => {
    const data: any = await api.detectSmtp(smtp.user);
    setSmtp((s) => ({ ...s, ...data.config }));
  };

  const verify = async () => {
    const data: any = await api.verifySmtp(smtp);
    setSmtpSessionId(data.smtpSessionId);
    setStatus("SMTP 验证通过");
  };

  const previewMail = async () => {
    const data = await api.previewMail({ rows: targetRows, subjectTemplate: subject, bodyTemplate: body, limit: 10 });
    setPreview(data);
    setStatus(`已生成 ${data.previews?.length || 0} 封预览`);
  };

  const send = async () => {
    const data: any = await api.sendMail({
      rows: targetRows,
      subjectTemplate: subject,
      bodyTemplate: body,
      smtpSessionId,
      settings: { maxRows: targetRows.length, testMode: false },
      previewConfirmed: true,
      confirmed: true,
      highVolumeConfirmed: targetRows.length <= 50,
    });
    setStatus(`发送任务已启动：${data.jobId}`);
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent side="right" className="w-[min(1180px,96vw)] max-w-none p-0">
        <div className="flex h-full flex-col">
          <SheetHeader className="border-b px-5 py-4">
            <SheetTitle>邮件发送</SheetTitle>
            <SheetDescription>先选学校和教师，再验证 SMTP、预览内容，最后发送。</SheetDescription>
          </SheetHeader>
          <div className="grid flex-1 min-h-0 grid-cols-[1fr_420px]">
            <div className="min-h-0 border-r p-4">
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <Input placeholder="SMTP 用户" value={smtp.user} onChange={(e) => setSmtp((s) => ({ ...s, user: e.target.value }))} onBlur={detect} />
                  <Input type="password" placeholder="SMTP 授权码" value={smtp.password} onChange={(e) => setSmtp((s) => ({ ...s, password: e.target.value }))} />
                  <Input placeholder="SMTP Host" value={smtp.host} onChange={(e) => setSmtp((s) => ({ ...s, host: e.target.value }))} />
                  <Input placeholder="发件人名称" value={smtp.fromName} onChange={(e) => setSmtp((s) => ({ ...s, fromName: e.target.value }))} />
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
              <div className="mt-4 rounded-lg border">
                <div className="border-b px-3 py-2 text-sm font-medium">收件人</div>
                <ScrollArea className="h-[calc(100vh-300px)]">
                  <table className="w-full text-left text-xs">
                    <thead className="sticky top-0 bg-background">
                      <tr>
                        <th className="border-b px-3 py-2">选中</th>
                        {columns.map((c) => <th key={c} className="border-b px-3 py-2">{c}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row, idx) => (
                        <tr key={idx} className="border-b">
                          <td className="px-3 py-2">
                            <input type="checkbox" checked={selectedRows.includes(idx)} onChange={(e) => setSelectedRows((curr) => e.target.checked ? [...curr, idx] : curr.filter((n) => n !== idx))} />
                          </td>
                          {columns.map((c) => <td key={c} className="px-3 py-2">{row[c] || ""}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </ScrollArea>
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
