from __future__ import annotations

import json

from fastapi import APIRouter, Query

from src import db

router = APIRouter()


@router.get("/themes")
async def list_themes(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List themes, optionally filtered by status."""
    if status:
        rows = await db.fetch(
            """SELECT theme_id, name, constraint_layer, status, tightening_score,
                      velocity_score, breadth_score, quality_score,
                      event_count, tightening_count, easing_count,
                      unique_entities, unique_sources, thesis,
                      first_seen_at, updated_at
               FROM themes WHERE status = $1
               ORDER BY tightening_score DESC LIMIT $2""",
            status, limit,
        )
    else:
        rows = await db.fetch(
            """SELECT theme_id, name, constraint_layer, status, tightening_score,
                      velocity_score, breadth_score, quality_score,
                      event_count, tightening_count, easing_count,
                      unique_entities, unique_sources, thesis,
                      first_seen_at, updated_at
               FROM themes
               ORDER BY tightening_score DESC LIMIT $1""",
            limit,
        )

    themes = []
    for row in rows:
        t = dict(row)
        if isinstance(t.get("thesis"), str):
            try:
                t["thesis"] = json.loads(t["thesis"])
            except json.JSONDecodeError:
                pass
        themes.append(t)

    return {"themes": themes, "count": len(themes)}


@router.get("/themes/{theme_id:path}")
async def get_theme(theme_id: str):
    """Get a single theme with its events."""
    theme = await db.fetchrow(
        """SELECT theme_id, name, constraint_layer, status, tightening_score,
                  velocity_score, breadth_score, quality_score, allocation_score, novelty_score,
                  event_count, tightening_count, easing_count,
                  unique_entities, unique_sources, thesis,
                  first_seen_at, updated_at
           FROM themes WHERE theme_id = $1""",
        theme_id,
    )
    if not theme:
        return {"error": "Theme not found"}, 404

    t = dict(theme)
    if isinstance(t.get("thesis"), str):
        try:
            t["thesis"] = json.loads(t["thesis"])
        except json.JSONDecodeError:
            pass

    # Get linked events
    events = await db.fetch(
        """SELECT e.id, e.event_type, e.constraint_layer, e.direction,
                  e.entities, e.objects, e.magnitude, e.timing,
                  e.confidence, e.created_at,
                  te.weight
           FROM events e
           JOIN theme_events te ON e.id = te.event_id
           WHERE te.theme_id = $1
           ORDER BY e.created_at DESC""",
        theme_id,
    )

    event_list = []
    for row in events:
        ev = dict(row)
        for field in ("entities", "objects", "magnitude", "timing"):
            if isinstance(ev.get(field), str):
                try:
                    ev[field] = json.loads(ev[field])
                except json.JSONDecodeError:
                    pass
        event_list.append(ev)

    t["events"] = event_list
    return t
