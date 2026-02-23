"""Re-process items when prompts/logic change. Resets items to a target status for reprocessing."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from src import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def backfill(target_status: str = "COLLECTED", source_id: str | None = None):
    """Reset DONE/EXTRACTED items back to target_status for reprocessing."""
    if source_id:
        count = await db.fetchval(
            """UPDATE items SET pipeline_status = $1, updated_at = now()
               WHERE pipeline_status IN ('DONE', 'EXTRACTED', 'ERROR')
                 AND source_id = $2
               RETURNING count(*)""",
            target_status, source_id,
        )
    else:
        count = await db.fetchval(
            """WITH updated AS (
                 UPDATE items SET pipeline_status = $1, updated_at = now()
                 WHERE pipeline_status IN ('DONE', 'EXTRACTED', 'ERROR')
                 RETURNING 1
               ) SELECT count(*) FROM updated""",
            target_status,
        )
    logger.info("Reset %s items to %s", count, target_status)


async def main():
    parser = argparse.ArgumentParser(description="Backfill pipeline items")
    parser.add_argument("--target", default="COLLECTED", help="Target pipeline status")
    parser.add_argument("--source", default=None, help="Filter by source_id")
    args = parser.parse_args()

    await db.run_migrations()
    await backfill(args.target, args.source)
    await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
