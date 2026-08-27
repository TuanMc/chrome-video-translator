"""Translation provider abstraction (requirement.md section 7)."""

from abc import ABC, abstractmethod
from typing import List, Optional


class TranslationProvider(ABC):
    @abstractmethod
    async def translate(self, text: str, source_language: str, context: Optional[List[str]] = None) -> str: ...
