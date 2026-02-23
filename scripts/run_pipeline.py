"""Main entry point: scheduler + pipeline processing loop."""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import db
from src.collector.scheduler import build_scheduler, load_source_jobs, run_all_sources_once
from src.extractor.event_extractor import extract_and_store
from src.normalizer.lang_detect import detect_language
from src.normalizer.translator import translate_to_english
from src.linker.entity_linker import link_entities_in_text, store_entity_mentions, load_alias_index
from src.linker.entity_discovery import promote_entities
from src.themes.clusterer import run_theme_cycle
from src.alerts.triage import run_alert_triage
from src.alerts.digest import build_daily_digest
from src.settings import PROJECT_ROOT

# ---------------------------------------------------------------------------
# Logging: console (INFO) + file (DEBUG) — always flushed, never a black box
# ---------------------------------------------------------------------------
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "pipeline.log"

root = logging.getLogger()
root.setLevel(logging.DEBUG)

# Console — INFO level, immediate flush
console = logging.StreamHandler(sys.stderr)
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter(
    "%(asctime)s │ %(levelname)-7s │ %(name)-28s │ %(message)s",
    datefmt="%H:%M:%S",
))
root.addHandler(console)

# File — DEBUG level, full detail
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
))
root.addHandler(file_handler)

# Quiet noisy libraries
for noisy in ("httpx", "httpcore", "asyncio", "apscheduler.executors", "hpack"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

logger = logging.getLogger("pipeline")

BATCH_SIZE = 40
PIPELINE_INTERVAL = 15  # seconds between pipeline sweeps


# ---------------------------------------------------------------------------
# Pipeline stages — each logs clearly what it's doing
# ---------------------------------------------------------------------------

async def _normalize_one(row: dict) -> tuple[bool, str]:
    """Normalize a single item (detect lang + translate). Returns (ok, title)."""
    title = (row["title"] or "untitled")[:60]
    try:
        text = row["raw_text"] or ""
        detected_lang, lang_conf = detect_language(text)

        if detected_lang != "en" and text:
            logger.info("  translating (%s→en): %s", detected_lang, title)
            text_en, trans_conf = await translate_to_english(text, detected_lang)
        else:
            text_en = text
            trans_conf = 1.0
            logger.debug("  already en: %s", title)

        await db.execute(
            """UPDATE items SET language = $2, text_en = $3,
                      translation_confidence = $4, updated_at = now()
               WHERE id = $1""",
            row["id"], detected_lang, text_en, trans_conf,
        )
        return True, title
    except Exception:
        logger.exception("  ERROR normalizing: %s", title)
        await db.execute(
            "UPDATE items SET pipeline_status = 'ERROR', pipeline_error = 'normalize_error', updated_at = now() WHERE id = $1",
            row["id"],
        )
        return False, title


async def process_collected_items() -> int:
    """COLLECTED -> detect lang, translate -> NORMALIZED."""
    rows = await db.fetch(
        """UPDATE items
           SET pipeline_status = 'NORMALIZED', updated_at = now()
           WHERE id IN (
               SELECT id FROM items
               WHERE pipeline_status = 'COLLECTED'
               ORDER BY fetched_at
               LIMIT $1
               FOR UPDATE SKIP LOCKED
           )
           RETURNING id, raw_text, language, title""",
        BATCH_SIZE,
    )
    if not rows:
        return 0

    logger.info("NORMALIZE: picked up %d items", len(rows))

    run_id = await db.fetchval(
        "INSERT INTO pipeline_runs (stage, items_processed) VALUES ('normalize', $1) RETURNING id",
        len(rows),
    )

    results = await asyncio.gather(*[_normalize_one(dict(r)) for r in rows])
    errored = sum(1 for ok, _ in results if not ok)

    await db.execute(
        "UPDATE pipeline_runs SET finished_at = now(), items_errored = $2 WHERE id = $1",
        run_id, errored,
    )
    logger.info("NORMALIZE: done (%d ok, %d errors)", len(rows) - errored, errored)
    return len(rows)


async def _link_one(row: dict) -> tuple[bool, str]:
    """Link entities in a single item. Returns (ok, title)."""
    title = (row["title"] or "untitled")[:60]
    try:
        text = row["text_en"] or row["raw_text"] or ""
        matches = await link_entities_in_text(text, str(row["id"]))
        if matches:
            await store_entity_mentions(str(row["id"]), matches)
            entity_names = [m["entity_id"].split(":")[-1] for m in matches[:5]]
            logger.info("  %d entities: [%s] — %s", len(matches), ", ".join(entity_names), title)
        else:
            logger.debug("  no entities: %s", title)
        return True, title
    except Exception:
        logger.exception("  ERROR linking: %s", title)
        await db.execute(
            "UPDATE items SET pipeline_status = 'ERROR', pipeline_error = 'link_error', updated_at = now() WHERE id = $1",
            row["id"],
        )
        return False, title


async def process_normalized_items() -> int:
    """NORMALIZED -> entity linking -> LINKED."""
    rows = await db.fetch(
        """UPDATE items
           SET pipeline_status = 'LINKED', updated_at = now()
           WHERE id IN (
               SELECT id FROM items
               WHERE pipeline_status = 'NORMALIZED'
               ORDER BY fetched_at
               LIMIT $1
               FOR UPDATE SKIP LOCKED
           )
           RETURNING id, text_en, raw_text, title""",
        BATCH_SIZE,
    )
    if not rows:
        return 0

    logger.info("LINK: picked up %d items", len(rows))

    run_id = await db.fetchval(
        "INSERT INTO pipeline_runs (stage, items_processed) VALUES ('link', $1) RETURNING id",
        len(rows),
    )

    results = await asyncio.gather(*[_link_one(dict(r)) for r in rows])
    errored = sum(1 for ok, _ in results if not ok)

    await db.execute(
        "UPDATE pipeline_runs SET finished_at = now(), items_errored = $2 WHERE id = $1",
        run_id, errored,
    )
    logger.info("LINK: done (%d ok, %d errors)", len(rows) - errored, errored)
    return len(rows)


async def _extract_one(row: dict) -> tuple[bool, int, str]:
    """Extract events from a single item. Returns (ok, event_count, title)."""
    title = (row["title"] or "untitled")[:60]
    try:
        logger.info("  extracting: %s", title)
        count = await extract_and_store(str(row["id"]))
        if count:
            logger.info("  → %d events: %s", count, title)
        else:
            logger.debug("  → no events: %s", title)
        return True, count, title
    except Exception:
        logger.exception("  ERROR extracting: %s", title)
        await db.execute(
            "UPDATE items SET pipeline_status = 'ERROR', pipeline_error = 'extraction_error', updated_at = now() WHERE id = $1",
            row["id"],
        )
        return False, 0, title


async def process_linked_items() -> int:
    """LINKED -> LLM extraction -> DONE."""
    rows = await db.fetch(
        """UPDATE items
           SET pipeline_status = 'EXTRACTED', updated_at = now()
           WHERE id IN (
               SELECT id FROM items
               WHERE pipeline_status = 'LINKED'
               ORDER BY fetched_at
               LIMIT $1
               FOR UPDATE SKIP LOCKED
           )
           RETURNING id, title""",
        BATCH_SIZE,
    )
    if not rows:
        return 0

    logger.info("EXTRACT: picked up %d items for LLM extraction", len(rows))

    run_id = await db.fetchval(
        "INSERT INTO pipeline_runs (stage, items_processed) VALUES ('extract', $1) RETURNING id",
        len(rows),
    )

    results = await asyncio.gather(*[_extract_one(dict(r)) for r in rows])
    errored = sum(1 for ok, _, _ in results if not ok)
    total_events = sum(c for _, c, _ in results)

    await db.execute(
        "UPDATE pipeline_runs SET finished_at = now(), items_errored = $2 WHERE id = $1",
        run_id, errored,
    )
    logger.info("EXTRACT: done (%d items → %d events, %d errors)", len(rows), total_events, errored)
    return len(rows)


# ---------------------------------------------------------------------------
# Main loop + startup
# ---------------------------------------------------------------------------

async def pipeline_loop():
    """Continuous pipeline processing loop."""
    cycle = 0
    while True:
        cycle += 1
        logger.info("━━━ Pipeline cycle %d ━━━", cycle)
        try:
            n1 = await process_collected_items()
            n2 = await process_normalized_items()
            n3 = await process_linked_items()

            if n1 + n2 + n3 == 0:
                logger.info("Nothing to process, sleeping %ds", PIPELINE_INTERVAL)

            # Entity discovery promotion
            promoted = await promote_entities()
            if promoted:
                logger.info("ENTITIES: promoted %d entities", promoted)

            # Theme cycle
            await run_theme_cycle()

            # Alert triage
            await run_alert_triage()

        except Exception:
            logger.exception("Pipeline loop error")

        await asyncio.sleep(PIPELINE_INTERVAL)


async def main():
    logger.info("=" * 60)
    logger.info("AI Constraints Radar — starting up")
    logger.info("Log file: %s", LOG_FILE)
    logger.info("=" * 60)

    # Run migrations
    logger.info("Running DB migrations...")
    await db.run_migrations()
    logger.info("Migrations complete")

    # Load entity alias index
    logger.info("Loading entity alias index...")
    await load_alias_index()

    # Print DB stats
    src_count = await db.fetchval("SELECT COUNT(*) FROM sources WHERE status = 'CONFIRMED'")
    ent_count = await db.fetchval("SELECT COUNT(*) FROM entities")
    logger.info("DB: %d confirmed sources, %d entities", src_count, ent_count)

    # Initial collection sweep
    logger.info("─── Initial collection sweep ───")
    new_items = await run_all_sources_once()
    logger.info("Initial sweep done: %d new items collected", new_items)

    # Print what we got
    items_total = await db.fetchval("SELECT COUNT(*) FROM items")
    logger.info("Total items in DB: %d", items_total)

    # Build and start scheduler
    scheduler = build_scheduler()
    await load_source_jobs(scheduler)

    # Daily digest at 07:00 UTC
    scheduler.add_job(
        build_daily_digest,
        "cron",
        hour=7,
        minute=0,
        id="daily_digest",
        name="Daily Digest",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started (%d jobs)", len(scheduler.get_jobs()))

    # Handle shutdown
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    logger.info("─── Entering pipeline loop (Ctrl+C to stop) ───")

    # Run pipeline loop until shutdown
    pipeline_task = asyncio.create_task(pipeline_loop())
    await stop_event.wait()

    # Cleanup
    scheduler.shutdown(wait=False)
    pipeline_task.cancel()
    await db.close_pool()
    logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
