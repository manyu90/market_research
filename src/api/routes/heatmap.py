from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query

from src import db

router = APIRouter()


@router.get("/heatmap")
async def get_heatmap(weeks: int = Query(default=12, ge=1, le=52)):
    """Constraint heatmap: tightening score by layer x week."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(weeks=weeks)

    rows = await db.fetch(
        """SELECT constraint_layer,
                  date_trunc('week', created_at) as week,
                  COUNT(*) as event_count,
                  SUM(CASE WHEN direction = 'TIGHTENING' THEN 1 ELSE 0 END) as tightening,
                  SUM(CASE WHEN direction = 'EASING' THEN 1 ELSE 0 END) as easing
           FROM events
           WHERE created_at >= $1
           GROUP BY constraint_layer, date_trunc('week', created_at)
           ORDER BY constraint_layer, week""",
        start,
    )

    # Build heatmap structure
    heatmap: dict[str, list[dict]] = {}
    for row in rows:
        layer = row["constraint_layer"]
        if layer not in heatmap:
            heatmap[layer] = []
        net = row["tightening"] - row["easing"]
        total = row["event_count"]
        score = min(net / max(total, 1), 1.0) if total > 0 else 0.0
        heatmap[layer].append({
            "week": row["week"].isoformat(),
            "event_count": row["event_count"],
            "tightening": row["tightening"],
            "easing": row["easing"],
            "score": round(score, 2),
        })

    return {"weeks": weeks, "heatmap": heatmap}
