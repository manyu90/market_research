# AI Constraints Radar

Supply chain constraint tracker for the AI hardware ecosystem. Collects articles from 46+ sources across 10 languages, extracts structured constraint events via LLM, clusters into themes, and sends Telegram alerts.

## Quick Start

```bash
cp .env.example .env          # add API keys
docker compose up -d
docker compose exec pipeline python scripts/seed_db.py  # first time only
docker compose logs pipeline -f
```

## Architecture

**Three Docker services:**
- `db` — PostgreSQL 16 (persistent pgdata volume)
- `pipeline` — Continuous processing loop (`scripts/run_pipeline.py`)
- `api` — FastAPI on port 8000

**No Redis, no Celery.** Postgres is the only queue — `SELECT FOR UPDATE SKIP LOCKED` on the items table.

## Pipeline Stages

Items flow: `COLLECTED → NORMALIZED → LINKED → EXTRACTED → DONE`

1. **Collect** — RSS, HTML scrape, JS render (Playwright), PDF monitor, Serper web search
2. **Normalize** — Language detect (lingua) + translate to English (MiniMax M2.5 via OpenRouter)
3. **Link** — Entity matching via alias index (substring, CJK-aware)
4. **Extract** — LLM structured extraction → constraint events (JSON mode)
5. **Theme** — Cluster events by layer+objects, score tightening, generate theses
6. **Alert** — Rule-based triage → Telegram (NEW_CANDIDATE, INFLECTION, ACTIONABLE_BRIEFING)

## Key Directories

```
config/
  constraint_taxonomy.yml   — Search queries per language (76 EN, 43 JA/KO/ZH, etc.)
  seed_sources.yml          — 46 bootstrap sources (RSS, scrapers, web search)
  seed_entities.yml         — 100+ entities with multilingual aliases
  llm.yml                   — LLM config (MiniMax M2.5 via OpenRouter)
src/
  db.py                     — asyncpg pool, migrations, query helpers
  llm.py                    — OpenRouter client with semaphore concurrency (5)
  models.py                 — Pydantic models (ConstraintEvent, ThemeThesis, etc.)
  settings.py               — Env config via pydantic-settings
  collector/                — All data acquisition (RSS, scrape, search, scheduler)
    query_generator.py      — Round-robin query rotation for web search sources
  normalizer/               — Language detection + translation
  linker/                   — Entity matching + auto-discovery
  extractor/                — LLM event extraction
  themes/                   — Clustering, scoring, thesis generation
  alerts/                   — Triage rules + Telegram delivery
  api/                      — FastAPI routes (themes, events, heatmap, sources)
scripts/
  run_pipeline.py           — Main entry point (scheduler + processing loop)
  seed_db.py                — One-time DB seeding from config YAMLs
  backfill.py               — Reset items for reprocessing
  backfill_entities.py      — Discover entities from existing events
migrations/
  001_initial_schema.sql    — Core tables
  002_themes_alerts.sql     — Themes + alerts
data/
  query_cursors.json        — Persisted round-robin cursor state (gitignored)
```

## Web Search Query System

`config/constraint_taxonomy.yml` has a flat list of search queries per language. Broad queries first (catch big stories), then topic-specific. The LLM downstream decides what's a constraint.

`src/collector/query_generator.py` loads these at startup, round-robins through them 3 at a time per sweep. Cursor state persists in `data/query_cursors.json` across restarts. Falls back to hardcoded `search_queries` in seed_sources.yml if taxonomy isn't loaded.

## LLM

MiniMax M2.5 via OpenRouter — $0.20/M input, $1.00/M output. Single model handles translation, extraction, and thesis generation. Config in `config/llm.yml`.

## Environment Variables

```
DATABASE_URL              — Postgres connection string
OPENROUTER_API_KEY        — For LLM calls
SERPER_API_KEY            — For web search
TELEGRAM_BOT_TOKEN        — For alerts (optional)
TELEGRAM_CHAT_ID          — Telegram chat target (optional)
LLM_CONCURRENCY=5         — Max concurrent LLM calls
```

## Rebuilding After Code Changes

```bash
docker compose up -d --build pipeline
```

The source code is COPYed into the image at build time. Local edits require a rebuild.
