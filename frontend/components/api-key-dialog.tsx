"use client";

import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Key, Check, AlertCircle, Eye, EyeOff, Loader2 } from "lucide-react";
import { api } from "@/services/api";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ApiKeyDialog({ open, onOpenChange }: Props) {
  const [apiKey, setApiKey] = useState("");
  const [maskedKey, setMaskedKey] = useState("");
  const [hasExistingKey, setHasExistingKey] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [sessionTokens, setSessionTokens] = useState<number | undefined>();

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError("");
    setSuccess(false);
    api.getConfig()
      .then((cfg) => {
        setHasExistingKey(cfg.has_deepseek_key);
        setMaskedKey(cfg.has_deepseek_key ? cfg.deepseek_api_key : "");
        setApiKey(cfg.has_deepseek_key ? cfg.deepseek_api_key : "");
        setSessionTokens(cfg.session_tokens);
      })
      .catch(() => setError("无法加载配置，请检查后端是否运行"))
      .finally(() => setLoading(false));
  }, [open]);

  const handleSave = async () => {
    setSaving(true);
    setError("");
    setSuccess(false);
    try {
      const trimmedKey = apiKey.trim();
      const keyUnchanged = hasExistingKey && trimmedKey === maskedKey;
      await api.updateConfig(keyUnchanged ? {} : { deepseek_api_key: trimmedKey || null });
      const cfg = await api.getConfig();
      setSuccess(true);
      setHasExistingKey(cfg.has_deepseek_key);
      setMaskedKey(cfg.has_deepseek_key ? cfg.deepseek_api_key : "");
      setApiKey(cfg.has_deepseek_key ? cfg.deepseek_api_key : "");
      setSessionTokens(cfg.session_tokens);
      setTimeout(() => onOpenChange(false), 800);
    } catch {
      setError("保存失败，请重试");
    } finally {
      setSaving(false);
    }
  };

  const handleClear = () => {
    setApiKey("");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Key className="size-5 text-primary" />
            API Key 配置
          </DialogTitle>
          <DialogDescription>
            配置 DeepSeek API Key 后可使用 AI 智能分类和快速响应。
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                DeepSeek API Key
              </label>
              <div className="relative">
                <Input
                  type={showKey ? "text" : "password"}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="sk-..."
                  className="pr-20 font-mono text-xs"
                />
                <div className="absolute right-1 top-1/2 -translate-y-1/2 flex gap-1">
                  <button
                    type="button"
                    onClick={() => setShowKey(!showKey)}
                    className="p-1.5 text-muted-foreground hover:text-foreground transition-colors"
                    title={showKey ? "隐藏" : "显示"}
                  >
                    {showKey ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                  </button>
                  {apiKey && (
                    <button
                      type="button"
                      onClick={handleClear}
                      className="p-1.5 text-muted-foreground hover:text-red-500 transition-colors text-xs"
                      title="清空"
                    >
                      ✕
                    </button>
                  )}
                </div>
              </div>
              <p className="text-[10px] text-muted-foreground/60">
                从 <a href="https://platform.deepseek.com/api_keys" target="_blank" rel="noopener noreferrer" className="underline hover:text-primary">platform.deepseek.com</a> 获取
              </p>
            </div>

            {hasExistingKey && (
              <div className="flex items-center gap-1.5 text-xs text-emerald-600">
                <Check className="size-3.5" />
                <span>已配置 API Key</span>
              </div>
            )}

            {sessionTokens !== undefined && (
              <div className="text-[10px] text-muted-foreground/40">
                本轮会话 Token 用量：{sessionTokens.toLocaleString()}
              </div>
            )}

            {error && (
              <div className="flex items-center gap-1.5 text-xs text-red-500 bg-red-50 dark:bg-red-950/30 rounded-lg px-3 py-2">
                <AlertCircle className="size-3.5 shrink-0" />
                {error}
              </div>
            )}

            {success && (
              <div className="flex items-center gap-1.5 text-xs text-emerald-600 bg-emerald-50 dark:bg-emerald-950/30 rounded-lg px-3 py-2">
                <Check className="size-3.5" />
                保存成功
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
                取消
              </Button>
              <Button size="sm" onClick={handleSave} disabled={saving}>
                {saving && <Loader2 className="size-3.5 animate-spin mr-1" />}
                保存
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
