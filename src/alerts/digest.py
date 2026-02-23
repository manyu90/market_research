from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta

from src import db
from src.alerts.telegram import send_telegram_message

logger = logging.getLogger(__name__)


async def build_daily_digest() -> str | None:
    """Build and send the daily digest message. Returns telegram message_id."""
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    # Get new events from last 24h
    event_count = await db.fetchval(
        "SELECT COUNT(*) FROM events WHERE created_at >= $1", yesterday
    ) or 0

    tightening_count = await db.fetchval(
        "SELECT COUNT(*) FROM events WHERE created_at >= $1 AND direction = 'TIGHTENING'",
        yesterday,
    ) or 0

    easing_count = await db.fetchval(
        "SELECT COUNT(*) FROM events WHERE created_at >= $1 AND direction = 'EASING'",
        yesterday,
    ) or 0

    # Get items collected
    items_count = await db.fetchval(
        "SELECT COUNT(*) FROM items WHERE fetched_at >= $1", yesterday
    ) or 0

    # Top active themes by tightening score
    themes = await db.fetch(
        """SELECT name, constraint_layer, status, tightening_score,
                  event_count, tightening_count, easing_count
           FROM themes
           WHERE status IN ('CANDIDATE', 'ACTIVE', 'MATURE')
           ORDER BY tightening_score DESC
           LIMIT 5"""
    )

    # Recent high-impact events
    top_events = await db.fetch(
        """SELECT e.event_type, e.constraint_layer, e.direction,
                  e.objects, e.confidence, e.created_at,
                  s.name as source_name, s.tier
           FROM events e
           JOIN items i ON e.item_id = i.id
           JOIN sources s ON i.source_id = s.source_id
           WHERE e.created_at >= $1
             AND e.direction = 'TIGHTENING'
             AND s.tier <= 2
           ORDER BY e.confidence DESC, e.created_at DESC
           LIMIT 5""",
        yesterday,
    )

    # New entities discovered
    new_entities = await db.fetch(
        """SELECT canonical_name, type, status, layers
           FROM entities
           WHERE created_at >= $1 AND status IN ('DISCOVERED', 'PROVISIONAL')
           ORDER BY created_at DESC
           LIMIT 5""",
        yesterday,
    )

    # Build message
    date_str = now.strftime("%Y-%m-%d")
    lines = [
        f"📊 <b>AI Constraints Radar — Daily Digest ({date_str})</b>",
        "",
        f"<b>Pipeline:</b> {items_count} articles → {event_count} events "
        f"({tightening_count} tightening, {easing_count} easing)",
        "",
    ]

    # Top themes
    if themes:
        lines.append("<b>Top themes:</b>")
        for t in themes:
            status_icon = {"CANDIDATE": "🟡", "ACTIVE": "🟠", "MATURE": "🔵"}.get(
                t["status"], "⚪"
            )
            lines.append(
                f"  {status_icon} {t['name']} — score {t['tightening_score']:.2f} "
                f"({t['tightening_count']}↑ {t['easing_count']}↓)"
            )
        lines.append("")

    # Top events
    if top_events:
        lines.append("<b>Key events:</b>")
        for ev in top_events:
            objects = ev["objects"]
            if isinstance(objects, str):
                try:
                    objects = json.loads(objects)
                except json.JSONDecodeError:
                    objects = []
            obj_names = [o.get("name", "") for o in objects if isinstance(o, dict)]
            obj_str = ", ".join(obj_names[:2]) if obj_names else ev["constraint_layer"]
            lines.append(
                f"  • [{ev['event_type']}] {obj_str} — {ev['source_name']} (T{ev['tier']})"
            )
        lines.append("")

    # New entities
    if new_entities:
        lines.append("<b>New entities discovered:</b>")
        for ent in new_entities:
            layers = ent["layers"] or []
            layer_str = ", ".join(layers[:2]) if layers else "?"
            lines.append(f"  • {ent['canonical_name']} ({ent['type']}) in {layer_str}")

    if not themes and not top_events:
        lines.append("<i>No significant activity in the last 24 hours.</i>")

    message = "\n".join(lines)

    # Send and store
    msg_id = await send_telegram_message(message)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dedup_key = f"DAILY_DIGEST:none:{today}"
    await db.execute(
        """INSERT INTO alerts (alert_type, payload, telegram_message_id, dedup_key)
           VALUES ('DAILY_DIGEST', $1, $2, $3)
           ON CONFLICT (dedup_key) DO NOTHING""",
        json.dumps({"date": date_str, "event_count": event_count}),
        msg_id,
        dedup_key,
    )

    logger.info("Daily digest sent for %s", date_str)
    return msg_id
