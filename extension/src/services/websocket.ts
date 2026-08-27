import type { ClientControlMessage, ServerMessage } from "../types/protocol";

export interface TranslationSocketHandlers {
  onServerMessage?: (message: ServerMessage) => void;
  onClose?: (event: CloseEvent) => void;
  onError?: () => void;
}

export class TranslationSocket {
  private ws: WebSocket | null = null;
  private readonly url: string;
  private readonly handlers: TranslationSocketHandlers;

  constructor(url: string, handlers: TranslationSocketHandlers = {}) {
    this.url = url;
    this.handlers = handlers;
  }

  connect(start: Extract<ClientControlMessage, { type: "start" }>): Promise<void> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(this.url);
      ws.binaryType = "arraybuffer";
      this.ws = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify(start));
        resolve();
      };
      ws.onerror = () => {
        this.handlers.onError?.();
        reject(new Error(`Could not connect to local server at ${this.url}.`));
      };
      ws.onclose = (event) => this.handlers.onClose?.(event);
      ws.onmessage = (event) => {
        if (typeof event.data === "string") {
          this.handlers.onServerMessage?.(JSON.parse(event.data) as ServerMessage);
        }
      };
    });
  }

  sendAudio(chunk: ArrayBuffer): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(chunk);
    }
  }

  stop(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "stop" } satisfies ClientControlMessage));
    }
  }

  close(): void {
    this.ws?.close();
    this.ws = null;
  }
}
