"""Load seed_sources.yml and seed_entities.yml into Postgres."""
from __future__ import annotations

import asyncio
import json
import logging
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from src import db
from src.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def seed_sources() -> int:
    sources = settings.load_seed_sources()
    count = 0
    for s in sources:
        exists = await db.fetchval(
            "SELECT 1 FROM sources WHERE source_id = $1", s["source_id"]
        )
        if exists:
            continue

        await db.execute(
            """INSERT INTO sources (source_id, name, url, feed_url, fetch_method, scrape_target,
                                    language, tier, reliability, earliness, schedule_minutes,
                                    layers, search_queries, status, notes)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
               ON CONFLICT (source_id) DO NOTHING""",
            s["source_id"],
            s["name"],
            s.get("url"),
            s.get("feed_url"),
            s["fetch_method"],
            s.get("scrape_target"),
            s.get("language", "en"),
            s.get("tier", 2),
            s.get("reliability", 0.5),
            s.get("earliness", 0.5),
            s.get("schedule_minutes", 60),
            s.get("layers", []),
            s.get("search_queries"),
            "CONFIRMED",
            s.get("notes"),
        )
        count += 1
        logger.info("Seeded source: %s", s["source_id"])
    return count


async def seed_entities() -> int:
    entities = settings.load_seed_entities()
    count = 0
    for e in entities:
        exists = await db.fetchval(
            "SELECT 1 FROM entities WHERE entity_id = $1", e["entity_id"]
        )
        if exists:
            continue

        await db.execute(
            """INSERT INTO entities (entity_id, canonical_name, type, aliases, tickers,
                                     roles, layers, ring, geo, status, notes)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
               ON CONFLICT (entity_id) DO NOTHING""",
            e["entity_id"],
            e["canonical_name"],
            e["type"],
            json.dumps(e.get("aliases", {})),
            json.dumps(e.get("tickers", [])),
            e.get("roles", []),
            e.get("layers", []),
            e.get("ring"),
            e.get("geo"),
            "CONFIRMED",
            e.get("notes"),
        )
        count += 1
        logger.info("Seeded entity: %s (%s)", e["entity_id"], e["canonical_name"])
    return count


async def main():
    await db.run_migrations()
    src_count = await seed_sources()
    ent_count = await seed_entities()
    logger.info("Seeded %d sources, %d entities", src_count, ent_count)
    await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
