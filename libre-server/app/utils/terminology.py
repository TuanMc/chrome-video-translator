"""Protects known technical terms from NLLB mistranslation/transliteration
(requirement.md section 10 / 34) by swapping them for placeholders before
translation and restoring them after.

Limitation: this only helps when the term survives STT as the literal Latin
word. Whisper sometimes transliterates it instead (e.g. "React" -> リアクト in
Japanese) — this technique can't catch that case; it would need a phonetic
glossary, out of scope here.

Match uses a not-preceded/followed-by-ASCII-letter lookaround rather than
`\\b`, because `\\b` doesn't create a boundary between an ASCII word and
adjacent CJK text (both count as "word" characters to Python's regex engine),
which would otherwise miss terms written with no space, e.g. "Reactについて".
"""

import re
from typing import Dict, Tuple

PROTECTED_TERMS = [
    "React",
    "TypeScript",
    "JavaScript",
    "API",
    "AWS",
    "Docker",
    "Kubernetes",
    "Python",
    "FastAPI",
    "GitHub",
    "Node.js",
    "npm",
]

_PLACEHOLDER = "XTERM{}X"


def protect_terms(text: str) -> Tuple[str, Dict[str, str]]:
    mapping: Dict[str, str] = {}
    result = text
    for i, term in enumerate(PROTECTED_TERMS):
        pattern = re.compile(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", re.IGNORECASE)
        if pattern.search(result):
            placeholder = _PLACEHOLDER.format(i)
            mapping[placeholder] = term
            result = pattern.sub(placeholder, result)
    return result, mapping


def restore_terms(text: str, mapping: Dict[str, str]) -> str:
    for placeholder, term in mapping.items():
        text = re.sub(re.escape(placeholder), term, text, flags=re.IGNORECASE)
    return text
