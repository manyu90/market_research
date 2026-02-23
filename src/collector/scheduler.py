from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src import db
from src.collector.rss import fetch_rss_source
from src.collector.scraper import fetch_scrape_html_source
from src.collector.js_renderer import fetch_js_source
from src.collector.pdf_monitor import fetch_pdf_source
from src.collector.web_search import fetch_web_search_source

logger = logging.getLogger(__name__)

FETCH_DISPATCH = {
    "rss": fetch_rss_source,
    "scrape_html": fetch_scrape_html_source,
    "scrape_js": fetch_js_source,
    "pdf_monitor": fetch_pdf_source,
    "web_search": fetch_web_search_source,
}


async def _collect_source(source: dict) -> None:
    """Dispatch a single source to its fetch handler."""
    method = source.get("fetch_method", "")
    handler = FETCH_DISPATCH.get(method)
    if not handler:
        logger.warning("Unknown fetch_method '%s' for source %s", method, source.get("source_id"))
        return
    try:
        await handler(source)
    except Exception:
        logger.exception("Error collecting source %s", source.get("source_id"))


def build_scheduler() -> AsyncIOScheduler:
    """Build APScheduler with a job per active source."""
    scheduler = AsyncIOScheduler()
    return scheduler


async def load_source_jobs(scheduler: AsyncIOScheduler) -> None:
    """Load sources from DB and add/update scheduler jobs."""
    rows = await db.fetch(
        """SELECT source_id, name, url, feed_url, fetch_method, scrape_target,
                  language, tier, reliability, earliness, schedule_minutes,
                  layers, search_queries, notes
           FROM sources WHERE status = 'CONFIRMED'"""
    )

    for row in rows:
        source = dict(row)
        job_id = f"collect:{source['source_id']}"
        minutes = source.get("schedule_minutes", 60)

        # Remove existing job if present (for reload)
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

        scheduler.add_job(
            _collect_source,
            "interval",
            minutes=minutes,
            args=[source],
            id=job_id,
            name=f"Collect {source['name']}",
            replace_existing=True,
            max_instances=1,
        )

    logger.info("Loaded %d source collection jobs", len(rows))


async def run_all_sources_once() -> int:
    """Run all confirmed sources once (for initial collection). Returns total new items."""
    rows = await db.fetch(
        """SELECT source_id, name, url, feed_url, fetch_method, scrape_target,
                  language, tier, reliability, earliness, schedule_minutes,
                  layers, search_queries, notes
           FROM sources WHERE status = 'CONFIRMED'"""
    )
    total = 0
    rss_sources = [dict(r) for r in rows if r["fetch_method"] == "rss"]
    other_sources = [dict(r) for r in rows if r["fetch_method"] != "rss"]

    # RSS sources first (most likely to work on first run)
    logger.info("Collecting %d RSS sources...", len(rss_sources))
    for i, source in enumerate(rss_sources, 1):
        handler = FETCH_DISPATCH.get("rss")
        if handler:
            try:
                logger.info("  [%d/%d] %s (%s)", i, len(rss_sources), source["name"], source["feed_url"] or "no feed")
                count = await handler(source)
                total += count
                if count:
                    logger.info("         → %d new items", count)
            except Exception:
                logger.exception("  [%d/%d] ERROR: %s", i, len(rss_sources), source["source_id"])

    # Other fetch methods
    logger.info("Collecting %d non-RSS sources (scrape/pdf/api/search)...", len(other_sources))
    for i, source in enumerate(other_sources, 1):
        method = source.get("fetch_method", "")
        handler = FETCH_DISPATCH.get(method)
        if handler:
            try:
                logger.info("  [%d/%d] [%s] %s", i, len(other_sources), method, source["name"])
                count = await handler(source)
                total += count
                if count:
                    logger.info("         → %d new items", count)
            except Exception:
                logger.exception("  [%d/%d] ERROR: %s", i, len(other_sources), source["source_id"])

    return total
