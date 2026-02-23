from __future__ import annotations

import logging

from src.llm import llm_extract

logger = logging.getLogger(__name__)

TRANSLATE_SYSTEM = """You are a precise technical translator for semiconductor, datacenter, and AI infrastructure content.

Rules:
- Translate to English faithfully
- PRESERVE all numbers, units, dates, percentages, and currency amounts exactly
- PRESERVE company names, product names, and technical terms (transliterate if needed)
- PRESERVE ticker symbols and stock exchange references
- Keep the same paragraph structure
- Do NOT add commentary or interpretation
- Do NOT omit any information from the original
- If a term has a standard English equivalent (e.g., 台積電 = TSMC), use it
- For ambiguous terms, include the original in parentheses

Output ONLY the translated text, nothing else."""


async def translate_to_english(text: str, source_lang: str) -> tuple[str, float]:
    """Translate text to English using LLM. Returns (translated_text, confidence).
    If text is already English, returns it unchanged."""
    if source_lang == "en":
        return text, 1.0

    if not text or len(text.strip()) < 20:
        return text, 0.0

    # Truncate very long texts
    truncated = text[:15000] if len(text) > 15000 else text

    prompt = f"Translate the following {source_lang} text to English:\n\n{truncated}"

    try:
        translated = await llm_extract(prompt, system=TRANSLATE_SYSTEM, temperature=0.1)
        # Rough confidence: higher for shorter texts (less room for error)
        confidence = 0.85 if len(text) < 5000 else 0.75
        return translated.strip(), confidence
    except Exception as exc:
        logger.error("Translation failed for %s text: %s", source_lang, exc)
        return text, 0.0
