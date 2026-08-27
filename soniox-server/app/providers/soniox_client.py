"""Thin wrapper around Soniox's real-time STT+translation WebSocket API.

Deliberately does NOT implement libre-server's SpeechToTextProvider /
TranslationProvider ABCs (app/providers/*/base.py there) — those exist to let
a server swap STT and translation backends independently. Soniox provides
both, inseparably, as one combined stream, so splitting it across two
interfaces would be a false abstraction rather than a real one.

Protocol reference: https://soniox.com/docs/api-reference/stt/websocket-api,
https://soniox.com/docs/translation/stt-translation/rt-translation,
https://soniox.com/docs/stt/rt/endpoint-detection. See README.md for what's
been verified against live Soniox traffic vs. assumed from docs alone.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import websockets

from app.config.settings import (
    AUDIO_CHANNELS,
    AUDIO_SAMPLE_RATE,
    SONIOX_API_KEY,
    SONIOX_ENABLE_ENDPOINT_DETECTION,
    SONIOX_MODEL,
    SONIOX_TARGET_LANGUAGE,
    SONIOX_WS_URL,
)

logger = logging.getLogger("soniox_client")

END_TOKEN = "<end>"


@dataclass
class SonioxEvent:
    """One parsed increment from a single Soniox response message.

    *_final_delta: newly-confirmed text to append to this segment's running
    total (finals are cumulative — never resent).
    *_draft: this response's full current non-final tail, which REPLACES
    (not appends to) whatever draft the caller was showing before — per
    Soniox docs, non-final tokens are reset and replaced on every response.
    """

    original_final_delta: str = ""
    original_draft: str = ""
    translated_final_delta: str = ""
    translated_draft: str = ""
    is_end: bool = False
    finished: bool = False
    error: Optional[str] = None
    # HTTP-style status Soniox includes on its error responses (verified
    # directly: 401 for a bad api_key, error_type "unauthenticated") — used
    # by the caller to decide whether the session is worth continuing (a bad
    # key never recovers) vs. a transient/non-fatal issue.
    error_code: Optional[int] = None


class SonioxClient:
    def __init__(self, source_language: str) -> None:
        self._source_language = source_language
        self._ws: Optional["websockets.WebSocketClientProtocol"] = None

    async def connect(self) -> None:
        if not SONIOX_API_KEY:
            raise RuntimeError("SONIOX_API_KEY is not set — see README.md for setup.")
        self._ws = await websockets.connect(SONIOX_WS_URL)
        config = {
            "api_key": SONIOX_API_KEY,
            "model": SONIOX_MODEL,
            "audio_format": "pcm_s16le",
            "sample_rate": AUDIO_SAMPLE_RATE,
            "num_channels": AUDIO_CHANNELS,
            "language_hints": [self._source_language],
            "enable_endpoint_detection": SONIOX_ENABLE_ENDPOINT_DETECTION,
            "translation": {"type": "one_way", "target_language": SONIOX_TARGET_LANGUAGE},
        }
        await self._ws.send(json.dumps(config))

    async def send_audio(self, chunk: bytes) -> None:
        assert self._ws is not None
        await self._ws.send(chunk)

    async def end_audio(self) -> None:
        """Signals end-of-audio to Soniox (its documented convention: an
        empty string frame). Soniox replies with a final response carrying
        "finished": true, then closes its side.

        Verified directly: if Soniox already closed the connection itself
        (e.g. after a fatal auth error — see translation_socket.py), this
        raises ConnectionClosedOK. That's an expected, benign race (nothing
        left to signal), not a bug — swallowed here rather than surfaced as
        a scary traceback on every session that ends this way."""
        assert self._ws is not None
        try:
            await self._ws.send("")
        except websockets.exceptions.ConnectionClosed:
            pass

    async def receive(self) -> AsyncIterator[SonioxEvent]:
        assert self._ws is not None
        async for raw in self._ws:
            yield self._parse_message(raw)

    @staticmethod
    def _parse_message(raw: str | bytes) -> SonioxEvent:
        payload = json.loads(raw)

        if payload.get("error_code") or payload.get("error_message"):
            return SonioxEvent(
                error=payload.get("error_message") or str(payload.get("error_code")),
                error_code=payload.get("error_code"),
            )

        event = SonioxEvent(finished=bool(payload.get("finished")))
        original_draft_parts: list[str] = []
        translated_draft_parts: list[str] = []

        for token in payload.get("tokens", []):
            text = token.get("text", "")
            is_final = bool(token.get("is_final"))
            status = token.get("translation_status")  # "original" | "translation" | None

            if text == END_TOKEN:
                event.is_end = True
                continue

            is_translation = status == "translation"

            if is_final:
                if is_translation:
                    event.translated_final_delta += text
                else:
                    event.original_final_delta += text
            else:
                if is_translation:
                    translated_draft_parts.append(text)
                else:
                    original_draft_parts.append(text)

        event.original_draft = "".join(original_draft_parts)
        event.translated_draft = "".join(translated_draft_parts)
        return event

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
