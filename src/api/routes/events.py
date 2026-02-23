from __future__ import annotations

import json

from fastapi import APIRouter, Query

from src import db

router = APIRouter()


@router.get("/events")
async def list_events(
    layer: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List events with optional filters."""
    conditions = []
    params: list = []
    idx = 1

    if layer:
        conditions.append(f"e.constraint_layer = ${idx}")
        params.append(layer)
        idx += 1
    if direction:
        conditions.append(f"e.direction = ${idx}")
        params.append(direction)
        idx += 1
    if event_type:
        conditions.append(f"e.event_type = ${idx}")
        params.append(event_type)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    params.extend([limit, offset])

    rows = await db.fetch(
        f"""SELECT e.id, e.event_type, e.constraint_layer, e.secondary_layer,
                   e.direction, e.entities, e.objects, e.magnitude, e.timing,
                   e.evidence, e.tags, e.confidence, e.created_at,
                   i.title, i.url, i.source_id, s.name as source_name, s.tier
            FROM events e
            JOIN items i ON e.item_id = i.id
            JOIN sources s ON i.source_id = s.source_id
            {where}
            ORDER BY e.created_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}""",
        *params,
    )

    events = []
    for row in rows:
        ev = dict(row)
        for field in ("entities", "objects", "magnitude", "timing", "evidence"):
            if isinstance(ev.get(field), str):
                try:
                    ev[field] = json.loads(ev[field])
                except json.JSONDecodeError:
                    pass
        events.append(ev)

    return {"events": events, "count": len(events)}
