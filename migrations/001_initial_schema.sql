-- 001_initial_schema.sql
-- Initial database schema for the AI supply chain constraint tracking system.

BEGIN;

-- ============================================================
-- sources – registry of every feed / scrape target we monitor
-- ============================================================
CREATE TABLE IF NOT EXISTS sources (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id               TEXT UNIQUE NOT NULL,          -- e.g. "S:semiengineering"
    name                    TEXT NOT NULL,
    url                     TEXT,
    feed_url                TEXT,
    fetch_method            TEXT NOT NULL
                            CHECK (fetch_method IN (
                                'rss', 'scrape_html', 'scrape_js',
                                'api', 'pdf_monitor', 'web_search'
                            )),
    scrape_target           TEXT,
    language                TEXT NOT NULL DEFAULT 'en',
    tier                    SMALLINT NOT NULL DEFAULT 2,
    reliability             REAL NOT NULL DEFAULT 0.5,
    earliness               REAL NOT NULL DEFAULT 0.5,
    schedule_minutes        INT NOT NULL DEFAULT 60,
    layers                  TEXT[] NOT NULL DEFAULT '{}',
    search_queries          TEXT[],
    status                  TEXT NOT NULL DEFAULT 'CONFIRMED'
                            CHECK (status IN (
                                'DISCOVERED', 'PROVISIONAL', 'CONFIRMED', 'DISABLED'
                            )),
    relevant_article_count  INT NOT NULL DEFAULT 0,
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- items – raw collected articles; doubles as the work queue
--         via pipeline_status
-- ============================================================
CREATE TABLE IF NOT EXISTS items (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id               TEXT NOT NULL REFERENCES sources(source_id),
    url                     TEXT NOT NULL,
    url_hash                TEXT NOT NULL,                  -- for dedup
    content_hash            TEXT,                           -- for content dedup
    title                   TEXT,
    raw_text                TEXT,
    text_en                 TEXT,                           -- translated text
    language                TEXT,
    translation_confidence  REAL,
    published_at            TIMESTAMPTZ,
    fetched_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    pipeline_status         TEXT NOT NULL DEFAULT 'COLLECTED'
                            CHECK (pipeline_status IN (
                                'COLLECTED', 'NORMALIZED', 'LINKED',
                                'EXTRACTED', 'DONE', 'SKIPPED', 'ERROR'
                            )),
    pipeline_error          TEXT,
    outbound_links          TEXT[],
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (url_hash)
);

-- ============================================================
-- entities – canonical entity registry
-- ============================================================
CREATE TABLE IF NOT EXISTS entities (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id           TEXT UNIQUE NOT NULL,               -- e.g. "E:company:tsmc"
    canonical_name      TEXT NOT NULL,
    type                TEXT NOT NULL
                        CHECK (type IN (
                            'COMPANY', 'FACILITY', 'PRODUCT', 'COMPONENT',
                            'MATERIAL', 'PROCESS_TECH', 'BUYER_CLASS',
                            'GEO', 'POLICY_PROGRAM', 'INDEX'
                        )),
    aliases             JSONB NOT NULL DEFAULT '{}',        -- language -> [aliases]
    tickers             JSONB NOT NULL DEFAULT '[]',
    roles               TEXT[] NOT NULL DEFAULT '{}',
    layers              TEXT[] NOT NULL DEFAULT '{}',
    ring                TEXT CHECK (ring IN ('A', 'B', 'C')),
    geo                 TEXT,
    status              TEXT NOT NULL DEFAULT 'CONFIRMED'
                        CHECK (status IN (
                            'DISCOVERED', 'PROVISIONAL', 'CONFIRMED'
                        )),
    mention_count       INT NOT NULL DEFAULT 0,
    discovered_from_item UUID,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- entity_mentions – tracks every entity appearance in an item
-- ============================================================
CREATE TABLE IF NOT EXISTS entity_mentions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id       TEXT NOT NULL REFERENCES entities(entity_id),
    item_id         UUID NOT NULL REFERENCES items(id),
    context_snippet TEXT,
    layer_hint      TEXT,
    role_hint       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- events – structured ConstraintEvent extracted from items
-- ============================================================
CREATE TABLE IF NOT EXISTS events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id             UUID NOT NULL REFERENCES items(id),
    event_type          TEXT NOT NULL
                        CHECK (event_type IN (
                            'LEAD_TIME_EXTENDED', 'ALLOCATION', 'PRICE_INCREASE',
                            'CAPEX_ANNOUNCED', 'CAPACITY_ONLINE', 'QUALIFICATION_DELAY',
                            'YIELD_ISSUE', 'DISRUPTION', 'POLICY_RESTRICTION'
                        )),
    constraint_layer    TEXT NOT NULL,
    secondary_layer     TEXT,
    direction           TEXT NOT NULL
                        CHECK (direction IN ('TIGHTENING', 'EASING', 'MIXED')),
    entities            JSONB NOT NULL DEFAULT '[]',
    objects             JSONB NOT NULL DEFAULT '[]',
    magnitude           JSONB NOT NULL DEFAULT '{}',
    timing              JSONB NOT NULL DEFAULT '{}',
    evidence            JSONB NOT NULL DEFAULT '{}',
    tags                TEXT[] NOT NULL DEFAULT '{}',
    confidence          REAL NOT NULL DEFAULT 0.5,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- pipeline_runs – audit log for batch executions
-- ============================================================
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stage           TEXT NOT NULL
                    CHECK (stage IN (
                        'collect', 'normalize', 'link',
                        'extract', 'theme_cycle', 'alert_triage'
                    )),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    items_processed INT NOT NULL DEFAULT 0,
    items_errored   INT NOT NULL DEFAULT 0,
    notes           TEXT
);

-- ============================================================
-- Indexes
-- ============================================================

-- sources
CREATE INDEX IF NOT EXISTS idx_sources_source_id     ON sources (source_id);
CREATE INDEX IF NOT EXISTS idx_sources_status         ON sources (status);
CREATE INDEX IF NOT EXISTS idx_sources_fetch_method   ON sources (fetch_method);

-- items
CREATE INDEX IF NOT EXISTS idx_items_pipeline_status  ON items (pipeline_status);
CREATE INDEX IF NOT EXISTS idx_items_source_id        ON items (source_id);
CREATE INDEX IF NOT EXISTS idx_items_url_hash         ON items (url_hash);
CREATE INDEX IF NOT EXISTS idx_items_content_hash     ON items (content_hash);
CREATE INDEX IF NOT EXISTS idx_items_fetched_at       ON items (fetched_at);

-- entities
CREATE INDEX IF NOT EXISTS idx_entities_entity_id     ON entities (entity_id);
CREATE INDEX IF NOT EXISTS idx_entities_status        ON entities (status);
CREATE INDEX IF NOT EXISTS idx_entities_type          ON entities (type);

-- entity_mentions
CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity_id ON entity_mentions (entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_item_id   ON entity_mentions (item_id);

-- events
CREATE INDEX IF NOT EXISTS idx_events_constraint_layer ON events (constraint_layer);
CREATE INDEX IF NOT EXISTS idx_events_event_type       ON events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_direction        ON events (direction);
CREATE INDEX IF NOT EXISTS idx_events_created_at       ON events (created_at);
CREATE INDEX IF NOT EXISTS idx_events_item_id          ON events (item_id);

COMMIT;
