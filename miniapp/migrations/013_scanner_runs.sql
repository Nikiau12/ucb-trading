-- Operational diagnostics only. No UPDATE/DELETE of existing trades or users.
CREATE TABLE IF NOT EXISTS scanner_runs (
    run_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    strategy_version TEXT NOT NULL,
    catalog_version TEXT NOT NULL,
    summary JSONB NOT NULL,
    decisions JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS scanner_runs_started_at_idx ON scanner_runs (started_at);
