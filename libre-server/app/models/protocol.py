"""Typed WebSocket protocol, mirroring extension/src/types/protocol.ts.

Binary WS frames carry raw PCM16 mono 16kHz audio directly (no envelope);
everything else is a JSON text frame matching one of the models below.
"""

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

SourceLanguage = Literal["en", "ja", "zh"]


class ClientStart(BaseModel):
    type: Literal["start"]
    sourceLanguage: SourceLanguage


class ClientStop(BaseModel):
    type: Literal["stop"]


ClientControlMessage = Union[ClientStart, ClientStop]


class ServerReady(BaseModel):
    type: Literal["ready"] = "ready"


class ServerStatus(BaseModel):
    type: Literal["status"] = "status"
    status: Literal["listening", "transcribing", "translating"]


class ServerTranscript(BaseModel):
    type: Literal["transcript"] = "transcript"
    segmentId: str
    text: str
    language: SourceLanguage
    final: bool
    ts: float


class ServerSubtitle(BaseModel):
    type: Literal["subtitle"] = "subtitle"
    segmentId: str
    original: str
    translated: str
    final: bool
    ts: float


class ServerError(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str


ServerMessage = Union[ServerReady, ServerStatus, ServerTranscript, ServerSubtitle, ServerError]


def parse_client_message(raw: dict) -> ClientControlMessage:
    msg_type = raw.get("type")
    if msg_type == "start":
        return ClientStart.model_validate(raw)
    if msg_type == "stop":
        return ClientStop.model_validate(raw)
    raise ValueError(f"Unknown client message type: {msg_type!r}")
