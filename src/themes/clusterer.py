from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone

from src import db
from src.themes.scorer import compute_theme_scores
from src.themes.thesis_writer import generate_thesis

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60]


def _extract_object_names(objects_json: str | list) -> set[str]:
    """Extract normalized object names from events.objects JSONB."""
    if isinstance(objects_json, str):
        try:
            objects_json = json.loads(objects_json)
        except json.JSONDecodeError:
            return set()
    names = set()
    for obj in objects_json:
        if isinstance(obj, dict):
            name = obj.get("name", "").lower().strip()
            if name:
                names.add(name)
    return names


async def cluster_events() -> dict[str, list[dict]]:
    """Group recent events by (constraint_layer + shared objects). Returns clusters."""
    # Get events from the last 30 days that aren't already in a theme
    rows = await db.fetch(
        """SELECT e.id, e.item_id, e.event_type, e.constraint_layer, e.direction,
                  e.entities, e.objects, e.magnitude, e.timing, e.evidence,
                  e.tags, e.confidence, e.created_at,
                  i.source_id
           FROM events e
           JOIN items i ON e.item_id = i.id
           WHERE e.created_at > now() - interval '30 days'
           ORDER BY e.created_at DESC"""
    )

    # Group by constraint_layer
    by_layer: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        event = dict(row)
        by_layer[event["constraint_layer"]].append(event)

    # Within each layer, sub-cluster by shared objects
    clusters: dict[str, list[dict]] = {}
    for layer, events in by_layer.items():
        # Build object -> events mapping
        obj_events: dict[str, list[dict]] = defaultdict(list)
        for ev in events:
            obj_names = _extract_object_names(ev["objects"])
            if obj_names:
                # Use first object as primary cluster key
                for name in obj_names:
                    obj_events[name].append(ev)
            else:
                # Events without objects go to a general cluster
                obj_events["_general"].append(ev)

        # Merge clusters that share events (transitive closure)
        for obj_name, evts in obj_events.items():
            cluster_key = f"{layer}:{obj_name}"
            if cluster_key not in clusters:
                clusters[cluster_key] = []
            # Dedup by event id
            existing_ids = {e["id"] for e in clusters[cluster_key]}
            for ev in evts:
                if ev["id"] not in existing_ids:
                    clusters[cluster_key].append(ev)
                    existing_ids.add(ev["id"])

    # Filter out tiny clusters
    return {k: v for k, v in clusters.items() if len(v) >= 2}


async def upsert_theme(cluster_key: str, events: list[dict]) -> str | None:
    """Create or update a theme from a cluster of events."""
    parts = cluster_key.split(":", 1)
    layer = parts[0]
    obj_hint = parts[1] if len(parts) > 1 else "general"

    theme_id = f"T:ai_constraints:{_slugify(cluster_key)}"
    name = f"{layer}: {obj_hint}".replace("_", " ").title()

    # Check if theme exists
    existing = await db.fetchrow(
        "SELECT id, theme_id, event_count FROM themes WHERE theme_id = $1", theme_id
    )

    if not existing:
        await db.execute(
            """INSERT INTO themes (theme_id, name, constraint_layer, status,
                                    event_count, first_seen_at)
               VALUES ($1, $2, $3, 'CANDIDATE', $4, now())""",
            theme_id, name, layer, len(events),
        )
        logger.info("New theme CANDIDATE: %s (%d events)", name, len(events))

    # Link events to theme
    for ev in events:
        await db.execute(
            """INSERT INTO theme_events (theme_id, event_id)
               VALUES ($1, $2)
               ON CONFLICT (theme_id, event_id) DO NOTHING""",
            theme_id, ev["id"],
        )

    # Compute scores
    scores = await compute_theme_scores(theme_id, events)

    # Count stats
    tightening_count = sum(1 for e in events if e["direction"] == "TIGHTENING")
    easing_count = sum(1 for e in events if e["direction"] == "EASING")
    unique_entities_set = set()
    for ev in events:
        ents = ev["entities"]
        if isinstance(ents, str):
            ents = json.loads(ents)
        for ent in ents:
            if isinstance(ent, dict):
                unique_entities_set.add(ent.get("entity_id", ""))
    unique_sources = len({ev["source_id"] for ev in events})

    await db.execute(
        """UPDATE themes SET
            tightening_score = $2, velocity_score = $3, breadth_score = $4,
            quality_score = $5, allocation_score = $6, novelty_score = $7,
            event_count = $8, tightening_count = $9, easing_count = $10,
            unique_entities = $11, unique_sources = $12, updated_at = now()
           WHERE theme_id = $1""",
        theme_id,
        scores["tightening_score"],
        scores["velocity"],
        scores["breadth"],
        scores["quality"],
        scores["allocation"],
        scores["novelty"],
        len(events),
        tightening_count,
        easing_count,
        len(unique_entities_set),
        unique_sources,
    )

    # Check promotion rules
    await check_promotion(theme_id, events, scores)

    return theme_id


async def check_promotion(theme_id: str, events: list[dict], scores: dict) -> None:
    """Check and apply theme status promotion rules."""
    theme = await db.fetchrow(
        "SELECT status, first_seen_at, tightening_count, unique_entities, unique_sources FROM themes WHERE theme_id = $1",
        theme_id,
    )
    if not theme:
        return

    status = theme["status"]
    now = datetime.now(timezone.utc)
    age_days = (now - theme["first_seen_at"]).days if theme["first_seen_at"] else 0

    if status == "CANDIDATE":
        # CANDIDATE -> ACTIVE: 14 days, 6+ tightening events, 4+ entities, 2+ tier1/2 sources
        if (
            age_days >= 14
            and theme["tightening_count"] >= 6
            and theme["unique_entities"] >= 4
            and theme["unique_sources"] >= 2
        ):
            await db.execute(
                "UPDATE themes SET status = 'ACTIVE', updated_at = now() WHERE theme_id = $1",
                theme_id,
            )
            logger.info("Theme promoted to ACTIVE: %s", theme_id)

    elif status == "ACTIVE":
        # ACTIVE -> MATURE: score plateauing (check if recent events are mostly easing)
        if theme["easing_count"] > theme["tightening_count"] * 0.5:
            await db.execute(
                "UPDATE themes SET status = 'MATURE', updated_at = now() WHERE theme_id = $1",
                theme_id,
            )

    elif status == "MATURE":
        # MATURE -> FADING: easing dominates
        if theme["easing_count"] > theme["tightening_count"]:
            await db.execute(
                "UPDATE themes SET status = 'FADING', updated_at = now() WHERE theme_id = $1",
                theme_id,
            )


async def run_theme_cycle() -> None:
    """Full theme cycle: cluster -> score -> promote -> write thesis."""
    clusters = await cluster_events()
    if not clusters:
        return

    logger.info("Theme cycle: %d clusters found", len(clusters))

    for key, events in clusters.items():
        theme_id = await upsert_theme(key, events)
        if theme_id:
            # Generate/update thesis for active+ themes
            theme = await db.fetchrow(
                "SELECT status FROM themes WHERE theme_id = $1", theme_id
            )
            if theme and theme["status"] in ("ACTIVE", "MATURE"):
                try:
                    thesis = await generate_thesis(theme_id, events)
                    if thesis:
                        await db.execute(
                            "UPDATE themes SET thesis = $2, updated_at = now() WHERE theme_id = $1",
                            theme_id, json.dumps(thesis),
                        )
                except Exception:
                    logger.exception("Thesis generation failed for %s", theme_id)
