from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser
import httpx
import trafilatura

from src import db
from src.collector.dedup import url_hash, content_hash

logger = logging.getLogger(__name__)


async def fetch_rss_source(source: dict) -> int:
    """Fetch an RSS feed and insert new items. Returns count of new items."""
    feed_url = source.get("feed_url")
    source_id = source["source_id"]
    if not feed_url:
        logger.warning("Source %s has no feed_url, skipping", source_id)
        return 0

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        try:
            resp = await client.get(feed_url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Failed to fetch RSS %s: %s", feed_url, exc)
            return 0

    feed = feedparser.parse(resp.text)
    new_count = 0

    for entry in feed.entries:
        link = entry.get("link", "")
        if not link:
            continue

        uhash = url_hash(link)

        # Check if already collected
        exists = await db.fetchval(
            "SELECT 1 FROM items WHERE url_hash = $1", uhash
        )
        if exists:
            continue

        # Try to extract full text via trafilatura
        title = entry.get("title", "")
        raw_text = ""
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                article_resp = await client.get(link)
                if article_resp.status_code == 200:
                    extracted = trafilatura.extract(article_resp.text)
                    raw_text = extracted or ""
        except Exception:
            logger.debug("Could not fetch full text for %s", link)

        # Fall back to RSS summary if no full text
        if not raw_text:
            raw_text = entry.get("summary", "") or entry.get("description", "")

        # Parse published date
        published_at = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass

        chash = content_hash(raw_text) if raw_text else None

        # Content-level dedup
        if chash:
            dup = await db.fetchval(
                "SELECT 1 FROM items WHERE content_hash = $1", chash
            )
            if dup:
                continue

        await db.execute(
            """INSERT INTO items (source_id, url, url_hash, content_hash, title, raw_text,
                                  language, published_at, pipeline_status)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'COLLECTED')
               ON CONFLICT (url_hash) DO NOTHING""",
            source_id, link, uhash, chash, title, raw_text,
            source.get("language", "en"), published_at,
        )
        new_count += 1

    if new_count:
        logger.info("Source %s: collected %d new items", source_id, new_count)
    return new_count
