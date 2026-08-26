-- Minimal schema: raw data + KPI snapshots (calculated, not stored precomputed
-- per-metric other than the snapshot cache) + documents + feedback + audit + telemetry.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS branches (
    branch_id   TEXT PRIMARY KEY,
    branch_name TEXT NOT NULL,
    region      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relationship_managers (
    rm_id      TEXT PRIMARY KEY,
    rm_name    TEXT NOT NULL,
    branch_id  TEXT NOT NULL REFERENCES branches(branch_id)
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id   TEXT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    rm_id         TEXT NOT NULL REFERENCES relationship_managers(rm_id),
    branch_id     TEXT NOT NULL REFERENCES branches(branch_id),
    segment       TEXT NOT NULL,          -- e.g. mass, affluent, platinum
    status        TEXT NOT NULL,          -- active, churned, dormant
    onboarded_on  TEXT NOT NULL,
    income_band   TEXT                    -- sensitive; admin-only field
);

CREATE TABLE IF NOT EXISTS product_holdings (
    holding_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id  TEXT NOT NULL REFERENCES customers(customer_id),
    product_code TEXT NOT NULL,           -- e.g. credit_card, salary_account, platinum_edge
    opened_on    TEXT NOT NULL,
    closed_on    TEXT
);

CREATE TABLE IF NOT EXISTS leads (
    lead_id      TEXT PRIMARY KEY,
    customer_id  TEXT NOT NULL REFERENCES customers(customer_id),
    rm_id        TEXT NOT NULL REFERENCES relationship_managers(rm_id),
    branch_id    TEXT NOT NULL REFERENCES branches(branch_id),
    product_code TEXT NOT NULL,
    status       TEXT NOT NULL,           -- open, converted, lost
    created_on   TEXT NOT NULL,
    updated_on   TEXT NOT NULL,
    value_estimate REAL
);

CREATE TABLE IF NOT EXISTS revenue_transactions (
    txn_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id      TEXT NOT NULL REFERENCES customers(customer_id),
    branch_id        TEXT NOT NULL REFERENCES branches(branch_id),
    rm_id            TEXT NOT NULL REFERENCES relationship_managers(rm_id),
    product_code     TEXT NOT NULL,
    product_category TEXT NOT NULL,       -- cross_sell, core, fee
    txn_date         TEXT NOT NULL,       -- YYYY-MM-DD
    month            TEXT NOT NULL,       -- YYYY-MM
    amount           REAL NOT NULL,
    volume_units     INTEGER NOT NULL DEFAULT 1,
    unit_price       REAL
);

CREATE TABLE IF NOT EXISTS kpi_snapshots (
    snapshot_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    kpi_key      TEXT NOT NULL,
    branch_id    TEXT,
    month        TEXT NOT NULL,
    value        REAL NOT NULL,
    computed_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id       TEXT PRIMARY KEY,
    source_type  TEXT NOT NULL,           -- matches config/source_registry.yaml keys
    title        TEXT NOT NULL,
    body         TEXT NOT NULL,
    branch_id    TEXT,
    rm_id        TEXT,
    customer_id  TEXT,
    product_code TEXT,
    driver_tags  TEXT,                    -- comma-separated keywords for scoped retrieval
    created_on   TEXT NOT NULL,
    access_level TEXT NOT NULL DEFAULT 'standard'  -- standard | sensitive
);

CREATE TABLE IF NOT EXISTS feedback (
    feedback_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    insight_ref  TEXT NOT NULL,           -- e.g. "cross_sell_revenue|2026-06|BR-01"
    user_id      TEXT NOT NULL,
    useful       INTEGER NOT NULL,        -- 1 / 0
    reason       TEXT,
    created_on   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      TEXT NOT NULL,
    action       TEXT NOT NULL,
    resource     TEXT NOT NULL,
    result       TEXT NOT NULL,           -- ALLOWED / DENIED
    reason       TEXT,
    created_on   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telemetry_log (
    telemetry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage        TEXT NOT NULL,           -- e.g. detect, attribute, llm_narrative
    duration_ms  REAL NOT NULL,
    model        TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    est_cost_usd REAL,
    created_on   TEXT NOT NULL
);
