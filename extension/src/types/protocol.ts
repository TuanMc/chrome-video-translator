// WebSocket protocol between the extension and the local server.
// Mirrors server/app/models/protocol.py — keep both in sync.
//
// Binary WS frames carry raw PCM16 mono 16kHz audio directly (no envelope);
// everything else is a JSON text frame matching one of the types below.

export type SourceLanguage = "en" | "ja" | "zh";

export type ClientControlMessage =
  | { type: "start"; sourceLanguage: SourceLanguage }
  | { type: "stop" };

export type ServerMessage =
  | { type: "ready" }
  | { type: "status"; status: "listening" | "transcribing" | "translating" }
  | { type: "transcript"; segmentId: string; text: string; language: SourceLanguage; final: boolean; ts: number }
  | {
      type: "subtitle";
      segmentId: string;
      original: string;
      translated: string;
      final: boolean;
      ts: number;
    }
  | { type: "error"; code: string; message: string };
