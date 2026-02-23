# Market Research Radar

A 24/7 autonomous system that detects emerging supply chain bottlenecks before they become consensus. Ingests global multi-language sources, extracts structured constraint events via LLM, clusters them into themes with tightening scores, and tracks which companies are affected — as suppliers (beneficiaries) or buyers (squeezed).

Built for investment research. The system surfaces tradable signals from the gap between when a constraint appears in niche trade press (Japanese, Korean, Chinese, Taiwanese) and when it hits mainstream English-language financial media.

## Current Radar: AI Supply Chain Constraints

The first radar tracks bottlenecks across the AI infrastructure stack:

| Layer | What's constrained | Example signals found |
|-------|-------------------|----------------------|
| **Memory** | HBM, DRAM, NAND, HDD | SK Hynix $14B packaging fab, memory prices doubled, HDDs sold out for 2025 |
| **Substrates & Films** | T-Glass, ABF film, CCL, glass fiber | Nittobo single-source risk, Ajinomoto ABF monopoly, glass fiber shortage |
| **Compute Silicon** | Foundry capacity, InP wafers, SiC | TSMC CoWoS bottleneck, AXT InP wafer monopoly, US export controls |
| **Advanced Packaging** | CoWoS, HBM assembly, OSAT | ASE/King Yuan capacity, Tata India OSAT entry |
| **Power Delivery** | Transformers, switchgear | Siemens Energy/GE Vernova 2-3 year lead times |
| **Datacenter Build** | Grid interconnection, permitting | PJM multi-year queue, Virginia/Texas/California backlogs |
| **Thermal Cooling** | Liquid cooling systems | Vertiv, Schneider, Envicool capacity race |
| **PCB Materials** | Drill bits, laminates | Korean micro drill bit bottleneck (Neotis) |
| **Interconnect** | Optical transceivers, HVDC | Transmission expansion for datacenter power |
| **Fuel / Onsite Power** | Natural gas, geothermal | Shadow power plants, Ormat geothermal for datacenters |

### What it found (first run)

248 structured constraint events from 698 articles across 10 languages. 43 emerging themes tracked. Key discoveries that were invisible in English-only sources:

- **Nittobo (3110.TSE)** — Dominant T-Glass supplier. Japanese/Korean/Taiwanese searches independently confirmed the glass fiber bottleneck. Tightening score 0.62.
- **AXT Inc (AXTI)** — Indium Phosphide wafer monopoly for optical transceivers connecting AI clusters. Micro-cap, pure-play bottleneck.
- **Neotis** (Korean) — Micro drill bits for PCB manufacturing. Samsung Electro-Mechanics and LG Innotek are dependent. Korean-language discovery only.
- **Grid interconnection queues** — PJM, Southern Company. Datacenter builds bottlenecked not by land but by multi-year power grid connection backlogs.
- **Copper mining** (BHP, Lundin) — Advanced packaging copper demand. LATAM sources surfaced Argentina/Chile mining constraints.

## Architecture

```
Sources (46 active)          Pipeline (Postgres queue)         Output
─────────────────           ─────────────────────────        ─────────
RSS feeds (15)      →                                    → Themes + scores
HTML scrapers (8)   →   COLLECTED → NORMALIZED → LINKED  → Entity tracking
PDF monitors (4)    →              → EXTRACTED → DONE    → Alerts (Telegram)
JS renderers (1)    →                                    → API + Dashboard
Web search (10)     →       ↑ asyncio.gather (5 concurrent LLM calls)
```

- **Postgres 16** — data store AND work queue (`SELECT FOR UPDATE SKIP LOCKED`). No Redis needed.
- **MiniMax M2.5** via OpenRouter — single LLM model handles translation, extraction, and thesis generation.
- **10 languages** — EN, JA, KO, ZH, ZH-TW, ES, PT, DE, HI + SE Asian English
- **Docker Compose** with `restart: always` — runs unattended.

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env: add OPENROUTER_API_KEY and SERPER_API_KEY

# 2. Start Postgres + Pipeline
docker compose up -d

# 3. Seed the database (first time only)
docker compose exec pipeline python scripts/seed_db.py

# The pipeline will automatically:
#   - Collect from all sources
#   - Translate non-English articles
#   - Link entities (companies, products)
#   - Extract structured constraint events via LLM
#   - Cluster into themes and compute tightening scores
#   - Loop every 15 seconds for new items
```

### Monitor

```bash
# Live logs
docker compose logs pipeline -f

# Check DB state
docker compose exec pipeline python -c "
import asyncio
from src import db
async def check():
    rows = await db.fetch('SELECT pipeline_status, COUNT(*) FROM items GROUP BY pipeline_status')
    for r in rows: print(f'{r[0]:15s} {r[1]}')
    events = await db.fetchval('SELECT COUNT(*) FROM events')
    themes = await db.fetchval('SELECT COUNT(*) FROM themes')
    print(f'Events: {events}, Themes: {themes}')
    await db.close_pool()
asyncio.run(check())
"
```

## Project Structure

```
config/
  seed_sources.yml      # 46 bootstrap sources (RSS, scrape, search)
  seed_entities.yml     # 41 seed entities with cross-language aliases
  llm.yml               # LLM provider config (OpenRouter)
migrations/
  001_initial_schema.sql  # sources, items, entities, events
  002_themes_alerts.sql   # themes, alerts, pipeline_runs
scripts/
  run_pipeline.py       # Main entry point (scheduler + pipeline loop)
  seed_db.py            # Load YAML configs into Postgres
  backfill.py           # Re-process items when prompts change
src/
  collector/            # RSS, HTML scrape, JS render, PDF, web search
  normalizer/           # Language detection (lingua-py) + LLM translation
  linker/               # Entity matching (alias index) + discovery
  extractor/            # LLM structured extraction → ConstraintEvent
  themes/               # Clustering, tightening scoring, thesis generation
  alerts/               # Telegram alerts + daily digest
  api/                  # FastAPI dashboard (heatmap, themes, events)
  db.py                 # asyncpg pool + migration runner
  llm.py                # OpenRouter client with retries + semaphore
  models.py             # Pydantic models (ConstraintEvent, Theme, etc.)
  settings.py           # pydantic-settings, loads .env + YAML
```

## How It Works

### Collection
Every 1-4 hours (configurable per source), the scheduler triggers collection jobs. Web search rotates through keyword queries in 10 languages, discovering articles from any domain. RSS and scrapers pull from known publications. New items enter the DB as `COLLECTED`.

### Extraction
The LLM reads each article and extracts zero or more structured `ConstraintEvent` objects:
- **event_type**: LEAD_TIME_EXTENDED, ALLOCATION, PRICE_INCREASE, CAPEX_ANNOUNCED, CAPACITY_ONLINE, YIELD_ISSUE, DISRUPTION, POLICY_RESTRICTION, QUALIFICATION_DELAY
- **constraint_layer**: which part of the stack
- **direction**: TIGHTENING, EASING, or MIXED
- **entities**: companies with roles (SUPPLIER, BUYER, DEMAND_DRIVER, OEM, REGULATOR)
- **magnitude**: concrete numbers (price change %, capex USD, lead time weeks, capacity delta)
- **timing**: when it happened, when reported, expected relief window

The extraction prompt includes a reference list of key suppliers per material (e.g., "glass fiber → Nittobo") so the LLM tags relevant companies even when they're not named in the article.

### Themes & Scoring
Events are clustered by (constraint_layer + shared objects). Each theme gets a tightening score:

```
0.35 × velocity  +  0.20 × breadth  +  0.20 × quality  +  0.15 × allocation  +  0.10 × novelty
```

Themes progress: CANDIDATE → EMERGING → CONFIRMED → CONSENSUS. The system is most valuable at the CANDIDATE/EMERGING stage — before the market prices it in.

### Entity Discovery
The system doesn't just track known companies. When the LLM extracts an entity not in the registry, it's logged as DISCOVERED. After enough mentions, it promotes to CONFIRMED. This is how niche suppliers like Neotis (Korean micro drill bits) or Guangyuan New Materials (Chinese CCL) get surfaced automatically.

## Future Radars

This system is designed as a **multi-radar platform**. The AI supply chain radar is the first instance. The architecture — multi-language collection, LLM extraction, entity tracking, theme clustering — is general-purpose. Future radars will track different supply chains and constraint domains:

- **Energy Transition** — transformer lead times, grid interconnection queues, copper/lithium/rare earth supply, permitting bottlenecks for renewables and nuclear
- **Defense & Aerospace** — munitions production capacity, titanium supply, semiconductor export controls, shipbuilding backlogs
- **Pharma & Biotech** — API (active pharmaceutical ingredient) sourcing, CDMO capacity, FDA approval queues, cold chain logistics
- **Agriculture & Food** — fertilizer supply (potash, phosphate), shipping route disruptions, weather-driven crop constraints, food processing capacity
- **Construction & Real Estate** — cement, steel, skilled labor shortages, permitting timelines, interest rate sensitivity on project pipelines
- **Automotive** — EV battery supply chain (cathode, anode, separator), legacy ICE component wind-down, ADAS sensor supply

Each radar gets its own spec file (in `radars/`), seed sources, seed entities, and extraction prompts. The pipeline, database schema, and infrastructure are shared. Adding a new radar means writing a spec and config — the collection, extraction, and scoring machinery is already built.

## Cost

Running costs are minimal:
- **LLM (OpenRouter/MiniMax M2.5)**: ~$2-5/day depending on article volume
- **Web search (Serper.dev)**: ~$6/month for 10-language coverage (~200 queries/day)
- **Infrastructure**: Single VPS (Hetzner CX32, ~$15/month) runs everything

## Tech Stack

Python 3.12, asyncpg, httpx, FastAPI, APScheduler, feedparser, trafilatura, lingua-py, Playwright, PyMuPDF, Pydantic v2, PostgreSQL 16, Docker Compose
