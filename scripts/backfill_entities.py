"""Backfill: scan all existing events and register any entities not in the entities table."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import db
from src.linker.entity_discovery import discover_entity


async def main():
    await db.run_migrations()

    # Get all unique entity references from events
    rows = await db.fetch(
        "SELECT id, item_id, constraint_layer, entities FROM events"
    )

    seen = set()
    created = 0
    bumped = 0

    for row in rows:
        entities = row["entities"]
        if isinstance(entities, str):
            entities = json.loads(entities)

        for ent in entities:
            eid = ent.get("entity_id", "")
            if not eid or eid in seen:
                continue
            seen.add(eid)

            parts = eid.split(":")
            name_part = parts[-1] if parts else eid
            readable_name = name_part.replace("_", " ").title()
            entity_type = parts[1] if len(parts) >= 2 else "company"

            # Check if already exists
            exists = await db.fetchval(
                "SELECT 1 FROM entities WHERE entity_id = $1", eid
            )
            if exists:
                bumped += 1
                continue

            # Also check by name
            exists_by_name = await db.fetchval(
                "SELECT 1 FROM entities WHERE canonical_name ILIKE $1", readable_name
            )
            if exists_by_name:
                bumped += 1
                continue

            await discover_entity(
                name=readable_name,
                entity_type=entity_type,
                item_id=str(row["item_id"]),
                layer_hint=row["constraint_layer"],
                role_hint=ent.get("role"),
                entity_id_override=eid,
            )
            created += 1

    print(f"Done. {created} new entities created, {bumped} already existed.")
    print(f"Total unique entity IDs in events: {len(seen)}")

    # Show counts by status
    status_rows = await db.fetch(
        "SELECT status, COUNT(*) as cnt FROM entities GROUP BY status ORDER BY status"
    )
    for r in status_rows:
        print(f"  {r['status']}: {r['cnt']}")

    await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
