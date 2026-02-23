"""Query generator with round-robin rotation.

Loads config/constraint_taxonomy.yml (a flat list of search queries per
language) and serves them via get_next_queries(source_id, count).
A persistent cursor per source ensures full rotation before repeating.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from src.settings import PROJECT_ROOT

logger = logging.getLogger(__name__)

TAXONOMY_PATH = PROJECT_ROOT / "config" / "constraint_taxonomy.yml"
CURSOR_PATH = PROJECT_ROOT / "data" / "query_cursors.json"

# Module-level state — populated by init()
_queries_by_source: dict[str, list[str]] = {}
_cursors: dict[str, int] = {}
_initialized = False


def init() -> None:
    """Load query lists per source. Call once at startup."""
    global _queries_by_source, _cursors, _initialized

    if not TAXONOMY_PATH.exists():
        logger.warning("Taxonomy not found at %s — query generator disabled", TAXONOMY_PATH)
        return

    with open(TAXONOMY_PATH, "r", encoding="utf-8") as f:
        taxonomy = yaml.safe_load(f)

    queries_by_lang: dict[str, list[str]] = taxonomy.get("queries", {})
    source_lang_map: dict[str, list[str]] = taxonomy.get("source_language_map", {})

    for source_id, langs in source_lang_map.items():
        combined: list[str] = []
        for lang in langs:
            combined.extend(queries_by_lang.get(lang, []))
        _queries_by_source[source_id] = combined

    _cursors = _load_cursors()
    _initialized = True

    for sid, qs in _queries_by_source.items():
        logger.info("Query generator: %s → %d queries", sid, len(qs))
    total = sum(len(qs) for qs in _queries_by_source.values())
    logger.info("Query generator: %d total queries across %d sources", total, len(_queries_by_source))


def get_next_queries(source_id: str, count: int = 3) -> list[str]:
    """Return the next `count` queries for a source, advancing the cursor."""
    if not _initialized or source_id not in _queries_by_source:
        return []

    queries = _queries_by_source[source_id]
    if not queries:
        return []

    cursor = _cursors.get(source_id, 0) % len(queries)
    selected: list[str] = []
    for i in range(count):
        idx = (cursor + i) % len(queries)
        selected.append(queries[idx])

    _cursors[source_id] = (cursor + count) % len(queries)
    _save_cursors()

    return selected


def get_query_count(source_id: str) -> int:
    """Return total number of queries available for a source."""
    return len(_queries_by_source.get(source_id, []))


def _load_cursors() -> dict[str, int]:
    if CURSOR_PATH.exists():
        try:
            with open(CURSOR_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not load cursor file, starting fresh")
    return {}


def _save_cursors() -> None:
    CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(CURSOR_PATH, "w") as f:
            json.dump(_cursors, f, indent=2)
    except OSError:
        logger.warning("Could not save cursor file")
