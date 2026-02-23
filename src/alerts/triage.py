from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta

from src import db
from src.alerts.telegram import (
    send_telegram_message,
    format_new_candidate,
    format_inflection,
    format_actionable_briefing,
)
from src.settings import settings

logger = logging.getLogger(__name__)


async def _alert_sent_today(alert_type: str, theme_id: str | None) -> bool:
    """Check if this alert type+theme was already sent today (dedup)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dedup_key = f"{alert_type}:{theme_id or 'none'}:{today}"
    exists = await db.fetchval(
        "SELECT 1 FROM alerts WHERE dedup_key = $1", dedup_key
    )
    return bool(exists)


async def _daily_alert_count() -> int:
    """Count alerts sent today."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return await db.fetchval(
        "SELECT COUNT(*) FROM alerts WHERE sent_at >= $1", today_start
    ) or 0


async def _store_alert(
    alert_type: str,
    theme_id: str | None,
    payload: dict,
    telegram_msg_id: str | None,
) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dedup_key = f"{alert_type}:{theme_id or 'none'}:{today}"
    await db.execute(
        """INSERT INTO alerts (alert_type, theme_id, payload, telegram_message_id, dedup_key)
           VALUES ($1, $2, $3, $4, $5)
           ON CONFLICT (dedup_key) DO NOTHING""",
        alert_type, theme_id, json.dumps(payload), telegram_msg_id, dedup_key,
    )


async def triage_new_candidates() -> int:
    """Check for new CANDIDATE themes that haven't been alerted."""
    sent = 0
    rows = await db.fetch(
        """SELECT theme_id, name, constraint_layer, tightening_score,
                  event_count, tightening_count, thesis
           FROM themes
           WHERE status = 'CANDIDATE'
             AND event_count >= 3
           ORDER BY tightening_score DESC"""
    )

    for row in rows:
        theme = dict(row)
        if await _alert_sent_today("NEW_CANDIDATE", theme["theme_id"]):
            continue
        if await _daily_alert_count() >= settings.max_alerts_per_day:
            break

        msg = format_new_candidate(theme)
        msg_id = await send_telegram_message(msg)
        await _store_alert("NEW_CANDIDATE", theme["theme_id"], theme, msg_id)
        sent += 1

    return sent


async def triage_inflections() -> int:
    """Check for inflection-worthy events in the last cycle."""
    sent = 0
    # Get recent high-impact events from tier 1 sources
    rows = await db.fetch(
        """SELECT e.id, e.event_type, e.constraint_layer, e.direction,
                  e.entities, e.objects, e.magnitude, e.timing, e.evidence,
                  e.confidence, e.created_at
           FROM events e
           JOIN items i ON e.item_id = i.id
           JOIN sources s ON i.source_id = s.source_id
           WHERE e.created_at > now() - interval '30 minutes'
             AND s.tier = 1
             AND e.event_type IN ('ALLOCATION', 'LEAD_TIME_EXTENDED', 'DISRUPTION', 'POLICY_RESTRICTION')
             AND e.direction = 'TIGHTENING'
           ORDER BY e.created_at DESC"""
    )

    for row in rows:
        event = dict(row)
        # Find associated theme
        theme_row = await db.fetchrow(
            """SELECT t.theme_id, t.name, t.constraint_layer, t.tightening_score,
                      t.event_count, t.tightening_count, t.thesis
               FROM themes t
               JOIN theme_events te ON t.theme_id = te.theme_id
               WHERE te.event_id = $1
               ORDER BY t.tightening_score DESC
               LIMIT 1""",
            event["id"],
        )

        if not theme_row:
            continue

        theme = dict(theme_row)
        if await _alert_sent_today("INFLECTION", theme["theme_id"]):
            continue
        if await _daily_alert_count() >= settings.max_alerts_per_day:
            break

        msg = format_inflection(theme, event)
        msg_id = await send_telegram_message(msg)
        await _store_alert("INFLECTION", theme["theme_id"], {**theme, "trigger_event": event}, msg_id)
        sent += 1

    return sent


async def triage_actionable_briefings() -> int:
    """Check for themes that crossed the actionable threshold."""
    sent = 0
    rows = await db.fetch(
        """SELECT theme_id, name, constraint_layer, tightening_score,
                  event_count, tightening_count, unique_sources, thesis
           FROM themes
           WHERE status IN ('ACTIVE', 'MATURE')
             AND tightening_score >= 0.70
             AND unique_sources >= 3
           ORDER BY tightening_score DESC"""
    )

    for row in rows:
        theme = dict(row)
        # Check thesis has required fields
        thesis = theme.get("thesis", {})
        if isinstance(thesis, str):
            try:
                thesis = json.loads(thesis)
            except json.JSONDecodeError:
                continue
        if not thesis.get("invalidation_triggers") or not thesis.get("relief_timeline"):
            continue

        if await _alert_sent_today("ACTIONABLE_BRIEFING", theme["theme_id"]):
            continue
        if await _daily_alert_count() >= settings.max_alerts_per_day:
            break

        msg = format_actionable_briefing(theme)
        msg_id = await send_telegram_message(msg)
        await _store_alert("ACTIONABLE_BRIEFING", theme["theme_id"], theme, msg_id)
        sent += 1

    return sent


async def run_alert_triage() -> None:
    """Run all alert triage checks."""
    candidates = await triage_new_candidates()
    inflections = await triage_inflections()
    briefings = await triage_actionable_briefings()

    total = candidates + inflections + briefings
    if total:
        logger.info(
            "Alert triage: %d new_candidate, %d inflection, %d briefing",
            candidates, inflections, briefings,
        )
