import type { WSEvent, WSEventHandlers } from "@/lib/types";

/**
 * WebSocket 连接管理器
 * 管理单个任务的 WebSocket 连接生命周期
 */
export class WebSocketManager {
  private ws: WebSocket | null = null;
  private taskId: string = "";
  private handlers: WSEventHandlers | null = null;

  /**
   * 建立 WebSocket 连接
   */
  connect(
    taskId: string,
    url: string,
    handlers: WSEventHandlers
  ): void {
    this.disconnect();
    this.taskId = taskId;
    this.handlers = handlers;

    const ws = new WebSocket(url);
    this.ws = ws;

    ws.onopen = () => {
      // 连接已建立
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WSEvent;
        this.handleEvent(data);
      } catch {
        // 忽略无法解析的消息
      }
    };

    ws.onclose = () => {
      if (this.ws === ws) {
        this.ws = null;
        this.handlers?.onClose();
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  /**
   * 断开连接
   */
  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.handlers = null;
  }

  /**
   * 检查是否已连接
   */
  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  /**
   * 获取当前任务 ID
   */
  get currentTaskId(): string {
    return this.taskId;
  }

  private handleEvent(data: WSEvent): void {
    if (!this.handlers) return;

    switch (data.type) {
      case "log":
        this.handlers.onLog(data.message, data.timestamp);
        break;
      case "download":
        this.handlers.onDownload(
          data.message,
          data.filename,
          data.url,
          data.timestamp
        );
        break;
      case "done":
        this.handlers.onDone();
        break;
      case "error":
        this.handlers.onError(data.message);
        break;
    }
  }
}
