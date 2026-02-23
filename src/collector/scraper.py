from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx
import trafilatura

from src import db
from src.collector.dedup import url_hash, content_hash

logger = logging.getLogger(__name__)


async def fetch_scrape_html_source(source: dict) -> int:
    """Scrape an HTML source: discover article links, extract text, insert items."""
    source_id = source["source_id"]
    target = source.get("scrape_target") or source.get("url")
    if not target:
        return 0

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, verify=False) as client:
        try:
            resp = await client.get(target)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Failed to scrape %s: %s", target, exc)
            return 0

    # Discover article links from the listing page
    links = trafilatura.extract_metadata(resp.text)
    # Use trafilatura's link extraction for article URLs
    article_urls = _extract_article_links(resp.text, target)

    if not article_urls:
        # If no links found, try to extract text directly from the page
        article_urls = [target]

    new_count = 0
    for url in article_urls[:20]:  # limit to 20 per sweep
        uhash = url_hash(url)
        exists = await db.fetchval("SELECT 1 FROM items WHERE url_hash = $1", uhash)
        if exists:
            continue

        # Fetch and extract article
        raw_text = ""
        title = ""
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True, verify=False) as client:
                art_resp = await client.get(url)
                if art_resp.status_code == 200:
                    raw_text = trafilatura.extract(art_resp.text) or ""
                    meta = trafilatura.extract_metadata(art_resp.text)
                    if meta:
                        title = meta.title or ""
        except Exception:
            logger.debug("Could not fetch %s", url)
            continue

        if not raw_text:
            continue

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
        logger.info("Source %s: scraped %d new items", source_id, new_count)
    return new_count


def _extract_article_links(html: str, base_url: str) -> list[str]:
    """Extract plausible article links from an HTML page."""
    from html.parser import HTMLParser

    links: list[str] = []

    class LinkParser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == "a":
                href = dict(attrs).get("href", "")
                if href and not href.startswith(("#", "javascript:", "mailto:")):
                    full = urljoin(base_url, href)
                    # Basic heuristic: article URLs tend to have path segments
                    if len(full.split("/")) > 4 and full not in links:
                        links.append(full)

    LinkParser().feed(html)
    return links
