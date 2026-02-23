from __future__ import annotations

import logging

import httpx

from src.settings import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org/bot"


async def send_telegram_message(text: str, parse_mode: str = "HTML") -> str | None:
    """Send a message via Telegram Bot API. Returns message_id or None."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("Telegram not configured, skipping message")
        return None

    url = f"{API_BASE}{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if data.get("ok"):
                msg_id = str(data["result"]["message_id"])
                logger.info("Telegram message sent: %s", msg_id)
                return msg_id
            else:
                logger.error("Telegram API error: %s", data.get("description"))
                return None
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)
            return None


def format_new_candidate(theme: dict) -> str:
    """Format NEW_CANDIDATE alert message."""
    thesis = theme.get("thesis", {})
    if isinstance(thesis, str):
        import json
        try:
            thesis = json.loads(thesis)
        except Exception:
            thesis = {}

    one_liner = thesis.get("one_liner", theme.get("name", "Unknown"))
    layer = theme.get("constraint_layer", "?")
    score = theme.get("tightening_score", 0)

    lines = [
        f"🟡 <b>New constraint candidate: {theme.get('name', '?')}</b>",
        "",
        f"<b>What:</b> {one_liner}",
        f"<b>Layer:</b> {layer} | <b>Score:</b> {score:.2f}",
        f"<b>Events:</b> {theme.get('event_count', 0)} ({theme.get('tightening_count', 0)} tightening)",
    ]

    # Add beneficiaries
    benefits = thesis.get("who_benefits", {})
    ring_a = benefits.get("ringA", [])
    ring_b = benefits.get("ringB", [])
    if ring_a or ring_b:
        tickers = ", ".join(ring_a[:3] + ring_b[:2])
        lines.append(f"<b>Potential winners:</b> {tickers}")

    # Add invalidation
    triggers = thesis.get("invalidation_triggers", [])
    if triggers:
        lines.append(f"<b>Disconfirm:</b> {triggers[0]}")

    return "\n".join(lines)


def format_inflection(theme: dict, event: dict) -> str:
    """Format INFLECTION alert message."""
    lines = [
        f"🟥 <b>INFLECTION: {theme.get('name', '?')}</b>",
        "",
        f"<b>Change:</b> {event.get('event_type', '?')} — {event.get('direction', '?')}",
    ]

    # Add magnitude details
    magnitude = event.get("magnitude", {})
    if isinstance(magnitude, str):
        import json
        try:
            magnitude = json.loads(magnitude)
        except Exception:
            magnitude = {}
    if isinstance(magnitude, dict):
        for k, v in magnitude.items():
            if v is not None:
                lines.append(f"<b>{k}:</b> {v}")

    thesis = theme.get("thesis", {})
    if isinstance(thesis, str):
        import json
        try:
            thesis = json.loads(thesis)
        except Exception:
            thesis = {}

    relief = thesis.get("relief_timeline")
    if relief:
        lines.append(f"<b>Relief timeline:</b> {relief}")

    indicators = thesis.get("leading_indicators", [])
    if indicators:
        lines.append(f"<b>Next indicator:</b> {indicators[0]}")

    return "\n".join(lines)


def format_actionable_briefing(theme: dict) -> str:
    """Format ACTIONABLE_BRIEFING alert message."""
    thesis = theme.get("thesis", {})
    if isinstance(thesis, str):
        import json
        try:
            thesis = json.loads(thesis)
        except Exception:
            thesis = {}

    lines = [
        f"🟢 <b>Briefing: {theme.get('name', '?')} crossed threshold</b>",
        "",
        f"<b>Thesis:</b> {thesis.get('one_liner', '?')}",
        f"<b>Score:</b> {theme.get('tightening_score', 0):.2f} | "
        f"<b>Events:</b> {theme.get('event_count', 0)}",
        "",
    ]

    # Why now
    why_now = thesis.get("why_now", [])
    if why_now:
        lines.append("<b>Why now:</b>")
        for bullet in why_now[:3]:
            lines.append(f"  • {bullet}")

    # Beneficiaries
    benefits = thesis.get("who_benefits", {})
    for ring, entities in benefits.items():
        if entities:
            lines.append(f"<b>{ring}:</b> {', '.join(entities[:5])}")

    # Invalidation
    triggers = thesis.get("invalidation_triggers", [])
    if triggers:
        lines.append("")
        lines.append("<b>Invalidation triggers:</b>")
        for t in triggers[:3]:
            lines.append(f"  • {t}")

    # Leading indicators
    indicators = thesis.get("leading_indicators", [])
    if indicators:
        lines.append("")
        lines.append("<b>Watch next:</b>")
        for ind in indicators[:3]:
            lines.append(f"  • {ind}")

    return "\n".join(lines)
