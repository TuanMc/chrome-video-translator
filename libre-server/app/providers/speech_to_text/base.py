"""STT provider abstraction (requirement.md section 7).

Represents one client's streaming session, not the underlying model — a
provider implementation wraps a shared, already-loaded model instance so
model load cost is paid once at server startup (section 25), not per session.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional


@dataclass
class TranscriptResult:
    text: str
    language: str
    is_final: bool
    segment_id: str
    confidence: Optional[float] = None


TranscriptCallback = Callable[[TranscriptResult], Awaitable[None]]
ErrorCallback = Callable[[str], Awaitable[None]]


class SpeechToTextProvider(ABC):
    @abstractmethod
    async def start(self, language: str) -> None: ...

    @abstractmethod
    def send_audio(self, chunk: bytes) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    def on_transcript(self, callback: TranscriptCallback) -> None: ...

    @abstractmethod
    def on_error(self, callback: ErrorCallback) -> None:
        """Non-fatal: a single failed transcription pass doesn't end the session —
        the next scheduled pass retries over the same (plus more) buffered audio.
        This exists purely so failures are visible to the client instead of only
        appearing in server logs (requirement.md section 27: "STT provider error")."""
        ...
