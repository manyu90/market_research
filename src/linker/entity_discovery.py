from __future__ import annotations

import json
import logging
import re

from src import db
from src.linker.entity_linker import load_alias_index

logger = logging.getLogger(__name__)

# Map LLM entity type prefixes to valid DB types
_TYPE_MAP = {
    "company": "COMPANY",
    "facility": "FACILITY",
    "product": "PRODUCT",
    "component": "COMPONENT",
    "material": "MATERIAL",
    "process_tech": "PROCESS_TECH",
    "buyer_class": "BUYER_CLASS",
    "geo": "GEO",
    "location": "GEO",
    "policy_program": "POLICY_PROGRAM",
    "index": "INDEX",
    # Catch-alls for LLM-generated types
    "agency": "POLICY_PROGRAM",
    "regulator": "POLICY_PROGRAM",
    "org": "COMPANY",
    "person": "COMPANY",
    "entity": "COMPANY",
    "industry": "BUYER_CLASS",
    "generic": "BUYER_CLASS",
    "unknown": "COMPANY",
    "utility": "COMPANY",
}


def _normalize_type(raw_type: str) -> str:
    """Map a raw entity type to a valid DB type."""
    return _TYPE_MAP.get(raw_type.lower(), "COMPANY")


def _slugify(name: str) -> str:
    """Create a slug from entity name for entity_id."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug[:50]


async def discover_entity(
    name: str,
    entity_type: str,
    item_id: str,
    layer_hint: str | None = None,
    role_hint: str | None = None,
    entity_id_override: str | None = None,
) -> str | None:
    """Create a DISCOVERED entity if not already known. Returns entity_id or None.

    If entity_id_override is provided, use that exact ID (e.g. from LLM extraction).
    Otherwise generate one from the name.
    """
    import uuid as _uuid

    entity_id = entity_id_override or f"E:{entity_type.lower()}:{_slugify(name)}"
    db_type = _normalize_type(entity_type)

    # Check if this entity_id already exists
    exists = await db.fetchval(
        "SELECT 1 FROM entities WHERE entity_id = $1", entity_id
    )
    if exists:
        # Bump mention count
        await db.execute(
            "UPDATE entities SET mention_count = mention_count + 1, updated_at = now() WHERE entity_id = $1",
            entity_id,
        )
        return entity_id

    # Also check by name match (might exist under a different ID)
    existing = await db.fetchval(
        "SELECT entity_id FROM entities WHERE canonical_name ILIKE $1",
        name,
    )
    if existing:
        await db.execute(
            "UPDATE entities SET mention_count = mention_count + 1, updated_at = now() WHERE entity_id = $1",
            existing,
        )
        return existing

    # Create new DISCOVERED entity
    await db.execute(
        """INSERT INTO entities (entity_id, canonical_name, type, aliases, roles, layers,
                                 status, mention_count, discovered_from_item)
           VALUES ($1, $2, $3, $4, $5, $6, 'DISCOVERED', 1, $7)
           ON CONFLICT (entity_id) DO UPDATE SET mention_count = entities.mention_count + 1""",
        entity_id,
        name,
        db_type,
        json.dumps({"en": [name]}),
        [role_hint] if role_hint else [],
        [layer_hint] if layer_hint else [],
        _uuid.UUID(item_id) if isinstance(item_id, str) else item_id,
    )
    logger.info("DISCOVERED new entity: %s [%s] layer=%s role=%s", name, entity_id, layer_hint, role_hint)
    return entity_id


async def promote_entities() -> int:
    """Check DISCOVERED/PROVISIONAL entities for promotion. Returns count promoted."""
    promoted = 0

    # DISCOVERED -> PROVISIONAL: mention_count >= 3 from >= 2 distinct sources
    rows = await db.fetch(
        """SELECT e.entity_id, e.canonical_name, e.mention_count,
                  COUNT(DISTINCT i.source_id) as source_count
           FROM entities e
           JOIN entity_mentions em ON e.entity_id = em.entity_id
           JOIN items i ON em.item_id = i.id
           WHERE e.status = 'DISCOVERED'
           GROUP BY e.entity_id, e.canonical_name, e.mention_count
           HAVING e.mention_count >= 3 AND COUNT(DISTINCT i.source_id) >= 2"""
    )
    for row in rows:
        await db.execute(
            "UPDATE entities SET status = 'PROVISIONAL', updated_at = now() WHERE entity_id = $1",
            row["entity_id"],
        )
        logger.info("Promoted to PROVISIONAL: %s (%s)", row["entity_id"], row["canonical_name"])
        promoted += 1

    # PROVISIONAL -> CONFIRMED: mention_count >= 6 from >= 3 sources AND has tightening event
    rows = await db.fetch(
        """SELECT e.entity_id, e.canonical_name, e.mention_count,
                  COUNT(DISTINCT i.source_id) as source_count
           FROM entities e
           JOIN entity_mentions em ON e.entity_id = em.entity_id
           JOIN items i ON em.item_id = i.id
           WHERE e.status = 'PROVISIONAL'
           GROUP BY e.entity_id, e.canonical_name, e.mention_count
           HAVING e.mention_count >= 6 AND COUNT(DISTINCT i.source_id) >= 3"""
    )
    for row in rows:
        # Check for tightening event involvement
        has_tightening = await db.fetchval(
            """SELECT 1 FROM events
               WHERE direction = 'TIGHTENING'
                 AND entities::text ILIKE $1
               LIMIT 1""",
            f"%{row['entity_id']}%",
        )
        if has_tightening:
            await db.execute(
                "UPDATE entities SET status = 'CONFIRMED', updated_at = now() WHERE entity_id = $1",
                row["entity_id"],
            )
            logger.info(
                "Promoted to CONFIRMED: %s (%s)", row["entity_id"], row["canonical_name"]
            )
            promoted += 1

    if promoted:
        await load_alias_index()
    return promoted
