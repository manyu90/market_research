from __future__ import annotations

from fastapi import APIRouter, Query

from src import db

router = APIRouter()


@router.get("/sources")
async def list_sources(
    status: str | None = Query(default=None),
    fetch_method: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    """List sources with optional filters."""
    conditions = []
    params: list = []
    idx = 1

    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if fetch_method:
        conditions.append(f"fetch_method = ${idx}")
        params.append(fetch_method)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    rows = await db.fetch(
        f"""SELECT source_id, name, url, feed_url, fetch_method, language,
                   tier, reliability, earliness, schedule_minutes,
                   layers, status, relevant_article_count,
                   created_at, updated_at
            FROM sources {where}
            ORDER BY tier, name
            LIMIT ${idx}""",
        *params,
    )

    return {"sources": [dict(r) for r in rows], "count": len(rows)}


@router.get("/sources/stats")
async def source_stats():
    """Aggregate source statistics."""
    total = await db.fetchval("SELECT COUNT(*) FROM sources") or 0
    by_status = await db.fetch(
        "SELECT status, COUNT(*) as count FROM sources GROUP BY status"
    )
    by_method = await db.fetch(
        "SELECT fetch_method, COUNT(*) as count FROM sources GROUP BY fetch_method"
    )
    items_total = await db.fetchval("SELECT COUNT(*) FROM items") or 0
    items_by_status = await db.fetch(
        "SELECT pipeline_status, COUNT(*) as count FROM items GROUP BY pipeline_status"
    )

    return {
        "total_sources": total,
        "by_status": {r["status"]: r["count"] for r in by_status},
        "by_method": {r["fetch_method"]: r["count"] for r in by_method},
        "total_items": items_total,
        "items_by_pipeline_status": {r["pipeline_status"]: r["count"] for r in items_by_status},
    }
