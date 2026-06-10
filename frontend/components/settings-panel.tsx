"use client";

import { useState, useEffect } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { useUIStore } from "@/stores/ui-store";
import { useTheme } from "next-themes";
import {
  Settings,
  Palette,
  Server,
  Download,
  Keyboard,
  Moon,
  Sun,
  Monitor,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Copy,
  Check,
  ExternalLink,
} from "lucide-react";
import { api } from "@/services/api";

const shortcuts = [
  { key: "Enter", label: "发送消息" },
  { key: "Shift + Enter", label: "换行" },
  { key: "Ctrl + Enter", label: "发送消息（备选）" },
  { key: "Ctrl + K", label: "聚焦搜索栏" },
  { key: "Ctrl + N", label: "新建任务" },
  { key: "Escape", label: "关闭侧边栏/弹窗" },
];

type SettingsTab = "api" | "env" | "export" | "shortcuts";

const tabs: { id: SettingsTab; label: string; icon: React.ReactNode }[] = [
  { id: "api", label: "账户与 API", icon: <Server className="size-4" /> },
  { id: "env", label: "环境诊断", icon: <ShieldCheck className="size-4" /> },
  { id: "export", label: "导出偏好", icon: <Download className="size-4" /> },
  { id: "shortcuts", label: "快捷键", icon: <Keyboard className="size-4" /> },
];

export function SettingsPanel() {
  const settingsOpen = useUIStore((s) => s.settingsOpen);
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen);
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [activeTab, setActiveTab] = useState<SettingsTab>("api");

  // Config State
  const [serviceMode, setServiceMode] = useState<"cloud" | "custom">("custom");
  const [serviceToken, setServiceToken] = useState("");
  const [deepseekApiKey, setDeepseekApiKey] = useState("");
  const [originalDeepseekKey, setOriginalDeepseekKey] = useState("");  // 记录原始值（脱敏后）
  const [keyModified, setKeyModified] = useState(false);               // 用户是否改过key
  const [sessionTokens, setSessionTokens] = useState({ prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 });
  const [loading, setLoading] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "success" | "error">("idle");
  const [diagnostics, setDiagnostics] = useState<{
    node: boolean;
    claude_code: boolean;
    hermes: boolean;
    playwright: boolean;
    python: string;
  } | null>(null);

  const [copiedText, setCopiedText] = useState<string | null>(null);
  const [refreshingDiagnostics, setRefreshingDiagnostics] = useState(false);
  const [installStatus, setInstallStatus] = useState<{
    node: string;
    claude_code: string;
    hermes: string;
    playwright: string;
    is_running: boolean;
    current_action: string;
    logs: string[];
  } | null>(null);

  const [balanceYuan, setBalanceYuan] = useState<number>(5.00);
  const [rechargeOrder, setRechargeOrder] = useState<{
    order_id: string;
    amount: number;
    qr_url: string;
  } | null>(null);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedText(text);
    setTimeout(() => setCopiedText(null), 2000);
  };

  const handleRefreshDiagnostics = async () => {
    setRefreshingDiagnostics(true);
    try {
      const res = await fetch(`${api.getBackendUrl()}/api/diagnostics`);
      const data = await res.json();
      setDiagnostics(data);
    } catch (err) {
      console.error("Failed to refresh diagnostics:", err);
    } finally {
      setRefreshingDiagnostics(false);
    }
  };

  // Poll install status and balance when settings open
  useEffect(() => {
    let timer: NodeJS.Timeout | null = null;
    
    const fetchStatusAndBalance = async () => {
      try {
        const res = await fetch(`${api.getBackendUrl()}/api/diagnostics/install-status`);
        if (res.ok) {
          const data = await res.json();
          setInstallStatus(data);
          
          if (!data.is_running && timer) {
            // Refetch static diagnostics once installer completes
            fetch(`${api.getBackendUrl()}/api/diagnostics`)
              .then((r) => r.json())
              .then((d) => setDiagnostics(d))
              .catch((err) => console.error(err));
          }
        }

        // Fetch balance
        const balRes = await fetch(`${api.getBackendUrl()}/api/billing/balance`);
        if (balRes.ok) {
          const balData = await balRes.json();
          setBalanceYuan(balData.balance_yuan);
          setServiceToken(balData.service_token);
        }
      } catch (err) {
        console.error("Failed to fetch status/balance:", err);
      }
    };

    if (settingsOpen) {
      fetchStatusAndBalance();
      timer = setInterval(fetchStatusAndBalance, 1500);
    }

    return () => {
      if (timer) clearInterval(timer);
    };
  }, [settingsOpen]);

  const handleInitiateRecharge = async (amount: number) => {
    try {
      const res = await fetch(`${api.getBackendUrl()}/api/billing/recharge/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount, method: "wechat" })
      });
      if (res.ok) {
        const data = await res.json();
        setRechargeOrder({
          order_id: data.order_id,
          amount: data.amount,
          qr_url: data.qr_url
        });
      }
    } catch (err) {
      console.error("Failed to initiate recharge:", err);
    }
  };

  const handleConfirmPaymentMock = async () => {
    if (!rechargeOrder) return;
    try {
      const res = await fetch(`${api.getBackendUrl()}/api/billing/recharge/mock-confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ order_id: rechargeOrder.order_id })
      });
      if (res.ok) {
        const data = await res.json();
        setBalanceYuan(data.balance_yuan);
        setRechargeOrder(null);
      }
    } catch (err) {
      console.error("Failed to confirm mock recharge:", err);
    }
  };

  const handleStartAutoInstall = async () => {
    try {
      await fetch(`${api.getBackendUrl()}/api/diagnostics/install`, { method: "POST" });
      const res = await fetch(`${api.getBackendUrl()}/api/diagnostics/install-status`);
      if (res.ok) {
        const data = await res.json();
        setInstallStatus(data);
      }
    } catch (err) {
      console.error("Failed to trigger installation:", err);
    }
  };

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (settingsOpen) {
      setLoading(true);
      
      // 1. 获取基础配置
      fetch(`${api.getBackendUrl()}/api/config`)
        .then((res) => res.json())
        .then((data) => {
          setServiceMode(data.service_mode || "custom");
          setServiceToken(data.service_token || "");
          const loadedKey = data.deepseek_api_key || "";
          setDeepseekApiKey(loadedKey);
          setOriginalDeepseekKey(loadedKey);
          setKeyModified(false);
          if (data.session_tokens) {
            setSessionTokens(data.session_tokens);
          }
          setLoading(false);
        })
        .catch((err) => {
          console.error("Failed to load config:", err);
          setLoading(false);
        });

      // 2. 获取环境诊断状态
      fetch(`${api.getBackendUrl()}/api/diagnostics`)
        .then((res) => res.json())
        .then((data) => setDiagnostics(data))
        .catch((err) => console.error("Failed to load diagnostics:", err));
    }
  }, [settingsOpen]);

  const handleSaveConfig = async () => {
    setSaveStatus("saving");
    try {
      const body: Record<string, unknown> = {
        service_mode: serviceMode,
        service_token: serviceToken,
      };
      // 只在用户实际修改过key时才发送，避免把脱敏值发回后端
      if (keyModified) {
        body.deepseek_api_key = deepseekApiKey;
      }
      const res = await fetch(`${api.getBackendUrl()}/api/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setSaveStatus("success");
        setTimeout(() => setSaveStatus("idle"), 2000);
      } else {
        setSaveStatus("error");
      }
    } catch (err) {
      setSaveStatus("error");
    }
  };

  if (!mounted) return null;

  return (
    <Sheet open={settingsOpen} onOpenChange={setSettingsOpen}>
      <SheetContent side="right" className="w-[380px] sm:max-w-[420px] p-0 flex flex-col">
        <SheetHeader className="px-5 py-4 border-b border-border/30">
          <SheetTitle className="flex items-center gap-2">
            <Settings className="size-4 text-primary" />
            设置
          </SheetTitle>
          <SheetDescription>
            管理应用外观、连接和偏好
          </SheetDescription>
        </SheetHeader>

        {/* Tab navigation */}
        <div className="flex gap-1 px-4 pt-3 pb-1 border-b border-border/20">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                activeTab === tab.id
                  ? "bg-primary/15 text-primary"
                  : "text-muted-foreground/60 hover:text-muted-foreground hover:bg-muted/30"
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        <ScrollArea className="flex-1 px-5 py-4">
          {activeTab === "api" && (
            <div className="space-y-4">
              <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
                <Server className="size-4 text-primary" />
                服务与 API 配置
              </h3>

              {loading ? (
                <div className="text-xs text-muted-foreground animate-pulse py-4 text-center">正在加载配置...</div>
              ) : (
                <div className="space-y-4">
                  {/* Mode select */}
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-muted-foreground">服务模式</label>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        onClick={() => setServiceMode("cloud")}
                        className={`rounded-lg border p-2 text-xs font-medium transition-all ${
                          serviceMode === "cloud"
                            ? "border-primary bg-primary/10 text-primary"
                            : "border-border/40 hover:bg-muted/20"
                        }`}
                      >
                        官方云端算力
                      </button>
                      <button
                        onClick={() => setServiceMode("custom")}
                        className={`rounded-lg border p-2 text-xs font-medium transition-all ${
                          serviceMode === "custom"
                            ? "border-primary bg-primary/10 text-primary"
                            : "border-border/40 hover:bg-muted/20"
                        }`}
                      >
                        个人 API Key
                      </button>
                    </div>
                  </div>

                  {/* Mode dependent inputs */}
                  {serviceMode === "cloud" ? (
                    <div className="space-y-3">
                      <div className="space-y-1">
                        <label className="text-xs font-medium text-muted-foreground">官方服务账号 ID (Service Token)</label>
                        <div className="flex items-center gap-1 bg-muted/40 rounded-lg px-3 py-2 border border-border/20 font-mono text-xs text-foreground">
                          <span className="flex-1 select-all">{serviceToken || "生成中..."}</span>
                          <button 
                            onClick={() => handleCopy(serviceToken)} 
                            className="p-0.5 text-muted-foreground/50 hover:text-foreground transition-colors"
                            type="button"
                          >
                            {copiedText === serviceToken ? <Check className="size-3.5 text-emerald-500" /> : <Copy className="size-3.5" />}
                          </button>
                        </div>
                      </div>

                      <div className="rounded-xl border border-border/30 bg-muted/20 p-3.5 space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-muted-foreground">账户可用余额:</span>
                          <span className="text-base font-bold text-primary font-mono">￥{balanceYuan.toFixed(2)} 元</span>
                        </div>
                        
                        {/* Recharge quick options */}
                        <div className="space-y-2">
                          <p className="text-[10px] text-muted-foreground/60">微信/支付宝在线扫码充值 (30倍 Token 费率):</p>
                          <div className="grid grid-cols-3 gap-2">
                            {[10, 30, 50].map((amt) => (
                              <button
                                key={amt}
                                onClick={() => handleInitiateRecharge(amt)}
                                className="rounded-lg border border-border/30 hover:border-primary/40 hover:bg-primary/5 py-1.5 text-xs font-bold font-mono transition-all text-center text-foreground bg-background hover:text-primary"
                                type="button"
                              >
                                充 {amt}元
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>

                      {rechargeOrder && (
                        <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 space-y-3">
                          <div className="flex items-center justify-between border-b border-primary/10 pb-2">
                            <span className="text-xs font-semibold text-primary flex items-center gap-1.5">
                              <RefreshCw className="size-3.5 animate-spin" />
                              正在等待扫码支付...
                            </span>
                            <span className="text-xs font-bold text-foreground font-mono">￥{rechargeOrder.amount} 元</span>
                          </div>
                          
                          <div className="flex flex-col items-center py-2 space-y-2">
                            <div className="bg-white p-2 rounded-lg border border-border/30 shadow-sm">
                              <img src={rechargeOrder.qr_url} alt="支付二维码" className="size-36" />
                            </div>
                            <p className="text-[10px] text-muted-foreground/60 text-center">
                              请使用 微信/支付宝 扫描上方二维码付款
                            </p>
                          </div>
                          
                          <div className="flex gap-2">
                            <button
                              onClick={handleConfirmPaymentMock}
                              className="flex-1 text-xs bg-primary hover:bg-primary/95 text-white font-medium py-1.5 rounded-lg transition-colors text-center"
                              type="button"
                            >
                              模拟支付成功 (沙箱测试)
                            </button>
                            <button
                              onClick={() => setRechargeOrder(null)}
                              className="text-xs bg-background border border-border/40 hover:bg-muted/10 text-foreground px-3 py-1.5 rounded-lg transition-colors text-center"
                              type="button"
                            >
                              取消
                            </button>
                          </div>
                        </div>
                      )}

                      <p className="text-[10px] text-muted-foreground/40 leading-relaxed">
                        官方云服务由 南京微特喜网络科技有限公司 统一提供安全保障。Token 消耗按 30 倍官方基准价格实时自动核减。账户注册即送 5.00 元体验金。
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <div className="space-y-1">
                        <label className="text-xs font-medium text-muted-foreground">DeepSeek API Key</label>
                        <input
                          type="password"
                          value={deepseekApiKey}
                          onChange={(e) => {
                            setDeepseekApiKey(e.target.value);
                            setKeyModified(true);
                          }}
                          placeholder={deepseekApiKey ? "••••••••••••••••" : "输入以 sk- 开头的密钥"}
                          className="w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-xs font-mono placeholder:text-muted-foreground/40 focus:border-primary focus:outline-none"
                        />
                      </div>
                      <p className="text-[10px] text-muted-foreground/40">使用您的个人 DeepSeek API Key 运行，您需要自己向大模型服务商付费。</p>
                    </div>
                  )}

                  {/* Session stats */}
                  <div className="rounded-xl border border-border/30 bg-muted/10 p-3 space-y-1.5">
                    <p className="text-xs font-medium text-foreground">本次运行累计消耗 (Session Tokens)</p>
                    <div className="grid grid-cols-3 gap-1 text-[10px] font-mono text-muted-foreground">
                      <div className="flex flex-col rounded bg-background/50 p-1.5 border border-border/10">
                        <span>输入 (Prompt)</span>
                        <span className="text-foreground font-bold mt-0.5">{sessionTokens.prompt_tokens.toLocaleString()}</span>
                      </div>
                      <div className="flex flex-col rounded bg-background/50 p-1.5 border border-border/10">
                        <span>输出 (Output)</span>
                        <span className="text-foreground font-bold mt-0.5">{sessionTokens.completion_tokens.toLocaleString()}</span>
                      </div>
                      <div className="flex flex-col rounded bg-background/50 p-1.5 border border-border/10">
                        <span>总消耗</span>
                        <span className="text-primary font-bold mt-0.5">{sessionTokens.total_tokens.toLocaleString()}</span>
                      </div>
                    </div>
                  </div>

                  {/* Save button */}
                  <Button
                    onClick={handleSaveConfig}
                    disabled={saveStatus === "saving"}
                    size="sm"
                    className="w-full text-xs"
                  >
                    {saveStatus === "saving" && "正在保存..."}
                    {saveStatus === "success" && "保存成功 ✓"}
                    {saveStatus === "error" && "保存失败 ✗"}
                    {saveStatus === "idle" && "应用并保存配置"}
                  </Button>
                </div>
              )}
            </div>
          )}

          {activeTab === "env" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
                  <ShieldCheck className="size-4 text-primary" />
                  环境诊断与依赖
                </h3>
                <button
                  onClick={handleRefreshDiagnostics}
                  disabled={refreshingDiagnostics || installStatus?.is_running}
                  className="p-1 rounded-md hover:bg-muted/40 transition-colors text-muted-foreground hover:text-foreground disabled:opacity-50"
                  title="重新检测"
                >
                  <RefreshCw className={`size-3.5 ${(refreshingDiagnostics || installStatus?.is_running) ? 'animate-spin' : ''}`} />
                </button>
              </div>

              <p className="text-xs text-muted-foreground/60 leading-relaxed">
                本程序基于 Agent 双轨机制运行：优先使用 Claude Code CLI 进行自主交互；若检测未安装，系统将尝试后台自动部署，或降级至内置 Playwright 爬虫。
              </p>

              {/* Automatic Installer Panel */}
              {installStatus?.is_running ? (
                <div className="rounded-xl border border-primary/20 bg-primary/5 p-3.5 space-y-3 animate-pulse">
                  <div className="flex items-center gap-2.5">
                    <RefreshCw className="size-4 text-primary animate-spin" />
                    <div className="space-y-0.5">
                      <p className="text-xs font-semibold text-primary">正在自动安装配置依赖中...</p>
                      <p className="text-[10px] text-muted-foreground">{installStatus.current_action}</p>
                    </div>
                  </div>
                  <div className="rounded-lg bg-zinc-950 p-2.5 font-mono text-[9px] text-zinc-300 border border-zinc-800">
                    <p className="text-[10px] text-zinc-500 border-b border-zinc-800 pb-1 mb-1 flex justify-between">
                      <span>实时安装日志</span>
                      <span className="text-[9px] bg-zinc-800 px-1 rounded text-zinc-400">后台线程</span>
                    </p>
                    <div className="max-h-[120px] overflow-y-auto space-y-0.5 scrollbar-thin scrollbar-thumb-zinc-800">
                      {installStatus.logs.length > 0 ? (
                        installStatus.logs.map((log, idx) => (
                          <div key={idx} className="whitespace-pre-wrap leading-relaxed">{log}</div>
                        ))
                      ) : (
                        <div className="text-zinc-600">正在等待输出...</div>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                diagnostics && (!diagnostics.node || !diagnostics.claude_code || !diagnostics.playwright) && (
                  <Button 
                    onClick={handleStartAutoInstall}
                    size="sm" 
                    className="w-full text-xs flex items-center justify-center gap-1.5 bg-primary hover:bg-primary/90 text-white font-medium shadow-sm transition-all"
                  >
                    <ShieldCheck className="size-3.5" />
                    一键自动配置与安装缺失环境
                  </Button>
                )
              )}

              <div className="space-y-3">
                {/* Node.js Check */}
                <div className="rounded-xl border border-border/30 bg-muted/10 p-3 space-y-2">
                  <div className="flex items-start justify-between">
                    <div className="space-y-0.5">
                      <p className="text-xs font-semibold text-foreground">Node.js 运行时环境</p>
                      <p className="text-[10px] text-muted-foreground/60">运行 Claude Code CLI 的核心前置依赖。</p>
                    </div>
                    {diagnostics?.node ? (
                      <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-500 bg-emerald-500/10 px-2 py-0.5 rounded-full">
                        <CheckCircle2 className="size-3" />
                        已就绪
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-[10px] font-medium text-amber-500 bg-amber-500/10 px-2 py-0.5 rounded-full">
                        <AlertTriangle className="size-3" />
                        未检测到
                      </span>
                    )}
                  </div>
                  {!diagnostics?.node && !installStatus?.is_running && (
                    <div className="text-[10px] bg-background/50 border border-border/10 rounded-lg p-2 space-y-1.5">
                      <p className="text-muted-foreground/80">手动安装指引：建议通过 WinGet 安装或访问官网下载</p>
                      <div className="flex items-center gap-1 bg-muted/30 rounded px-1.5 py-1 font-mono text-muted-foreground">
                        <span className="flex-1 select-all">winget install OpenJS.NodeJS</span>
                        <button 
                          onClick={() => handleCopy("winget install OpenJS.NodeJS")}
                          className="text-muted-foreground/40 hover:text-foreground transition-colors p-0.5"
                        >
                          {copiedText === "winget install OpenJS.NodeJS" ? <Check className="size-3 text-emerald-500" /> : <Copy className="size-3" />}
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* Claude Code Check */}
                <div className="rounded-xl border border-border/30 bg-muted/10 p-3 space-y-2">
                  <div className="flex items-start justify-between">
                    <div className="space-y-0.5">
                      <p className="text-xs font-semibold text-foreground">Claude Code CLI</p>
                      <p className="text-[10px] text-muted-foreground/60">Anthropic 官方 Agent，具备网页爬取与自主执行能力。</p>
                    </div>
                    {diagnostics?.claude_code ? (
                      <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-500 bg-emerald-500/10 px-2 py-0.5 rounded-full">
                        <CheckCircle2 className="size-3" />
                        已就绪
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-[10px] font-medium text-amber-500 bg-amber-500/10 px-2 py-0.5 rounded-full">
                        <AlertTriangle className="size-3" />
                        未安装
                      </span>
                    )}
                  </div>
                  {!diagnostics?.claude_code && !installStatus?.is_running && (
                    <div className="text-[10px] bg-background/50 border border-border/10 rounded-lg p-2 space-y-1.5">
                      <p className="text-muted-foreground/80">手动安装指引：确保 Node.js 已就绪，以管理员身份执行</p>
                      <div className="flex items-center gap-1 bg-muted/30 rounded px-1.5 py-1 font-mono text-muted-foreground">
                        <span className="flex-1 select-all">npm install -g @anthropic-ai/claude-code</span>
                        <button 
                          onClick={() => handleCopy("npm install -g @anthropic-ai/claude-code")}
                          className="text-muted-foreground/40 hover:text-foreground transition-colors p-0.5"
                        >
                          {copiedText === "npm install -g @anthropic-ai/claude-code" ? <Check className="size-3 text-emerald-500" /> : <Copy className="size-3" />}
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* Hermes Check */}
                <div className="rounded-xl border border-border/30 bg-muted/10 p-3 space-y-2">
                  <div className="flex items-start justify-between">
                    <div className="space-y-0.5">
                      <p className="text-xs font-semibold text-foreground">Hermes Orchestrator</p>
                      <p className="text-[10px] text-muted-foreground/60">可选的智能编排引擎，用于生成简报与沉淀知识。</p>
                    </div>
                    {diagnostics?.hermes ? (
                      <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-500 bg-emerald-500/10 px-2 py-0.5 rounded-full">
                        <CheckCircle2 className="size-3" />
                        已就绪
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-[10px] font-medium text-muted-foreground/60 bg-muted/20 px-2 py-0.5 rounded-full">
                        未检测到
                      </span>
                    )}
                  </div>
                  {!diagnostics?.hermes && !installStatus?.is_running && (
                    <div className="text-[10px] bg-background/50 border border-border/10 rounded-lg p-2 space-y-1.5">
                      <p className="text-muted-foreground/80">手动安装指引：可选编排包，可在 Python 虚拟环境中安装</p>
                      <div className="flex items-center gap-1 bg-muted/30 rounded px-1.5 py-1 font-mono text-muted-foreground">
                        <span className="flex-1 select-all">pip install hermes-agent</span>
                        <button 
                          onClick={() => handleCopy("pip install hermes-agent")}
                          className="text-muted-foreground/40 hover:text-foreground transition-colors p-0.5"
                        >
                          {copiedText === "pip install hermes-agent" ? <Check className="size-3 text-emerald-500" /> : <Copy className="size-3" />}
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* Playwright Check */}
                <div className="rounded-xl border border-border/30 bg-muted/10 p-3 space-y-2">
                  <div className="flex items-start justify-between">
                    <div className="space-y-0.5">
                      <p className="text-xs font-semibold text-foreground">Playwright Chromium 浏览器</p>
                      <p className="text-[10px] text-muted-foreground/60">内置的回退浏览器自动化引擎。</p>
                    </div>
                    {diagnostics?.playwright ? (
                      <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-500 bg-emerald-500/10 px-2 py-0.5 rounded-full">
                        <CheckCircle2 className="size-3" />
                        已就绪
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-[10px] font-medium text-amber-500 bg-amber-500/10 px-2 py-0.5 rounded-full">
                        <AlertTriangle className="size-3" />
                        未就绪
                      </span>
                    )}
                  </div>
                  {!diagnostics?.playwright && !installStatus?.is_running && (
                    <div className="text-[10px] bg-background/50 border border-border/10 rounded-lg p-2 space-y-1.5">
                      <p className="text-muted-foreground/80">手动安装指引：请在命令行中运行安装浏览器内核</p>
                      <div className="flex items-center gap-1 bg-muted/30 rounded px-1.5 py-1 font-mono text-muted-foreground">
                        <span className="flex-1 select-all">playwright install chromium</span>
                        <button 
                          onClick={() => handleCopy("playwright install chromium")}
                          className="text-muted-foreground/40 hover:text-foreground transition-colors p-0.5"
                        >
                          {copiedText === "playwright install chromium" ? <Check className="size-3 text-emerald-500" /> : <Copy className="size-3" />}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === "export" && (
            <div className="space-y-4">
              <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
                <Download className="size-4 text-primary" />
                导出偏好
              </h3>
              <p className="text-xs text-muted-foreground/60">
                导出格式和下载路径由后端配置决定。支持 CSV、XLSX、MD 等格式。
              </p>
              <div className="rounded-xl border border-border/30 bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">默认导出格式</p>
                <div className="mt-2 flex gap-2">
                  {["CSV", "XLSX", "MD"].map((fmt) => (
                    <span
                      key={fmt}
                      className="rounded-lg bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary"
                    >
                      {fmt}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeTab === "shortcuts" && (
            <div className="space-y-4">
              <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
                <Keyboard className="size-4 text-primary" />
                快捷键列表
              </h3>
              <div className="space-y-1">
                {shortcuts.map((s) => (
                  <div
                    key={s.key}
                    className="flex items-center justify-between rounded-lg px-3 py-2 text-sm hover:bg-muted/20 transition-colors"
                  >
                    <span className="text-muted-foreground">{s.label}</span>
                    <kbd className="rounded-md border border-border/40 bg-muted/40 px-2 py-0.5 text-[11px] font-mono text-foreground/70 shadow-sm">
                      {s.key}
                    </kbd>
                  </div>
                ))}
              </div>
            </div>
          )}
        </ScrollArea>

        <div className="px-5 py-3 border-t border-border/30 bg-muted/10 text-[10px] text-muted-foreground/40 text-center">
          UniEmail Agent v0.1.0
        </div>
      </SheetContent>
    </Sheet>
  );
}
