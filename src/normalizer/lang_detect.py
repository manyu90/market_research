from __future__ import annotations

import logging

from lingua import Language, LanguageDetectorBuilder

logger = logging.getLogger(__name__)

# Build detector once — supports the languages we care about
_SUPPORTED = [
    Language.ENGLISH, Language.JAPANESE, Language.KOREAN, Language.CHINESE,
    Language.GERMAN, Language.FRENCH, Language.SPANISH, Language.PORTUGUESE,
    Language.HINDI,
]
_detector = LanguageDetectorBuilder.from_languages(*_SUPPORTED).build()

# Map lingua Language to ISO 639-1 codes
_LANG_MAP = {
    Language.ENGLISH: "en",
    Language.JAPANESE: "ja",
    Language.KOREAN: "ko",
    Language.CHINESE: "zh",
    Language.GERMAN: "de",
    Language.FRENCH: "fr",
    Language.SPANISH: "es",
    Language.PORTUGUESE: "pt",
    Language.HINDI: "hi",
}


def detect_language(text: str) -> tuple[str, float]:
    """Detect language of text. Returns (iso_code, confidence)."""
    if not text or len(text.strip()) < 10:
        return "en", 0.0

    results = _detector.compute_language_confidence_values(text)
    if not results:
        return "en", 0.0

    top = results[0]
    iso = _LANG_MAP.get(top.language, "en")
    return iso, round(top.value, 3)
