-- 002_themes_alerts.sql
-- Add themes, theme_events, and alerts tables.

BEGIN;

-- ============================================================
-- themes — bottleneck clusters with living thesis
-- ============================================================
CREATE TABLE IF NOT EXISTS themes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    theme_id            TEXT UNIQUE NOT NULL,          -- e.g. "T:ai_constraints:hbm_allocation"
    name                TEXT NOT NULL,
    constraint_layer    TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'CANDIDATE'
                        CHECK (status IN ('CANDIDATE', 'ACTIVE', 'MATURE', 'FADING')),
    tightening_score    REAL NOT NULL DEFAULT 0.0,
    velocity_score      REAL NOT NULL DEFAULT 0.0,
    breadth_score       REAL NOT NULL DEFAULT 0.0,
    quality_score       REAL NOT NULL DEFAULT 0.0,
    allocation_score    REAL NOT NULL DEFAULT 0.0,
    novelty_score       REAL NOT NULL DEFAULT 0.0,
    thesis              JSONB NOT NULL DEFAULT '{}',
    event_count         INT NOT NULL DEFAULT 0,
    tightening_count    INT NOT NULL DEFAULT 0,
    easing_count        INT NOT NULL DEFAULT 0,
    unique_entities     INT NOT NULL DEFAULT 0,
    unique_sources      INT NOT NULL DEFAULT 0,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- theme_events — link table (theme <-> events)
-- ============================================================
CREATE TABLE IF NOT EXISTS theme_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    theme_id    TEXT NOT NULL REFERENCES themes(theme_id),
    event_id    UUID NOT NULL REFERENCES events(id),
    weight      REAL NOT NULL DEFAULT 1.0,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (theme_id, event_id)
);

-- ============================================================
-- alerts — sent alerts with dedup
-- ============================================================
CREATE TABLE IF NOT EXISTS alerts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_type          TEXT NOT NULL
                        CHECK (alert_type IN (
                            'NEW_CANDIDATE', 'INFLECTION', 'ACTIONABLE_BRIEFING',
                            'DAILY_DIGEST', 'NEW_ENTITY_DISCOVERED'
                        )),
    theme_id            TEXT,
    payload             JSONB NOT NULL DEFAULT '{}',
    telegram_message_id TEXT,
    sent_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    dedup_key           TEXT UNIQUE            -- for alert dedup (type + theme + time window)
);

-- ============================================================
-- Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_themes_theme_id          ON themes (theme_id);
CREATE INDEX IF NOT EXISTS idx_themes_status             ON themes (status);
CREATE INDEX IF NOT EXISTS idx_themes_constraint_layer   ON themes (constraint_layer);
CREATE INDEX IF NOT EXISTS idx_themes_tightening_score   ON themes (tightening_score DESC);

CREATE INDEX IF NOT EXISTS idx_theme_events_theme_id    ON theme_events (theme_id);
CREATE INDEX IF NOT EXISTS idx_theme_events_event_id    ON theme_events (event_id);

CREATE INDEX IF NOT EXISTS idx_alerts_alert_type        ON alerts (alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_theme_id          ON alerts (theme_id);
CREATE INDEX IF NOT EXISTS idx_alerts_sent_at           ON alerts (sent_at);
CREATE INDEX IF NOT EXISTS idx_alerts_dedup_key         ON alerts (dedup_key);

COMMIT;
