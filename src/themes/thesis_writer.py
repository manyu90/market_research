from __future__ import annotations

import json
import logging

from src.llm import llm_extract

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AI supply chain constraint analyst. Generate a structured thesis for a bottleneck theme based on the evidence events provided.

Your thesis must answer:
1. What is scarce and why it matters NOW
2. The causal mechanism (demand driver -> constraint -> impact)
3. Who benefits (Ring A = pure plays, Ring B = adjacent winners, Ring C = expression vehicles)
4. Who suffers
5. What leading indicators to watch
6. What would invalidate this thesis
7. Expected relief timeline

Return JSON matching this exact schema:
{
  "one_liner": "Single sentence thesis",
  "why_now": ["bullet 1", "bullet 2"],
  "mechanism": ["causal chain step 1", "step 2"],
  "who_benefits": {"ringA": ["entity1"], "ringB": ["entity2"], "ringC": ["ETF1"]},
  "who_suffers": ["entity or class"],
  "leading_indicators": ["indicator 1", "indicator 2"],
  "invalidation_triggers": ["trigger 1", "trigger 2"],
  "relief_timeline": "e.g. 2027-H2 when new capacity comes online"
}

Be specific. Use entity names. Reference concrete numbers from the evidence."""


async def generate_thesis(theme_id: str, events: list[dict]) -> dict | None:
    """Generate a living thesis for a theme based on its evidence events."""
    if not events:
        return None

    # Build evidence summary for the LLM
    evidence_lines = []
    for ev in events[:15]:  # limit to most recent 15
        line_parts = [
            f"- [{ev.get('event_type', '?')}]",
            f"layer={ev.get('constraint_layer', '?')}",
            f"dir={ev.get('direction', '?')}",
        ]
        # Add objects
        objects = ev.get("objects", [])
        if isinstance(objects, str):
            try:
                objects = json.loads(objects)
            except json.JSONDecodeError:
                objects = []
        obj_names = [o.get("name", "") for o in objects if isinstance(o, dict)]
        if obj_names:
            line_parts.append(f"objects={', '.join(obj_names)}")

        # Add entities
        entities = ev.get("entities", [])
        if isinstance(entities, str):
            try:
                entities = json.loads(entities)
            except json.JSONDecodeError:
                entities = []
        ent_ids = [e.get("entity_id", "") for e in entities if isinstance(e, dict)]
        if ent_ids:
            line_parts.append(f"entities={', '.join(ent_ids)}")

        # Add magnitude info
        magnitude = ev.get("magnitude", {})
        if isinstance(magnitude, str):
            try:
                magnitude = json.loads(magnitude)
            except json.JSONDecodeError:
                magnitude = {}
        if isinstance(magnitude, dict):
            for k, v in magnitude.items():
                if v is not None:
                    line_parts.append(f"{k}={v}")

        evidence_lines.append(" | ".join(line_parts))

    evidence_text = "\n".join(evidence_lines)

    prompt = f"""Theme: {theme_id}
Layer: {events[0].get('constraint_layer', 'unknown')}
Event count: {len(events)}
Tightening events: {sum(1 for e in events if e.get('direction') == 'TIGHTENING')}
Easing events: {sum(1 for e in events if e.get('direction') == 'EASING')}

Evidence events:
{evidence_text}

Generate a structured thesis for this bottleneck theme."""

    try:
        raw = await llm_extract(prompt, system=SYSTEM_PROMPT, json_mode=True)
        thesis = json.loads(raw)
        return thesis
    except json.JSONDecodeError:
        logger.warning("Invalid JSON from thesis writer for %s", theme_id)
        return None
    except Exception as exc:
        logger.error("Thesis generation failed for %s: %s", theme_id, exc)
        return None
