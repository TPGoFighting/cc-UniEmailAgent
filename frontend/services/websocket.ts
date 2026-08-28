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
  private static connectedTasks = new Set<string>();

  connect(taskId: string, url: string, handlers: WSEventHandlers): void {
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
      this.reconnectAttempts = 0;
      try {
        this._handleEvent(JSON.parse(event.data) as WSEvent);
      } catch {
        // ignore malformed payloads
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
      try { this.ws.close(); } catch { /* ignore */ }
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

  private _handleEvent(data: WSEvent): void {
    if (!this.handlers) return;
    switch (data.type) {
      case "log":
        this.handlers.onLog(data.message, data.timestamp);
        break;
      case "text":
        this.handlers.onText(data.message, data.timestamp);
        break;
      case "download":
        this.handlers.onDownload(data.message, data.filename, data.url, data.timestamp);
        break;
      case "done":
        this.handlers.onDone(data.message, data.timestamp);
        break;
      case "error":
        this.handlers.onError(data.message);
        break;
      case "activity":
        if (this.handlers.onActivity && data.activity) {
          this.handlers.onActivity(data.activity, data.timestamp);
        }
        break;
      case "worker_progress":
        if (this.handlers.onWorkerProgress && data.worker_progress) {
          this.handlers.onWorkerProgress(data.worker_progress, data.timestamp);
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
