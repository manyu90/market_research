# Market Research Radar

A multi-radar platform that detects emerging supply chain bottlenecks and structural constraints before they become consensus. Ingests global multi-language sources, extracts structured constraint events via LLM, clusters them into themes with tightening scores, and tracks affected companies (suppliers as beneficiaries, buyers as squeezed).

Built for investment research. Surfaces tradable signals from the gap between when a constraint appears in niche trade press (Japanese, Korean, Chinese, Taiwanese) and when it hits mainstream English-language financial media.

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
- **Single LLM** via OpenRouter — handles translation, extraction, and thesis generation.
- **10 languages** — EN, JA, KO, ZH, ZH-TW, ES, PT, DE, HI + SE Asian English
- **Docker Compose** with `restart: always` — runs unattended 24/7.

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env: add OPENROUTER_API_KEY and SERPER_API_KEY

# 2. Start everything
docker compose up -d

# 3. Seed the database (first time only)
docker compose exec pipeline python scripts/seed_db.py

# The pipeline will automatically:
#   - Collect from all sources every 1-4 hours
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

## How It Works

**Collection** — The scheduler triggers collection jobs per source (configurable intervals). Web search rotates keyword queries in 10 languages. RSS and scrapers pull from known publications. New items enter the DB as `COLLECTED`.

**Extraction** — The LLM reads each article and extracts structured `ConstraintEvent` objects: event type (LEAD_TIME_EXTENDED, ALLOCATION, PRICE_INCREASE, CAPEX_ANNOUNCED, etc.), constraint layer, direction (TIGHTENING/EASING/MIXED), affected entities with roles, magnitude (price %, capex USD, lead time weeks), and timing.

**Themes & Scoring** — Events are clustered by (constraint_layer + shared objects). Each theme gets a tightening score (`0.35*velocity + 0.20*breadth + 0.20*quality + 0.15*allocation + 0.10*novelty`). Themes progress: CANDIDATE → EMERGING → CONFIRMED → CONSENSUS. Most valuable at CANDIDATE/EMERGING — before the market prices it in.

**Entity Discovery** — When the LLM extracts an entity not in the registry, it's logged as DISCOVERED and promoted after enough mentions. This is how niche suppliers get surfaced automatically.

### What kind of results does it produce?

The system finds constraint themes across supply chain layers — materials shortages, capacity bottlenecks, lead time extensions, single-source dependencies — and tracks which companies sit on each side. It surfaces niche suppliers invisible to English-only research (e.g. monopoly substrate makers found via Japanese/Korean sources), detects tightening trends before they hit mainstream media, and scores how severe each bottleneck is becoming over time.

## Project Structure

```
config/
  seed_sources.yml      # Bootstrap sources (RSS, scrape, search)
  seed_entities.yml     # Seed entities with cross-language aliases
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

## Planned Radars

The architecture — multi-language collection, LLM extraction, entity tracking, theme clustering — is general-purpose. Each radar gets its own spec file (in `radars/`), seed sources, seed entities, and extraction prompts. The pipeline and infrastructure are shared.

**Radar 1 — AI Eats the World: Constraint Hunter** (live)
Detects the next AI supply chain bottleneck early. Tracks compute, memory, packaging, interconnect, power, cooling, and materials. Sources: supplier earnings, niche packaging/PCB publications, Asian supply chain media. Focus is AI supply chain *stress*, not AI news.

**Radar 2 — Grid + Power Buildout**
AI + reindustrialization is power-limited; the grid is the hidden throttle. Signals: transformer backlog, switchgear lead times, interconnect approvals, turbine order books. Sources: utility commission filings, equipment OEM commentary, regional permitting news.

**Radar 3 — Industrial Materials & Specialty Chemicals**
"Boring inputs" become huge trades when one spec dominates. Signals: purity constraints, yield issues, qualification delays, single-factory dependencies. Sources: trade journals, supplier PR, plant expansions, environmental/regulatory actions.

**Radar 4 — Precious Metals + Miners (Local-Language Edge)**
Detect early capex, permitting, billionaire flows, jurisdiction shifts. Signals: new mines financed, royalty/tax changes, political risk. Sources: Spanish/LatAm outlets, provincial bulletins, local regulators, company decks.

**Radar 5 — Credit/Liquidity Stress & Forced Selling**
Catch structure breaks — when financing or leverage forces repricing. Signals: fund gating, covenant stress, spreads, refinancing walls, margin changes. Sources: filings, credit commentary, finance press, earnings risk language.

**Radar 6 — Geopolitics / Export Controls / Industrial Policy**
Themes often begin as policy constraints. Signals: export bans, subsidies, procurement ramps, strategic stockpile changes. Sources: government releases, official registers, tender portals, sanctions lists.

**Radar 7 — Shipping / Logistics / Chokepoints**
Physical constraints leak into prices early via logistics. Signals: freight spikes, port disruptions, insurance rates, rerouting, canal issues. Sources: shipping industry sources, port authority updates, marine insurance.

**Radar 8 — Country-Specific Capital Rotation**
Some themes express through countries (indexes + policy + champions). Signals: local capex, pension flows, currency policy, national subsidy stacks. Sources: local-language business press, gov policy, conglomerate disclosures.

## Cost

- **LLM** (OpenRouter): ~$2-5/day depending on article volume
- **Web search** (Serper.dev): ~$6/month for 10-language coverage
- **Infrastructure**: Single VPS (Hetzner CX32, ~$15/month) runs everything

## Tech Stack

Python 3.12, asyncpg, httpx, FastAPI, APScheduler, feedparser, trafilatura, lingua-py, Playwright, PyMuPDF, Pydantic v2, PostgreSQL 16, Docker Compose
