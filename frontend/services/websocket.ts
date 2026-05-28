import type { WSEvent, WSEventHandlers } from "@/lib/types";

class WebSocketManager {
  private ws: WebSocket | null = null;
  private taskId = "";
  private handlers: WSEventHandlers | null = null;

  connect(taskId: string, url: string, handlers: WSEventHandlers): void {
    this.disconnect();
    this.taskId = taskId;
    this.handlers = handlers;

    const ws = new WebSocket(url);
    this.ws = ws;

    ws.onmessage = (event) => {
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
      }
    };

    ws.onerror = () => ws.close();
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
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

  private handleEvent(data: WSEvent): void {
    if (!this.handlers) return;
    switch (data.type) {
      case "progress":
        this.handlers.onProgress(data.message, data.step, data.total, data.timestamp);
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
    }
  }
}

let _instance: WebSocketManager | null = null;

export function getWsManager(): WebSocketManager {
  if (!_instance) _instance = new WebSocketManager();
  return _instance;
}
