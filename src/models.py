from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


# ── Enums ────────────────────────────────────────────────────────────────

class ConstraintLayer(str, Enum):
    COMPUTE_SILICON = "COMPUTE_SILICON"
    MEMORY = "MEMORY"
    ADV_PACKAGING = "ADV_PACKAGING"
    SUBSTRATES_FILMS = "SUBSTRATES_FILMS"
    PCB_MATERIALS = "PCB_MATERIALS"
    INTERCONNECT_NETWORKING = "INTERCONNECT_NETWORKING"
    POWER_DELIVERY_EQUIP = "POWER_DELIVERY_EQUIP"
    THERMAL_COOLING = "THERMAL_COOLING"
    DATACENTER_BUILD_PERMIT = "DATACENTER_BUILD_PERMIT"
    FUEL_ONSITE_POWER = "FUEL_ONSITE_POWER"


class EventType(str, Enum):
    LEAD_TIME_EXTENDED = "LEAD_TIME_EXTENDED"
    ALLOCATION = "ALLOCATION"
    PRICE_INCREASE = "PRICE_INCREASE"
    CAPEX_ANNOUNCED = "CAPEX_ANNOUNCED"
    CAPACITY_ONLINE = "CAPACITY_ONLINE"
    QUALIFICATION_DELAY = "QUALIFICATION_DELAY"
    YIELD_ISSUE = "YIELD_ISSUE"
    DISRUPTION = "DISRUPTION"
    POLICY_RESTRICTION = "POLICY_RESTRICTION"


class Direction(str, Enum):
    TIGHTENING = "TIGHTENING"
    EASING = "EASING"
    MIXED = "MIXED"


class EntityRole(str, Enum):
    SUPPLIER = "SUPPLIER"
    BUYER = "BUYER"
    DEMAND_DRIVER = "DEMAND_DRIVER"
    OEM = "OEM"
    REGULATOR = "REGULATOR"
    LOCATION = "LOCATION"


class PipelineStatus(str, Enum):
    COLLECTED = "COLLECTED"
    NORMALIZED = "NORMALIZED"
    LINKED = "LINKED"
    EXTRACTED = "EXTRACTED"
    DONE = "DONE"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class ThemeStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"
    MATURE = "MATURE"
    FADING = "FADING"


class SourceStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    PROVISIONAL = "PROVISIONAL"
    CONFIRMED = "CONFIRMED"
    DISABLED = "DISABLED"


class EntityStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    PROVISIONAL = "PROVISIONAL"
    CONFIRMED = "CONFIRMED"


# ── Models ───────────────────────────────────────────────────────────────

class EntityRef(BaseModel):
    entity_id: str
    role: EntityRole


class ObjectRef(BaseModel):
    type: str
    name: str
    aliases: list[str] = []


class Magnitude(BaseModel):
    lead_time_weeks: dict | None = None
    price_change_pct: float | None = None
    capex_usd: int | None = None
    capacity_delta: str | None = None
    notes: str | None = None


class Timing(BaseModel):
    happened_at: str | None = None
    reported_at: str | None = None
    expected_relief_window: str | None = None


class Evidence(BaseModel):
    source_id: str
    source_url: str
    source_tier: int = 2
    language: str = "en"
    translation_used: bool = False
    confidence: float = 0.5
    snippets: list[str] = []


class ConstraintEvent(BaseModel):
    event_type: EventType
    constraint_layer: ConstraintLayer
    secondary_layer: ConstraintLayer | None = None
    direction: Direction
    entities: list[EntityRef] = []
    objects: list[ObjectRef] = []
    magnitude: Magnitude = Magnitude()
    timing: Timing = Timing()
    evidence: Evidence | None = None
    tags: list[str] = []
    confidence: float = 0.5


class ExtractionResult(BaseModel):
    events: list[ConstraintEvent] = []
    skipped: bool = False
    skip_reason: str | None = None
    raw_llm_response: str | None = None


class ThemeThesis(BaseModel):
    one_liner: str
    why_now: list[str] = []
    mechanism: list[str] = []
    who_benefits: dict[str, list[str]] = {}
    who_suffers: list[str] = []
    leading_indicators: list[str] = []
    invalidation_triggers: list[str] = []
    relief_timeline: str | None = None
