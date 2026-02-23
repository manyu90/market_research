# Market Research Radar

Finds supply chain bottlenecks before Wall Street does.

The AI buildout has a problem nobody talks about on CNBC: it's physically constrained at every layer of the stack. GPUs need HBM. HBM needs advanced packaging. Packaging needs substrates. Substrates need glass fiber cloth — and one company in Japan makes most of it. The constraint migrates up the stack, and the earliest signals appear in Japanese trade journals, Korean PCB newsletters, and Taiwanese substrate reports — weeks before English-language analysts notice.

This system reads those sources. It ingests niche trade press in 10 languages, extracts structured constraint events via LLM, clusters them into scored bottleneck themes, and continuously answers four questions:

- **What is scarce? Why now?**
- **Who benefits / who gets squeezed?**
- **What would disconfirm this?**
- **What to watch next?**

This is not AI news. This is **AI supply chain stress**.

## What it found (first run — 698 articles, 10 languages, 43 themes)

The system's top themes by event volume were memory (SK Hynix, Samsung, Micron — HBM allocation, pricing, capex) and compute silicon (TSMC CoWoS capacity, NVIDIA supply). No surprise — those are consensus trades and well-covered in English. The system detects them, but that's table stakes.

The interesting finds are the ones further down the stack — the kind of thing that doesn't show up if you only read English-language sources. Each traces the causal chain: demand driver → constraint layer → scarce object → supplier → capacity/lead time.

**Nittobo (3110.TSE)** — AI packaging needs advanced substrates. Substrates need T-Glass / glass fiber cloth. Nittobo is the dominant supplier. Japanese, Korean, and Taiwanese sources all independently flagged tightening — allocation language, lead time extensions, capacity fully booked. This company barely appears in English financial media. Ring A pure play on the substrates bottleneck.

**AXT Inc (AXTI)** — GPU clusters need optical transceivers to interconnect. Transceivers need Indium Phosphide wafers. AXT has a near-monopoly on InP substrates. Micro-cap, pure-play on the AI interconnect layer. Found by cross-referencing Asian semiconductor supply chain coverage that English sources hadn't picked up yet.

**Neotis** — AI servers need HDI PCBs. PCBs need laser-drilled microvias. The micro drill bits come from Neotis in Korea. Samsung Electro-Mechanics and LG Innotek depend on them. Surfaced exclusively from Korean-language sources — zero English coverage exists. This is why multi-language ingestion matters.

**Grid interconnection queues** — Every new AI datacenter needs grid power. The bottleneck isn't land or capital — it's multi-year power grid connection queues (PJM, Southern Company). The entire AI buildout is physically gated by how fast utilities can hook up new load. Constraint layer: DATACENTER_BUILD_PERMIT.

**Copper for advanced packaging** — HBM and CoWoS packaging (the stuff that stacks memory on GPUs) are copper-intensive. LATAM sources surfaced mining constraints in Argentina and Chile that map directly to AI packaging capacity timelines. Spanish/Portuguese-language discovery.

248 structured constraint events across 10 layers. Each event has: type, direction (tightening/easing), affected entities with roles, magnitude (price %, capex $, lead time weeks), timing, and source evidence. Each theme has a tightening score, a living thesis, beneficiaries (Ring A/B/C), and invalidation triggers.

## How it works

The system tracks 10 constraint layers — every physical input that has to scale for AI infrastructure to grow:

| Layer | What's constrained |
|-------|-------------------|
| COMPUTE_SILICON | Foundry capacity, wafers, lithography |
| MEMORY | HBM, DRAM stacks, yields, allocation |
| ADV_PACKAGING | 2.5D/3D packaging, interposers, CoWoS |
| SUBSTRATES_FILMS | ABF film, advanced substrates |
| PCB_MATERIALS | Glass cloth, copper foil, laminates, drill bits |
| INTERCONNECT_NETWORKING | Optical transceivers, switches, cables |
| POWER_DELIVERY_EQUIP | Transformers, switchgear, PDUs |
| THERMAL_COOLING | Liquid cooling, chillers, heat exchangers |
| DATACENTER_BUILD_PERMIT | EPC, permitting, grid interconnect queues |
| FUEL_ONSITE_POWER | Gas turbines, gensets, microgrids |

```
Sources (46 active)            Pipeline (Postgres queue)           Output
─────────────────             ─────────────────────────          ─────────
RSS feeds (15)        →                                      → Scored themes
HTML scrapers (8)     →   COLLECTED → NORMALIZED → LINKED    → Living theses
PDF monitors (4)      →              → EXTRACTED → DONE      → Telegram alerts
JS renderers (1)      →                                      → API + Dashboard
Serper web search (10)→       ↑ asyncio.gather (5 concurrent MiniMax M2.5 calls)
```

**Collect** — RSS, HTML scraping (trafilatura), JS rendering (Playwright), PDF monitoring, and Serper.dev web search across EN, JA, KO, ZH, ZH-TW, ES, PT, DE, HI, and SE Asian English. Each source runs on its own schedule. Web search rotates constraint-layer keyword queries in all 10 languages.

**Extract** — MiniMax M2.5 (via OpenRouter) reads each article and produces structured `ConstraintEvent` JSON: event type (LEAD_TIME_EXTENDED, ALLOCATION, PRICE_INCREASE, CAPEX_ANNOUNCED, CAPACITY_ONLINE, YIELD_ISSUE, DISRUPTION, POLICY_RESTRICTION, QUALIFICATION_DELAY), constraint layer, direction, entities with roles, magnitude, and timing. A reference list of key suppliers per material ensures the LLM tags relevant companies even when not named.

**Cluster & Score** — Events group into themes by (constraint_layer + shared objects). Each theme gets a tightening score: `0.35*velocity + 0.20*breadth + 0.20*quality + 0.15*allocation + 0.10*novelty`. Themes progress CANDIDATE → EMERGING → CONFIRMED → CONSENSUS. The signal is strongest at CANDIDATE/EMERGING — before the market prices it in.

**Discover** — The system finds what it doesn't know. Entities not in the seed registry get logged as DISCOVERED and promote to CONFIRMED after enough cross-source mentions. The next Nittobo won't be in any seed file — it'll be some company in a Japanese trade publication that the system surfaces automatically.

**Alert** — Three alert types: NEW_CANDIDATE (something new is forming), INFLECTION (hard fact changed the situation — allocation announced, lead time jumped, disruption occurred), and ACTIONABLE_BRIEFING (theme crossed threshold with full thesis, beneficiaries, and disconfirmers).

## Tradables mapping

Every theme maps affected companies into rings:
- **Ring A** — Pure plays: the constrained supplier of the scarce object (e.g., Nittobo for glass cloth)
- **Ring B** — Adjacent winners: equipment makers, substitutes, second-source qualifiers
- **Ring C** — Expression vehicles: country/sector ETFs capturing the theme (e.g., Korea memory, Japan materials)

## Running it

```bash
cp .env.example .env
# Add OPENROUTER_API_KEY and SERPER_API_KEY

docker compose up -d
docker compose exec pipeline python scripts/seed_db.py   # first time only

# Watch it work
docker compose logs pipeline -f
```

Three services: Postgres 16 (data store + work queue via `SELECT FOR UPDATE SKIP LOCKED`), pipeline (`restart: always`), and API (FastAPI). No Redis, no Celery. Runs on a single Hetzner CX32 (~$15/month). LLM costs ~$2-5/day. Search costs ~$6/month.

## Project structure

```
radars/           ai_constraints_spec.md (canonical design spec)
config/           seed_sources.yml, seed_entities.yml, llm.yml
migrations/       numbered SQL (001_initial_schema, 002_themes_alerts)
scripts/          run_pipeline.py, seed_db.py, backfill.py
src/collector/    RSS, scraper, JS renderer, PDF monitor, Serper web search
src/normalizer/   lingua-py language detection + LLM translation
src/linker/       entity matching (alias index) + discovery lifecycle
src/extractor/    LLM → structured ConstraintEvent extraction
src/themes/       clustering, tightening scoring, thesis generation
src/alerts/       Telegram alerts + daily digest
src/api/          FastAPI dashboard
```

## Next radars

The pipeline is radar-agnostic. Adding a new radar = spec file + seed sources + seed entities. The collection, extraction, and scoring machinery is shared.

**Grid + Power Buildout** — AI and reindustrialization are power-limited. Transformer backlogs, switchgear lead times, interconnect approval queues, turbine order books. Sources: utility commission filings, equipment OEM earnings, regional permitting news. Tradables: equipment OEMs, EPC firms, specialty component suppliers, gas turbine ecosystem.

**Industrial Materials & Specialty Chemicals** — Boring inputs become huge trades when one purity spec or one factory dominates. Yield issues, qualification delays, single-source dependencies. Sources: trade journals, supplier PR, plant expansions. Tradables: niche materials makers, chemical producers, upstream mining/processing.

**Precious Metals + Miners (Local-Language Edge)** — Early capex signals, permitting changes, jurisdiction shifts. Spanish/LatAm provincial bulletins surface mine financing and royalty changes before English-language mining press picks them up. Tradables: miners, streamers/royalties, project developers, country ETFs.

## Tech stack

Python 3.12 / asyncpg / httpx / FastAPI / APScheduler / feedparser / trafilatura / lingua-py / Playwright / PyMuPDF / Pydantic v2 / PostgreSQL 16 / MiniMax M2.5 (OpenRouter) / Serper.dev / Docker Compose
