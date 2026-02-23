from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta

from src import db

logger = logging.getLogger(__name__)

# Tightening score weights from spec section 7.2
WEIGHTS = {
    "velocity": 0.35,
    "breadth": 0.20,
    "quality": 0.20,
    "allocation": 0.15,
    "novelty": 0.10,
}


async def compute_theme_scores(theme_id: str, events: list[dict]) -> dict:
    """Compute tightening score components for a theme. Returns dict of scores."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    # --- Velocity: tightening events per week (rolling) ---
    recent_tightening = sum(
        1 for e in events
        if e["direction"] == "TIGHTENING"
        and e["created_at"] and e["created_at"] > week_ago
    )
    # Normalize: 10+ events/week = 1.0
    velocity = min(recent_tightening / 10.0, 1.0)

    # --- Breadth: unique suppliers + buyers + geos ---
    entity_set = set()
    for ev in events:
        ents = ev["entities"]
        if isinstance(ents, str):
            ents = json.loads(ents)
        for ent in ents:
            if isinstance(ent, dict):
                entity_set.add(ent.get("entity_id", ""))
    source_set = {ev.get("source_id", "") for ev in events}
    # Normalize: 10+ unique entities or 5+ sources = 1.0
    breadth = min((len(entity_set) / 10.0 + len(source_set) / 5.0) / 2.0, 1.0)

    # --- Source quality: weighted by source tier + reliability ---
    quality_sum = 0.0
    for ev in events:
        evidence = ev.get("evidence", {})
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence)
            except json.JSONDecodeError:
                evidence = {}
        tier = evidence.get("source_tier", 3) if isinstance(evidence, dict) else 3
        # Tier 1 = 1.0, Tier 2 = 0.6, Tier 3 = 0.3
        tier_weight = {1: 1.0, 2: 0.6, 3: 0.3}.get(tier, 0.3)
        quality_sum += tier_weight
    quality = min(quality_sum / max(len(events), 1) if events else 0.0, 1.0)

    # --- Allocation language index: count of allocation/lead-time events ---
    allocation_types = {"ALLOCATION", "LEAD_TIME_EXTENDED"}
    alloc_count = sum(1 for e in events if e["event_type"] in allocation_types)
    allocation = min(alloc_count / 5.0, 1.0)

    # --- Novelty: new objects/entities not seen before this theme ---
    # Check how many entities appeared for the first time recently
    novel_count = 0
    for ev in events:
        if ev["created_at"] and ev["created_at"] > two_weeks_ago:
            ents = ev["entities"]
            if isinstance(ents, str):
                ents = json.loads(ents)
            for ent in ents:
                if isinstance(ent, dict):
                    eid = ent.get("entity_id", "")
                    # Check if entity was first mentioned recently
                    first_mention = await db.fetchval(
                        "SELECT MIN(created_at) FROM entity_mentions WHERE entity_id = $1", eid
                    )
                    if first_mention and first_mention > two_weeks_ago:
                        novel_count += 1
    novelty = min(novel_count / 3.0, 1.0)

    # --- Composite tightening score ---
    tightening_score = (
        WEIGHTS["velocity"] * velocity
        + WEIGHTS["breadth"] * breadth
        + WEIGHTS["quality"] * quality
        + WEIGHTS["allocation"] * allocation
        + WEIGHTS["novelty"] * novelty
    )

    return {
        "tightening_score": round(tightening_score, 3),
        "velocity": round(velocity, 3),
        "breadth": round(breadth, 3),
        "quality": round(quality, 3),
        "allocation": round(allocation, 3),
        "novelty": round(novelty, 3),
    }
