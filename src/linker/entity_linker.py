from __future__ import annotations

import json
import logging
import re

from src import db

logger = logging.getLogger(__name__)

# In-memory alias index: alias_lower -> entity_id
_alias_index: dict[str, str] = {}
_loaded = False


async def load_alias_index() -> None:
    """Build alias index from all entities in DB."""
    global _alias_index, _loaded
    rows = await db.fetch("SELECT entity_id, canonical_name, aliases FROM entities")

    index: dict[str, str] = {}
    for row in rows:
        eid = row["entity_id"]
        # Index canonical name
        index[row["canonical_name"].lower()] = eid

        # Index all aliases across languages
        aliases = row["aliases"]
        if isinstance(aliases, str):
            aliases = json.loads(aliases)
        for lang, alias_list in aliases.items():
            for alias in alias_list:
                index[alias.lower()] = eid
                # For CJK, also index without spaces
                stripped = alias.replace(" ", "")
                if stripped != alias:
                    index[stripped.lower()] = eid

    _alias_index = index
    _loaded = True
    logger.info("Alias index loaded: %d entries", len(index))


async def _ensure_loaded():
    if not _loaded:
        await load_alias_index()


async def link_entities_in_text(
    text: str,
    item_id: str,
) -> list[dict]:
    """Find entity mentions in text using substring matching. Returns list of matches."""
    await _ensure_loaded()

    if not text:
        return []

    text_lower = text.lower()
    matches: list[dict] = []
    seen_entities: set[str] = set()

    # Sort aliases by length (longest first) to prefer specific matches
    sorted_aliases = sorted(_alias_index.items(), key=lambda x: len(x[0]), reverse=True)

    for alias, entity_id in sorted_aliases:
        if entity_id in seen_entities:
            continue
        if len(alias) < 2:
            continue

        # For Latin text, use word boundary matching
        if alias.isascii():
            pattern = r"\b" + re.escape(alias) + r"\b"
            match = re.search(pattern, text_lower)
        else:
            # For CJK text, use simple substring matching
            match = alias in text_lower

        if match:
            # Extract context snippet
            if isinstance(match, re.Match):
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                snippet = text[start:end]
            else:
                idx = text_lower.find(alias)
                start = max(0, idx - 50)
                end = min(len(text), idx + len(alias) + 50)
                snippet = text[start:end]

            matches.append({
                "entity_id": entity_id,
                "context_snippet": snippet.strip(),
            })
            seen_entities.add(entity_id)

    return matches


async def store_entity_mentions(
    item_id: str,
    matches: list[dict],
    layer_hint: str | None = None,
) -> None:
    """Store entity mentions in DB and increment mention counts."""
    import uuid as _uuid

    for m in matches:
        await db.execute(
            """INSERT INTO entity_mentions (entity_id, item_id, context_snippet, layer_hint)
               VALUES ($1, $2, $3, $4)""",
            m["entity_id"],
            _uuid.UUID(item_id) if isinstance(item_id, str) else item_id,
            m.get("context_snippet"),
            layer_hint,
        )
        await db.execute(
            "UPDATE entities SET mention_count = mention_count + 1, updated_at = now() WHERE entity_id = $1",
            m["entity_id"],
        )
