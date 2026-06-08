import type { WSEvent, WSEventHandlers } from "@/lib/types";

class WebSocketManager {
  private ws: WebSocket | null = null;
  private taskId = "";
  private handlers: WSEventHandlers | null = null;
  private wsUrl = "";
  private shouldReconnect = false;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private maxReconnectDelay = 30000;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  // 模块级 Set，跨 Strict Mode 双挂载周期持久
  private static connectedTasks = new Set<string>();

  connect(taskId: string, url: string, handlers: WSEventHandlers): void {
    // 防止 React Strict Mode 双倍触发
    if (WebSocketManager.connectedTasks.has(taskId)) {
      this.handlers = handlers;
      return;
    }
    WebSocketManager.connectedTasks.add(taskId);
    this.disconnect();
    this.taskId = taskId;
    this.handlers = handlers;
    this.wsUrl = url;
    this.shouldReconnect = true;
    this.reconnectAttempts = 0;

    this._createWebSocket(url);
  }

  private _createWebSocket(url: string): void {
    const ws = new WebSocket(url);
    this.ws = ws;

    ws.onmessage = (event) => {
      // Reset reconnect counter on successful message
      this.reconnectAttempts = 0;
      try {
        this.handleEvent(JSON.parse(event.data) as WSEvent);
      } catch {
        // Ignore malformed websocket payloads.
      }
    };

    ws.onclose = () => {
      if (this.ws === ws) {
        this.ws = null;
        this.handlers?.onClose();
        this._scheduleReconnect();
      }
    };

    ws.onerror = () => ws.close();
  }

  private _scheduleReconnect(): void {
    if (!this.shouldReconnect) return;
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.shouldReconnect = false;
      this.handlers?.onError("连接已断开，请刷新页面重试");
      return;
    }
    const delay = Math.min(
      1000 * Math.pow(2, this.reconnectAttempts++),
      this.maxReconnectDelay
    );
    this.reconnectTimer = setTimeout(() => {
      if (!this.shouldReconnect || !this.taskId || !this.wsUrl) return;
      this._createWebSocket(this.wsUrl);
    }, delay);
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onclose = null;
      try { this.ws.close(); } catch {}
      this.ws = null;
    }
    this.handlers = null;
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  get currentTaskId(): string {
    return this.taskId;
  }

  private handleStage(data: WSEvent): void {
    if (!this.handlers?.stageHandlers) return;
    switch (data.type) {
      case "stage_start":
        this.handlers.stageHandlers.onStageStart(data.stage, data.college, data.college_index, data.college_total);
        break;
      case "stage_progress":
        this.handlers.stageHandlers.onStageProgress(data.stage, data.phase, data.found, data.extracted, data.total_pages);
        break;
      case "stage_done":
        this.handlers.stageHandlers.onStageDone(data.stage, data.college, data.found, data.valid_email, data.elapsed_ms);
        break;
    }
  }

  private handleEvent(data: WSEvent): void {
    if (!this.handlers) return;
    switch (data.type) {
      case "stage_start":
      case "stage_progress":
      case "stage_done":
        this.handleStage(data);
        break;
      // Phase 2: New WS message types
      case "stage":
        this.handlers.onCrawlStage?.(data.stage, data.stage_name, data.progress_pct, data.timestamp);
        break;
      case "stats":
        this.handlers.onCrawlStats?.(data.teachers_found, data.emails_extracted, data.departments_done, data.department_names, data.timestamp);
        break;
      case "summary":
        this.handlers.onCrawlSummary?.(data.university, data.total_teachers, data.total_emails, data.duration, data.files, data.timestamp);
        break;
      case "error_user":
        this.handlers.onErrorUser?.(data.message, data.severity, data.timestamp);
        break;
      case "progress":
        this.handlers.onProgress(data.message, data.step, data.total, data.timestamp);
        break;
      case "download":
        this.handlers.onDownload(data.message, data.filename, data.url, data.timestamp);
        break;
      case "file":
        this.handlers.onFile(data.message, data.filename, data.filepath, data.timestamp);
        break;
      case "log":
        this.handlers.onLog(data.message, data.timestamp);
        break;
      case "agent":
        this.handlers.onText(data.message, data.timestamp);
        break;
      case "text":
        this.handlers.onText(data.message, data.timestamp);
        break;
      case "done":
        this.handlers.onDone(data.message, data.timestamp);
        break;
      case "error":
        this.handlers.onError(data.message);
        break;
      case "eval":
        try {
          this.handlers.onEval?.({
            quality_score: data.quality_score,
            passed: data.passed,
            warnings: data.warnings,
            email_rate: data.email_rate,
            colleges_found: data.colleges_found,
            timestamp: data.timestamp,
          });
        } catch {
          // 静默兜底
        }
        break;
      case "trace":
        try {
          this.handlers.onTrace?.(data.trace_url);
        } catch {
          // 静默兜底
        }
        break;
    }
  }
}

let _instance: WebSocketManager | null = null;

export function getWsManager(): WebSocketManager {
  if (!_instance) _instance = new WebSocketManager();
  return _instance;
}
