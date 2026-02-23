from __future__ import annotations

import json
import logging
import uuid

from src import db
from src.llm import llm_extract
from src.models import ConstraintEvent, ExtractionResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AI supply chain constraint analyst. Your job is to extract structured constraint events from articles about semiconductor, datacenter, and AI infrastructure supply chains.

For each article, extract 0 or more ConstraintEvent objects. Only extract events that describe REAL supply chain constraints — shortages, allocation, lead time changes, capacity expansions, disruptions, yield issues, price changes, or policy restrictions.

DO NOT extract:
- Generic product launch news without supply chain impact
- Opinion pieces without concrete facts
- Hype narratives not anchored in measurable constraints

Each event must have:
- event_type: one of LEAD_TIME_EXTENDED, ALLOCATION, PRICE_INCREASE, CAPEX_ANNOUNCED, CAPACITY_ONLINE, QUALIFICATION_DELAY, YIELD_ISSUE, DISRUPTION, POLICY_RESTRICTION
- constraint_layer: one of COMPUTE_SILICON, MEMORY, ADV_PACKAGING, SUBSTRATES_FILMS, PCB_MATERIALS, INTERCONNECT_NETWORKING, POWER_DELIVERY_EQUIP, THERMAL_COOLING, DATACENTER_BUILD_PERMIT, FUEL_ONSITE_POWER
- direction: TIGHTENING, EASING, or MIXED
- entities: list of {entity_id, role} where entity_id is like "E:company:tsmc" and role is SUPPLIER/BUYER/DEMAND_DRIVER/OEM/REGULATOR/LOCATION
  IMPORTANT: Include companies that are KNOWN key suppliers even if not named in the article. Use this reference:
    Glass fiber / glass cloth / T-glass / low-CTE glass → Nittobo (E:company:nittobo), Nitto Boseki
    ABF substrate film → Ajinomoto (E:company:ajinomoto), Ajinomoto Fine-Techno
    IC package substrates → Ibiden (E:company:ibiden), Shinko Electric (E:company:shinko)
    Advanced packaging / CoWoS → TSMC (E:company:tsmc), Amkor (E:company:amkor)
    HBM → SK Hynix (E:company:skhynix), Samsung (E:company:samsung_semi), Micron (E:company:micron)
    SiC substrates → Wolfspeed, ON Semi, STMicro, Rohm
    EUV lithography → ASML (E:company:asml)
    Wafer fab equipment → Applied Materials, Lam Research, Tokyo Electron
    GPU / AI accelerators → NVIDIA (E:company:nvidia), AMD (E:company:amd)
    Power transformers → Siemens Energy (E:company:siemens_energy), GE Vernova (E:company:ge_vernova), Hitachi Energy
    Datacenter cooling → Vertiv, Schneider Electric
- objects: list of {type, name, aliases} where type is PRODUCT/COMPONENT/MATERIAL/PROCESS_TECH
- magnitude: concrete numbers when available (lead_time_weeks with from/to, price_change_pct, capex_usd, capacity_delta)
- timing: happened_at (YYYY-MM-DD), reported_at, expected_relief_window
- tags: relevant keywords
- confidence: 0.0-1.0

Pull NUMBERS whenever present. Separate happened_at vs reported_at. Classify direction carefully.

If the article has NO relevant constraint events, return {"events": [], "skipped": true, "skip_reason": "reason"}.

Return valid JSON matching this schema:
{
  "events": [ConstraintEvent, ...],
  "skipped": false,
  "skip_reason": null
}"""


async def extract_events(item_id: str, text: str, source: dict) -> ExtractionResult:
    """Run LLM extraction on article text. Returns ExtractionResult."""
    if not text or len(text.strip()) < 50:
        return ExtractionResult(skipped=True, skip_reason="text_too_short")

    # Truncate very long articles
    truncated = text[:12000] if len(text) > 12000 else text

    user_prompt = f"""Source: {source.get('name', 'unknown')} (tier {source.get('tier', 2)}, {source.get('language', 'en')})
URL: {source.get('url', '')}

Article text:
{truncated}

Extract constraint events as JSON."""

    try:
        raw = await llm_extract(
            user_prompt,
            system=SYSTEM_PROMPT,
            json_mode=True,
        )
    except Exception as exc:
        logger.error("LLM extraction failed for item %s: %s", item_id, exc)
        return ExtractionResult(skipped=True, skip_reason=f"llm_error: {exc}")

    # Parse and validate
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON from LLM for item %s", item_id)
        return ExtractionResult(skipped=True, skip_reason="invalid_json", raw_llm_response=raw)

    result = ExtractionResult(raw_llm_response=raw)

    if data.get("skipped"):
        result.skipped = True
        result.skip_reason = data.get("skip_reason", "llm_skipped")
        return result

    # Validate each event
    raw_events = data.get("events", [])
    for raw_event in raw_events:
        try:
            event = ConstraintEvent.model_validate(raw_event)
            # Attach evidence
            event.evidence = {
                "source_id": source.get("source_id", ""),
                "source_url": source.get("url", ""),
                "source_tier": source.get("tier", 2),
                "language": source.get("language", "en"),
                "confidence": event.confidence,
                "snippets": raw_event.get("evidence", {}).get("snippets", []),
            }
            result.events.append(event)
        except Exception as exc:
            logger.debug("Skipping invalid event in item %s: %s", item_id, exc)

    return result


async def extract_and_store(item_id: str) -> int:
    """Full extraction pipeline for a single item. Returns count of events stored."""
    row = await db.fetchrow(
        """SELECT i.id, i.raw_text, i.text_en, i.url,
                  s.source_id, s.name, s.url as source_url, s.tier, s.language as source_lang,
                  s.reliability, s.earliness
           FROM items i JOIN sources s ON i.source_id = s.source_id
           WHERE i.id = $1""",
        uuid.UUID(item_id) if isinstance(item_id, str) else item_id,
    )
    if not row:
        return 0

    # Prefer translated text, fall back to raw
    text = row["text_en"] or row["raw_text"] or ""
    source = {
        "source_id": row["source_id"],
        "name": row["name"],
        "url": row["source_url"],
        "tier": row["tier"],
        "language": row["source_lang"],
    }

    result = await extract_events(str(row["id"]), text, source)

    if result.skipped or not result.events:
        await db.execute(
            "UPDATE items SET pipeline_status = 'DONE', updated_at = now() WHERE id = $1",
            row["id"],
        )
        return 0

    # Store events
    count = 0
    for event in result.events:
        await db.execute(
            """INSERT INTO events (item_id, event_type, constraint_layer, secondary_layer,
                                   direction, entities, objects, magnitude, timing,
                                   evidence, tags, confidence)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)""",
            row["id"],
            event.event_type.value,
            event.constraint_layer.value,
            event.secondary_layer.value if event.secondary_layer else None,
            event.direction.value,
            json.dumps([e.model_dump() for e in event.entities]),
            json.dumps([o.model_dump() for o in event.objects]),
            json.dumps(event.magnitude.model_dump(exclude_none=True)),
            json.dumps(event.timing.model_dump(exclude_none=True)),
            json.dumps(event.evidence) if isinstance(event.evidence, dict) else "{}",
            event.tags,
            event.confidence,
        )
        count += 1

    await db.execute(
        "UPDATE items SET pipeline_status = 'DONE', updated_at = now() WHERE id = $1",
        row["id"],
    )
    return count
