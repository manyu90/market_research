# Radar 1 — AI Constraints (Constraint Hunter) — **Global‑First Implementation Spec**

> **Context for Codex / AI coding agent (read first):**  
> Implement a production‑ready “AI Constraints” radar: a 24/7 system that ingests **global, multi‑language** sources, extracts structured **constraint events**, clusters them into **themes (bottlenecks)**, maintains a **living thesis** per theme, computes **tightening indicators**, and emits **high‑signal alerts + daily digests**.  
> Optimize for **auditability**, **low noise**, and **causal supply‑chain structure**. Avoid “LLM vibes.”  
> This doc is the canonical build spec.

---

## 0) Mission, outputs, and success criteria

### 0.1 Mission
Detect **emerging bottlenecks** that throttle AI scaling **before they become consensus**, track how they evolve, and continuously answer:
- **What is scarce? Why now?**
- **Who benefits / who gets hurt?**
- **What would disconfirm / resolve this?**
- **What to watch next (leading indicators + relief timeline)?**

### 0.2 MVP Outputs (must ship)
1) **Event stream (append‑only):** every relevant item becomes a normalized `ConstraintEvent` (strict JSON).
2) **Daily digest (1 message/day):** top events, what changed, new bottleneck candidates, top active themes.
3) **Weekly heatmap:** tightening score by constraint layer + top themes.
4) **Living thesis per theme:** a short always‑up‑to‑date doc with evidence links + invalidation triggers.

### 0.3 Success criteria (how we know this creates edge)
- **Lead time advantage:** theme detected days/weeks before mainstream consensus (tracked vs “first mainstream pickup”).
- **Correct beneficiary mapping:** ring‑A/ring‑B winners match subsequent relative outperformance more often than chance.
- **Low false positives:** themes promoted to ACTIVE rarely die immediately without disconfirmers.
- **Auditability:** every alert can be traced to specific events + sources + scores.

---

## 1) Radar boundaries: what counts as “AI constraints”

### 1.1 In scope (IN)
Anything that can throttle AI scaling due to **physical, industrial, operational, or financing constraints**, including:
- component/material shortages
- lead‑time extensions
- allocation / “fully booked” language
- yield/qualification delays
- capex expansions (and their relief timelines)
- disruptions (fires, contamination, outages)
- permitting/interconnection bottlenecks
- power/cooling bottlenecks
- export/policy restrictions **only when directly causal to supply constraints**

### 1.2 Out of scope (OUT)
- generic AI product launch news without supply‑chain causality
- opinion pieces without concrete events
- hype narratives not anchored in measurable constraints

**Key rule:** This radar is not “AI news.” It is **AI supply chain stress**.

---

## 2) Global‑first approach (non‑negotiable)

### 2.1 Geography
Treat **East Asia** (Japan/Korea/Taiwan/China/SE Asia) as first‑class:
- many bottlenecks originate upstream in Asia (memory, substrates, glass, PCB materials, packaging, optics supply chains)
- the earliest signals appear in local trade press and company disclosures

### 2.2 Language
Must support multi‑language ingestion and normalization:
- Detect language → translate to English (store both original + translated)
- Preserve numbers/units/dates; normalize currencies and measurement units
- Canonicalize entities across languages (aliases)

**Store:** `raw_text_original`, `raw_text_en`, `language`, `translation_confidence`.

---

## 3) World model (ontology) — the backbone

### 3.1 Canonical constraint layers (10)
Bottlenecks migrate across layers; track each explicitly:

1) `COMPUTE_SILICON`  
2) `MEMORY` (HBM/DRAM stacks, yields, allocation)  
3) `ADV_PACKAGING` (2.5D/3D packaging capacity, interposers, bumping)  
4) `SUBSTRATES_FILMS` (ABF ecosystem, advanced substrates capacity)  
5) `PCB_MATERIALS` (glass cloth / low‑CTE glass, copper foil, resins, laminates)  
6) `INTERCONNECT_NETWORKING` (switches, optics, transceivers, cables)  
7) `POWER_DELIVERY_EQUIP` (transformers, switchgear, breakers, PDUs)  
8) `THERMAL_COOLING` (liquid cooling loops, chillers, heat exchangers)  
9) `DATACENTER_BUILD_PERMIT` (EPC bottlenecks, permitting, grid interconnect queues)  
10) `FUEL_ONSITE_POWER` (gas turbines, gensets, microgrids, off‑grid builds)

Each event MUST map to exactly one primary layer (optional secondary layer).

### 3.2 Entity types (canonical)
- `COMPANY` (public/private)
- `FACILITY` (fab/plant/refinery/site)
- `PRODUCT` (HBM4, 800G optics, etc.)
- `COMPONENT` (substrate, interposer, transceiver)
- `MATERIAL` (ABF film, low‑CTE glass cloth, copper foil)
- `PROCESS_TECH` (CoWoS, 2.5D, advanced substrate classes)
- `BUYER_CLASS` (hyperscaler, GPU vendor, OEM, telco)
- `GEO` (country/region)
- `POLICY_PROGRAM` (subsidy/export restriction, only if causal)

### 3.3 Relationship graph (must exist in data model)
Represent a causal chain:
`DEMAND_DRIVER` → `CONSTRAINT_LAYER` → `OBJECT` → `SUPPLIER` → `CAPACITY/LEAD_TIME` → `CAPEX` → `RELIEF_TIMELINE`

This graph is what turns “news” into “actionable structure.”

---

## 4) Source strategy (global, tiered, scored)

### 4.1 Source tiers
- **Tier 1 (earliest + highest signal):**
  - supplier earnings transcripts (allocation/lead times/yields/capacity)
  - supplier PR (expansions, new lines, qualification milestones)
  - niche trade publications (packaging/PCB/optics/power equipment)
  - industrial ministry / regulator bulletins in Asia (Japan/Korea/Taiwan)
- **Tier 2 (confirmation / broader):**
  - reputable wires and financial press
- **Tier 3 (discovery only):**
  - curated social (X), Substack — never sole basis for major alerts

### 4.2 Source scoring rubric
Each source has:
- `reliability ∈ [0,1]` (primary docs > trade press > mainstream > social)
- `earliness ∈ [0,1]` (how often it surfaces constraints early)
- `bias_notes` (optional)

### 4.3 Acceptance policy for high‑severity alerts
For `INFLECTION` and `ACTIONABLE_BRIEFING` alerts:
- Require either **Tier 1** source, or **cross‑confirmation** from ≥2 independent sources.
- Social-only evidence can create a `CANDIDATE`, not an `ACTIVE` theme.

### 4.4 Source discovery (the system finds its own sources)

The seed source file (`config/seed_sources.yml`) bootstraps the collector with ~28 known
publications. But the best sources for the NEXT bottleneck may not be in any predefined list.

**Three discovery channels run continuously:**

**(A) Web search sweeps**
- Periodically run keyword searches via news search APIs (Google News, Bing News, Brave Search)
- Queries built from: constraint layer keywords × object names × constraint phrases
  - e.g., `"glass cloth" shortage semiconductor`, `"ABF film" allocation lead time`
  - e.g., `ガラスクロス 供給不足` (Japanese: glass cloth supply shortage)
- Results from domains NOT in the source registry are flagged as new source candidates.
- This is how the system would have found the Tom's Hardware glass cloth article
  even if Tom's Hardware wasn't a seed source.

**(B) Citation / link extraction**
- Every ingested article's outbound links and cited sources are extracted.
- If a new domain appears repeatedly (3+ times) in articles with constraint relevance,
  it becomes a PROVISIONAL source.
- This follows the citation chain: trade pub cites analyst report → analyst cites
  supplier disclosure → supplier references industry association data.

**(C) Source lifecycle: DISCOVERED → PROVISIONAL → CONFIRMED**
- `DISCOVERED`: first time a domain appears in a search sweep or citation extraction.
  Record: `{domain, first_seen, discovered_via, relevant_article_count: 1}`
- `PROVISIONAL` (auto): `relevant_article_count >= 3` from that domain.
  System begins periodic scraping of the domain's relevant section/feed.
- `CONFIRMED` (auto): `relevant_article_count >= 6` AND at least 2 articles
  produced valid ConstraintEvents. System assigns initial reliability/earliness scores
  based on how those articles performed (did they confirm? were they early?).
- Operator can also manually add, promote, or demote sources via dashboard.

**Source quality tracking (feedback loop):**
- Every source's reliability and earliness scores are recomputed monthly.
- `earliness` = how often this source's events appeared before the same event
  from higher-tier sources (i.e., did it beat the consensus?).
- `reliability` = what fraction of its extracted events were later confirmed
  by independent sources.
- Sources that consistently produce noise get auto-demoted. Sources that
  consistently surface early signals get auto-promoted.

---

## 5) Event system — strict JSON (no summaries)

### 5.1 ConstraintEvent schema (minimum viable)
Every ingested item yields **0+** events (usually 1). Use strict JSON; enforce validation.

```json
{
  "event_id": "uuid",
  "radar": "AI_CONSTRAINTS",
  "event_type": "LEAD_TIME_EXTENDED | ALLOCATION | PRICE_INCREASE | CAPEX_ANNOUNCED | CAPACITY_ONLINE | QUALIFICATION_DELAY | YIELD_ISSUE | DISRUPTION | POLICY_RESTRICTION",
  "constraint_layer": "MEMORY | ADV_PACKAGING | PCB_MATERIALS | POWER_DELIVERY_EQUIP | ...",
  "secondary_layer": "optional",
  "direction": "TIGHTENING | EASING | MIXED",
  "entities": [
    {"entity_id": "E:company:...", "role": "SUPPLIER | BUYER | DEMAND_DRIVER | OEM | REGULATOR"},
    {"entity_id": "E:geo:...", "role": "LOCATION"}
  ],
  "objects": [
    {"type": "PRODUCT | COMPONENT | MATERIAL | PROCESS_TECH", "name": "string", "aliases": ["optional"]}
  ],
  "magnitude": {
    "lead_time_weeks": {"from": 0, "to": 0},
    "price_change_pct": 0.0,
    "capex_usd": 0,
    "capacity_delta": "string or number",
    "notes": "optional"
  },
  "timing": {
    "happened_at": "YYYY-MM-DD or null",
    "reported_at": "YYYY-MM-DD",
    "expected_relief_window": "e.g., 2027-H2 or 2027-12 or null"
  },
  "evidence": {
    "source_id": "S:...",
    "source_url": "https://...",
    "source_tier": 1,
    "language": "ja|ko|zh|en|...",
    "translation_used": true,
    "confidence": 0.0,
    "snippets": ["optional short excerpts <= 25 words each"]
  },
  "tags": ["allocation", "fully-booked", "hyperscaler", "yield", "qualification"]
}
```

### 5.2 Event types — definitions
- `LEAD_TIME_EXTENDED`: lead time increased materially (must include from/to when possible)
- `ALLOCATION`: explicit allocation / “fully booked” / prioritized customers
- `PRICE_INCREASE`: credible price increase for constrained object
- `CAPEX_ANNOUNCED`: capacity expansion announced (include amount + timeline)
- `CAPACITY_ONLINE`: new capacity actually online (most important for easing)
- `QUALIFICATION_DELAY`: qualification bottleneck (e.g., second source not qualified)
- `YIELD_ISSUE`: yields deteriorate or complexity blocks ramp
- `DISRUPTION`: fire/outage/contamination/strike
- `POLICY_RESTRICTION`: export control / licensing / sanctions restricting key object

### 5.3 Required extraction behaviors
Event extractor must:
- pull **numbers** (capex, lead time, percent changes) whenever present
- separate **happened_at** vs **reported_at**
- identify **roles** (supplier vs buyer vs regulator)
- classify `direction` (tightening/easing/mixed)
- assign `confidence` (calibrated later)

---

## 6) Theme system — candidate → active → mature → fading

### 6.1 Theme object (living thesis)
A theme is a cluster of events about the same bottleneck.

```json
{
  "theme_id": "T:ai_constraints:<slug>",
  "name": "Human readable theme name",
  "constraint_layer": "PCB_MATERIALS",
  "status": "CANDIDATE | ACTIVE | MATURE | FADING",
  "scores": {
    "tightening_score": 0.0,
    "breadth_score": 0.0,
    "source_quality_score": 0.0,
    "novelty_score": 0.0
  },
  "thesis": {
    "one_liner": "What is scarce and why it matters",
    "why_now": ["bullet", "bullet"],
    "mechanism": ["causal chain bullet(s)"],
    "who_benefits": {"ringA": [], "ringB": [], "ringC": []},
    "who_suffers": [],
    "leading_indicators": [],
    "invalidation_triggers": [],
    "relief_timeline": "string or null"
  },
  "evidence_log": [
    {"event_id": "uuid", "weight": 0.0, "added_at": "YYYY-MM-DD"}
  ],
  "updated_at": "YYYY-MM-DD"
}
```

### 6.2 Candidate creation
A `CANDIDATE` theme is created when:
- clusterer sees a coherent cluster (same layer + shared objects)
- novelty is non‑trivial (new object/entity not seen recently)
- evidence quality is at least Tier 2+ or multiple Tier 3 mentions (discovery)

### 6.3 Promotion rule: CANDIDATE → ACTIVE (robust thresholds)
Promote when ALL hold within a rolling window:
- `min_window_days = 14`
- `min_tightening_events = 6`
- `min_unique_entities = 4`
- `min_tier1_or_tier2_sources = 2`
- coherence: same primary `constraint_layer` and shared key objects

### 6.4 Maturity and fading
- `MATURE`: tightening score plateauing and mainstream coverage increasing; relief timeline clearer.
- `FADING`: easing events dominate, capacity online, lead times normalize, or invalidation triggers hit.

---

## 7) Indicators & scoring (tightening score is the key)

### 7.1 Core indicators (computed per layer and per theme)
- **Event velocity**: tightening events/week (rolling)
- **Breadth**: unique suppliers + buyers + geos (normalized)
- **Source quality**: weighted by source tier + reliability
- **Allocation language index**: counts of allocation/lead‑time language (tier‑weighted)
- **Capex momentum**: capex announcements + on‑line dates (gives relief timeline)
- **Novelty**: new objects/entities not seen in last N days

### 7.2 Tightening score (initial weights; tune later)
Compute:

`TighteningScore(theme) =`
- `0.35 * velocity_norm`
- `0.20 * breadth_norm`
- `0.20 * source_quality`
- `0.15 * allocation_language_norm`
- `0.10 * novelty_norm`

Also compute per‑layer score as aggregate of theme scores in that layer.

### 7.3 Directional balance
Maintain:
- `tightening_events_count`
- `easing_events_count`
- `net_tightening = tightening - easing` (rolling)

---

## 8) Alerts (low noise, high signal)

### 8.1 Alert types
1) `NEW_CANDIDATE` — “something new is forming”
2) `INFLECTION` — “hard fact changed the situation”
3) `ACTIONABLE_BRIEFING` — “theme crossed threshold; here’s the trade map + disconfirmers”

### 8.2 Inflection triggers (hard rules)
Fire `INFLECTION` immediately if any of:
- Tier 1 reports **allocation / fully booked** through a date
- lead time jumps materially (tier‑weighted)
- disruption occurs (fire/outage/contamination/strike)
- policy restriction targets critical input (chips/tools/materials)
- major capex announced WITH timeline or capacity online

### 8.3 Actionable briefing threshold (initial)
Emit `ACTIONABLE_BRIEFING` if:
- `tightening_score >= 0.70`
- ≥3 Tier‑1/2 sources in evidence log
- thesis includes explicit invalidation triggers + relief timeline hypothesis

### 8.4 Slack/Discord templates (generate exactly)
#### NEW_CANDIDATE
- Title: `🟡 New constraint candidate: {theme_name}`
- Body (max 8 lines):
  - **What:** {one_liner}
  - **Layer:** {constraint_layer} | **Score:** {tightening_score:.2f}
  - **Evidence:** 2–3 bullets (each bullet = 1 event + link)
  - **Potential winners (Ring A/B):** {tickers/entities}
  - **What would disconfirm:** 1 bullet

#### INFLECTION
- Title: `🟥 INFLECTION: {theme_name}`
- Body:
  - **Change:** {hard fact}
  - **Impact path:** {one causal chain}
  - **Relief timeline:** {if known}
  - **Next indicator:** {leading indicator}

#### ACTIONABLE_BRIEFING
- Title: `🟢 Briefing: {theme_name} crossed threshold`
- Body sections:
  - **Thesis (3 lines)**
  - **Evidence table** (top 5 events)
  - **Beneficiaries:** Ring A / Ring B / Ring C
  - **Invalidation triggers**
  - **What to watch next (leading indicators)**

---

## 9) Tradables mapping (Ring A / B / C)

### 9.1 Rings
- **Ring A (pure plays):** constrained supplier of the scarce object
- **Ring B (adjacent winners):** equipment makers, substitutes, second source qualifiers
- **Ring C (expression vehicles):** country/sector indices capturing the theme (e.g., Korea memory, Japan materials)

### 9.2 Mapping workflow (system)
Maintain a `tradables_map` per theme:
- `entities[]` → canonical company
- `company` → `ticker` (if public) + `exchange`
- also store `baskets` (ETF/index) as Ring C options

**Note:** mapping does NOT imply trade; it creates a structured “who benefits” list.

---

## 10) Dashboards (MVP pages)

### Page A — Constraint heatmap
- Rows: 10 layers
- Columns: last 12 weeks
- Cell: tightening score + event count

### Page B — Theme board
Cards for ACTIVE themes:
- one‑liner thesis
- tightening score trend (sparkline)
- top 3 evidence events (links)
- ring A/B/C mapping
- invalidation triggers (1–3 bullets)

### Page C — Theme detail
- evidence timeline (events ordered)
- “what changed” weekly diff
- relief timeline (capex → online)
- entity graph (suppliers ↔ objects ↔ buyers)

### Page D — Capex & relief timeline
Gantt‑style:
- capex announcement date → construction → capacity online

---

## 11) Operating cadence (how humans use it)

### Daily (5–10 min)
- read daily digest
- acknowledge/ignore alerts
- add/remove 1–2 sources if needed

### Weekly (30–60 min)
- review top 3 tightening themes
- update invalidation triggers (human judgement)
- evaluate false positives, tune thresholds

---

## 12) Implementation blueprint (services + storage)

### 12.1 Services (containerized)
- `collector`: fetch RSS/sitemaps/web; store `raw_items`
- `normalizer`: language detect, translate, clean; store normalized text
- `entity_linker`: canonical IDs, aliases, ticker mapping + **entity discovery**
- `event_extractor`: produce `ConstraintEvent` JSON + validation
- `theme_engine`: cluster events → themes; update thesis; compute scores
- `alert_service`: triage → send Slack/Discord; store alert logs
- `dashboard`: UI/API for heatmap/theme board/details
- `monitoring`: logs/health checks; dead-letter queues

### 12.2 Entity discovery (critical — the system must find what it doesn't know)

The seed entity file (`config/seed_entities.yml`) bootstraps the system with known players.
But the real value is discovering NEW entities the operator has never heard of.

**Entity lifecycle: DISCOVERED → PROVISIONAL → CONFIRMED**

1. LLM extractor encounters a company/material/facility not in the registry.
2. System creates a `DISCOVERED` entity record:
   `{name, discovered_from_item, first_seen_at, layer_hint, mention_count: 1}`
3. On subsequent mentions, `mention_count` increments. Cross-language mentions merge.
4. **Promotion to PROVISIONAL** (auto): `mention_count >= 3` from `>= 2 distinct sources`.
5. **Promotion to CONFIRMED** (auto): `mention_count >= 6` from `>= 3 sources` AND
   appears in at least one `ConstraintEvent` with `direction: TIGHTENING`.
6. On promotion to CONFIRMED, system attempts:
   - ticker resolution (search for public listing)
   - alias expansion (find names in other languages)
   - ring classification (A/B/C based on role in constraint layer)
7. **Alert on discovery**: when a PROVISIONAL entity is promoted to CONFIRMED,
   emit a `NEW_ENTITY_DISCOVERED` notification:
   "New player in {layer}: {name} — mentioned in {N} articles from {M} sources.
   Appears to be a {role} of {object}. Ticker: {ticker or 'unknown/private'}."

**Why this matters:** The next Nittobo won't be in any seed file. It will be some
company in a Tom's Hardware article or a Japanese trade publication that the system
has never seen before. The system must surface it automatically.

### 12.3 Storage (minimum)
- Postgres (events, entities, themes, sources, alerts)
- Object storage (raw HTML/text snapshots)
- Optional: vector index for similarity (pgvector)

### 12.4 Core tables (conceptual)
- `sources(source_id, tier, reliability, earliness, language, url_pattern, notes)`
- `raw_items(item_id, source_id, fetched_at, url, title, raw_text, lang, hash)`
- `normalized_items(item_id, text_en, translation_conf, entities_hint, ...)`
- `entities(entity_id, type, canonical_name, aliases[], ticker_map, geo, status[DISCOVERED|PROVISIONAL|CONFIRMED], mention_count, first_seen_at, discovered_from)`
- `entity_mentions(entity_id, item_id, context_snippet, layer_hint, role_hint, seen_at)`
- `events(event_id, item_id, jsonb, constraint_layer, event_type, direction, reported_at, confidence)`
- `themes(theme_id, jsonb, status, tightening_score, updated_at)`
- `theme_event_links(theme_id, event_id, weight)`
- `alerts(alert_id, theme_id, alert_type, payload_json, sent_at, acked_at)`

---

## 13) RadarSpec YAML (drop-in config)
Save as `radars/ai_constraints.yml`.

```yaml
radar_id: AI_CONSTRAINTS
name: "AI Constraints — Constraint Hunter"
mode: "GLOBAL_FIRST"
mission: "Detect emerging bottlenecks that throttle AI scaling; maintain living theses with auditable evidence."

scope:
  include_layers:
    - COMPUTE_SILICON
    - MEMORY
    - ADV_PACKAGING
    - SUBSTRATES_FILMS
    - PCB_MATERIALS
    - INTERCONNECT_NETWORKING
    - POWER_DELIVERY_EQUIP
    - THERMAL_COOLING
    - DATACENTER_BUILD_PERMIT
    - FUEL_ONSITE_POWER
  exclude:
    - "generic AI product launch news without supply-chain causality"
    - "opinion-only macro pieces without concrete events"

globalization:
  languages: ["en", "ja", "ko", "zh", "es", "de", "fr"]
  store_original_text: true
  store_translated_text: true
  entity_aliasing_cross_language: true
  unit_normalization: true
  currency_normalization: "USD"

source_policy:
  tiers:
    tier1: ["supplier_earnings", "supplier_pr", "trade_pubs", "gov_industry_ministries"]
    tier2: ["reputable_wires_and_finance_press"]
    tier3: ["curated_social_discovery"]
  acceptance:
    require_cross_confirmation_for_major_alerts: true

event_types:
  - LEAD_TIME_EXTENDED
  - ALLOCATION
  - PRICE_INCREASE
  - CAPEX_ANNOUNCED
  - CAPACITY_ONLINE
  - QUALIFICATION_DELAY
  - YIELD_ISSUE
  - DISRUPTION
  - POLICY_RESTRICTION

theme_lifecycle:
  statuses: ["CANDIDATE", "ACTIVE", "MATURE", "FADING"]
  promote_candidate_to_active:
    window_days: 14
    min_tightening_events: 6
    min_unique_entities: 4
    min_tier12_sources: 2
    require_same_layer_coherence: true

indicators:
  - event_velocity
  - breadth
  - source_quality
  - allocation_language_index
  - capex_momentum
  - novelty

tightening_score_weights:
  event_velocity: 0.35
  breadth: 0.20
  source_quality: 0.20
  allocation_language_index: 0.15
  novelty: 0.10

alerts:
  types: ["NEW_CANDIDATE", "INFLECTION", "ACTIONABLE_BRIEFING"]
  inflection_triggers:
    - "tier1 allocation or fully-booked language"
    - "tier1 lead-time jump"
    - "disruption event"
    - "policy restriction targeting critical input"
    - "major capex announced with dates"
  actionable_briefing_threshold:
    tightening_score_gte: 0.70
    min_tier12_sources: 3

tradables_mapping:
  rings:
    A: "pure plays (constrained supplier)"
    B: "adjacent winners (equipment, substitutes, second source)"
    C: "expression vehicles (country/sector indices)"
```

---

## 14) Seed Kit (must exist; can be extended without code changes)

> Seed kit improves extraction/clustering. Implement so it can be edited without code changes.

### 14.1 Layer → object keywords (starter structure)
Create files:
- `seeds/ai_constraints/layers/<LAYER>.yml`
- Each contains canonical objects, aliases, and constraint phrase groups.

Example skeleton:

```yaml
layer: PCB_MATERIALS
objects:
  - name: "low-CTE glass cloth"
    aliases: ["T-glass", "low CTE glass", "glass fiber cloth", "glass cloth"]
  - name: "copper foil"
    aliases: ["electrolytic copper foil", "rolled copper foil"]
constraint_phrases:
  allocation: ["allocation", "fully booked", "prioritization", "limited supply"]
  lead_time: ["lead time extended", "delivery pushed", "backlog"]
  yield: ["yield issue", "low yield", "qualification delay"]
```

### 14.2 Multi-language phrase dictionaries
Maintain per-language lists for:
- allocation phrases
- lead-time phrases
- capacity ramp phrases
- disruption phrases

Store as:
- `seeds/ai_constraints/phrases/en.yml`
- `seeds/ai_constraints/phrases/ja.yml`, `.../ko.yml`, `.../zh.yml`, etc.

---

## 15) Non‑negotiable engineering constraints
- Deduplicate aggressively (`url canonicalization + fuzzy hash`).
- Idempotent pipelines (safe reruns).
- Full audit trail: item → event(s) → theme → alert.
- Never send more than **N** alerts/day (configurable). Prefer daily digest.
- Every alert must embed evidence links.
- Store original text for later verification (especially for non-English items).

---

## 16) Definition of done (Radar 1 “complete”)
Radar is complete when:
- It runs continuously and produces valid events.
- It maintains ACTIVE themes with living theses.
- It sends low-noise alerts with traceable evidence.
- It provides a dashboard heatmap + theme board.
- It can be extended via `radars/*.yml` + `seeds/*` with no code changes.
