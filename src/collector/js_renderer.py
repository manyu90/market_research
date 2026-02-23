from __future__ import annotations

import logging

from src import db
from src.collector.dedup import url_hash, content_hash

logger = logging.getLogger(__name__)

# Lazy browser init — only import playwright when needed
_browser = None


async def _get_browser():
    global _browser
    if _browser is None:
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        _browser = await pw.chromium.launch(headless=True)
    return _browser


async def fetch_js_source(source: dict) -> int:
    """Render a JS-heavy page with Playwright, extract text, insert items."""
    import trafilatura

    source_id = source["source_id"]
    target = source.get("scrape_target") or source.get("url")
    if not target:
        return 0

    try:
        browser = await _get_browser()
        page = await browser.new_page()
        await page.goto(target, wait_until="networkidle", timeout=30000)
        html = await page.content()
        await page.close()
    except Exception as exc:
        logger.error("Playwright failed for %s: %s", target, exc)
        return 0

    raw_text = trafilatura.extract(html) or ""
    if not raw_text:
        return 0

    uhash = url_hash(target)
    exists = await db.fetchval("SELECT 1 FROM items WHERE url_hash = $1", uhash)
    if exists:
        return 0

    chash = content_hash(raw_text)
    dup = await db.fetchval("SELECT 1 FROM items WHERE content_hash = $1", chash)
    if dup:
        return 0

    title = ""
    meta = trafilatura.extract_metadata(html)
    if meta:
        title = meta.title or ""

    await db.execute(
        """INSERT INTO items (source_id, url, url_hash, content_hash, title, raw_text,
                              language, pipeline_status)
           VALUES ($1, $2, $3, $4, $5, $6, $7, 'COLLECTED')
           ON CONFLICT (url_hash) DO NOTHING""",
        source_id, target, uhash, chash, title, raw_text,
        source.get("language", "en"),
    )
    logger.info("Source %s: collected 1 item via Playwright", source_id)
    return 1
