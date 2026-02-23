# Market Research Radar

Finds supply chain bottlenecks before Wall Street does.

The current radar tracks **AI supply chain stress** — every physical layer that has to scale for the AI buildout to continue. Not AI news. The actual bottlenecks: who makes the glass fiber for the substrates, who has the InP wafers for the optical interconnect, who's blocking the power grid hookups for the datacenters, where the copper comes from for advanced packaging. The stuff that constrains how fast AI infrastructure can actually get built.

The system reads niche trade press in 10 languages — Japanese semiconductor journals, Korean PCB industry newsletters, Taiwanese substrate reports, Brazilian mining bulletins — extracts structured "constraint events" via LLM, clusters them into scored themes, and tells you which companies are on each side: suppliers who benefit, and buyers who get squeezed.

The edge is language and speed. A glass fiber shortage for AI substrates shows up in Japanese trade press weeks before it hits English-language analyst notes. By the time CNBC runs the story, the move is done.

## What it found (first run, 698 articles, 10 languages)

Every example below is a chokepoint in the AI infrastructure stack.

**Nittobo (3110.TSE)** — The AI buildout needs advanced substrates (ABF, glass core). Those substrates need T-Glass / glass fiber cloth. Nittobo is the dominant supplier. Japanese, Korean, and Taiwanese sources all independently flagged tightening. This company barely appears in English financial media, but it sits directly in the critical path of AI packaging.

**AXT Inc (AXTI)** — GPU clusters need optical transceivers to talk to each other. Those transceivers need Indium Phosphide wafers. AXT has a near-monopoly. Micro-cap, pure-play on the AI interconnect bottleneck. Found via Asian semiconductor supply chain coverage.

**Neotis** — AI servers need HDI PCBs. Those PCBs need laser-drilled microvias. The micro drill bits come from Neotis in Korea. Samsung Electro-Mechanics and LG Innotek depend on them. Surfaced exclusively from Korean-language sources — zero English coverage.

**Grid interconnection queues** — Every new AI datacenter needs grid power. The bottleneck isn't land or capital — it's multi-year power grid connection queues (PJM, Southern Company). The AI buildout is physically gated by how fast utilities can hook up new load.

**Copper for advanced packaging** — HBM and CoWoS packaging (the stuff that stacks memory on GPUs) are copper-intensive. LATAM sources surfaced mining constraints in Argentina and Chile that connect directly to AI packaging capacity timelines.

248 structured constraint events. 43 emerging themes across memory, substrates, compute silicon, advanced packaging, power delivery, datacenter build, cooling, PCB materials, interconnect, and fuel. Suppliers, buyers, tightening scores, and a thesis for each.

## How it works

```
Sources (46 active)            Pipeline (Postgres queue)           Output
─────────────────             ─────────────────────────          ─────────
RSS feeds (15)        →                                      → Scored themes
HTML scrapers (8)     →   COLLECTED → NORMALIZED → LINKED    → Entity tracking
PDF monitors (4)      →              → EXTRACTED → DONE      → Telegram alerts
JS renderers (1)      →                                      → API + Dashboard
Serper web search (10)→       ↑ asyncio.gather (5 concurrent MiniMax M2.5 calls)
```

**Collect** — RSS, HTML scraping (trafilatura), JS rendering (Playwright), PDF monitoring, and Serper.dev web search across 10 languages. Each source runs on its own schedule (1-4 hours). Web search rotates keyword queries in EN, JA, KO, ZH, ZH-TW, ES, PT, DE, HI, and SE Asian English.

**Extract** — MiniMax M2.5 (via OpenRouter) reads each article and outputs structured `ConstraintEvent` objects: event type, constraint layer, direction (tightening/easing), affected entities with roles, magnitude (price %, capex $, lead time weeks), and timing. A reference list of key suppliers per material ensures the LLM tags relevant companies even when not named in the article.

**Cluster & Score** — Events group by (constraint_layer + shared objects). Each theme gets a tightening score: `0.35*velocity + 0.20*breadth + 0.20*quality + 0.15*allocation + 0.10*novelty`. Themes progress CANDIDATE → EMERGING → CONFIRMED → CONSENSUS. The signal is strongest at CANDIDATE/EMERGING.

**Discover** — Entities not in the seed registry get logged as DISCOVERED and promote to CONFIRMED after enough mentions. This is how Neotis and other niche suppliers get found without being pre-programmed.

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

The pipeline is radar-agnostic. Adding a new radar = new spec file + seed sources + seed entities. The collection, extraction, and scoring machinery is shared.

**Grid + Power Buildout** — AI and reindustrialization are power-limited. Transformer backlogs, switchgear lead times, interconnect approval queues, turbine order books. Sources: utility commission filings, equipment OEM earnings, regional permitting news.

**Industrial Materials & Specialty Chemicals** — Boring inputs become huge trades when one purity spec or one factory dominates. Yield issues, qualification delays, single-source dependencies. Sources: trade journals, supplier PR, plant expansion announcements.

**Precious Metals + Miners (Local-Language Edge)** — Early capex signals, permitting changes, jurisdiction shifts. The same multi-language advantage applies: Spanish/LatAm provincial bulletins surface mine financing and royalty changes before English-language mining press picks them up.

## Tech stack

Python 3.12 / asyncpg / httpx / FastAPI / APScheduler / feedparser / trafilatura / lingua-py / Playwright / PyMuPDF / Pydantic v2 / PostgreSQL 16 / MiniMax M2.5 (OpenRouter) / Serper.dev / Docker Compose
