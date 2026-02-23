from __future__ import annotations

import logging
import random

import httpx
import trafilatura

from src import db
from src.collector.dedup import url_hash, content_hash
from src.settings import settings

logger = logging.getLogger(__name__)


async def fetch_web_search_source(source: dict) -> int:
    """Run Serper.dev (Google Search API) sweeps for constraint keywords. Returns new item count."""
    source_id = source["source_id"]
    queries = source.get("search_queries", [])
    if not queries or not settings.serper_api_key:
        if not settings.serper_api_key:
            logger.debug("No SERPER_API_KEY set, skipping web search for %s", source_id)
        return 0

    # Pick 2-3 random queries per sweep to stay within rate limits
    selected = random.sample(queries, min(3, len(queries)))
    new_count = 0

    for query in selected:
        results = await _serper_search(query, source.get("language", "en"))
        for result in results:
            url = result.get("link", "")
            if not url:
                continue

            uhash = url_hash(url)
            exists = await db.fetchval("SELECT 1 FROM items WHERE url_hash = $1", uhash)
            if exists:
                continue

            title = result.get("title", "")
            snippet = result.get("snippet", "")

            # Try to fetch full article text
            raw_text = snippet
            try:
                async with httpx.AsyncClient(timeout=15, follow_redirects=True, verify=False) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        extracted = trafilatura.extract(resp.text)
                        if extracted and len(extracted) > len(snippet):
                            raw_text = extracted
            except Exception:
                pass  # fall back to snippet

            chash = content_hash(raw_text)
            dup = await db.fetchval("SELECT 1 FROM items WHERE content_hash = $1", chash)
            if dup:
                continue

            await db.execute(
                """INSERT INTO items (source_id, url, url_hash, content_hash, title, raw_text,
                                      language, pipeline_status)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, 'COLLECTED')
                   ON CONFLICT (url_hash) DO NOTHING""",
                source_id, url, uhash, chash, title, raw_text,
                source.get("language", "en"),
            )
            new_count += 1

    if new_count:
        logger.info("Web search %s: found %d new items", source_id, new_count)
    return new_count


async def _serper_search(query: str, language: str = "en") -> list[dict]:
    """Call Serper.dev Google Search API and return organic results."""
    # Map language codes to Google search params
    lang_map = {
        "en": ("en", "us"),
        "ja": ("ja", "jp"),
        "ko": ("ko", "kr"),
        "zh": ("zh-cn", "cn"),
        "es": ("es", "mx"),
        "pt": ("pt-br", "br"),
        "de": ("de", "de"),
        "hi": ("hi", "in"),
        "zh-tw": ("zh-tw", "tw"),
    }
    hl, gl = lang_map.get(language, ("en", "us"))

    headers = {
        "X-API-KEY": settings.serper_api_key,
        "Content-Type": "application/json",
    }
    body = {
        "q": query,
        "num": 20,
        "hl": hl,
        "gl": gl,
        "tbs": "qdr:w",  # past week
    }

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("organic", [])
        except Exception as exc:
            logger.error("Serper search failed for '%s': %s", query, exc)
            return []
