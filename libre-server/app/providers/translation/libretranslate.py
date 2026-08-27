"""Self-hosted LibreTranslate translation provider.

Independent server variant — see nllb-server's app/providers/translation/nllb.py
for the sibling implementation and the shared "translate each finalized segment
independently, `context` unused" reasoning (LibreTranslate is Argos-based MT,
same story as NLLB being sentence-level NMT: no safe way to feed it multi-turn
context).

Measured directly (this project, casual/slang EN/JA/ZH -> VI test sentences):
LibreTranslate is noticeably better than NLLB at interjections and register
("Damn" -> correct "Mẹ kiếp" vs. NLLB's nonsense "Đồ đập"; "crush" -> correct
"thích" vs. NLLB's overstated "yêu"). It's measurably worse in spots too —
dropped "kiss" entirely from one Japanese test sentence, and prior to the
protect_terms/restore_terms wiring below, mistranslated technical terms
(React -> "phản ứng", Docker -> "chim gõ kiến"). Neither backend is a strict
upgrade over the other — see README.md for the full comparison and when to
run this server instead of nllb-server.
"""

from __future__ import annotations

from typing import List, Optional

import httpx

from app.providers.translation.base import TranslationProvider
from app.utils.terminology import protect_terms, restore_terms

# Codes LibreTranslate actually reported via its own /languages endpoint when
# tested directly this session — not assumed from documentation.
LIBRETRANSLATE_LANGUAGE_MAP = {
    "en": "en",
    "ja": "ja",
    "zh": "zh-Hans",
}
TARGET_LANG_CODE = "vi"


class LibreTranslateProvider(TranslationProvider):
    def __init__(self, base_url: str, timeout_seconds: float = 10.0):
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def is_reachable(self, timeout_seconds: float = 1.0) -> bool:
        try:
            response = await self._client.get(f"{self._base_url}/languages", timeout=timeout_seconds)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def translate(self, text: str, source_language: str, context: Optional[List[str]] = None) -> str:
        # `context` intentionally unused — see module docstring.
        src_code = LIBRETRANSLATE_LANGUAGE_MAP.get(source_language)
        if src_code is None:
            raise ValueError(f"Unsupported source language for LibreTranslate: {source_language!r}")

        protected_text, mapping = protect_terms(text)

        response = await self._client.post(
            f"{self._base_url}/translate",
            json={"q": protected_text, "source": src_code, "target": TARGET_LANG_CODE, "format": "text"},
        )
        response.raise_for_status()
        translated = response.json()["translatedText"]
        return restore_terms(translated, mapping)

    async def aclose(self) -> None:
        await self._client.aclose()
