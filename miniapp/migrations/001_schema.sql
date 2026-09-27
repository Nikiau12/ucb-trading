CREATE TABLE IF NOT EXISTS user_profiles (
    telegram_user_id BIGINT PRIMARY KEY,
    language TEXT NOT NULL DEFAULT 'en',
    deposit NUMERIC,
    risk_pct NUMERIC NOT NULL DEFAULT 1,
    leverage NUMERIC NOT NULL DEFAULT 10,
    margin TEXT NOT NULL DEFAULT 'cross',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS subscriptions (
    telegram_user_id BIGINT PRIMARY KEY,
    trial_used INTEGER NOT NULL DEFAULT 0,
    paid_until TIMESTAMPTZ,
    payment_status TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS last_trial_signal_at TIMESTAMPTZ;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS paywall_sent BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS signals (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    confidence NUMERIC NOT NULL,
    price NUMERIC,
    entry NUMERIC,
    stop NUMERIC,
    tp1 NUMERIC,
    tp2 NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE signals ADD COLUMN IF NOT EXISTS price_unit NUMERIC;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS contract_size NUMERIC;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS vol_unit NUMERIC;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS min_vol NUMERIC;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS max_vol NUMERIC;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS max_leverage NUMERIC;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'scanner';

CREATE INDEX IF NOT EXISTS signals_created_at_idx ON signals (created_at DESC);
CREATE INDEX IF NOT EXISTS signals_source_created_idx ON signals (source, created_at DESC);

CREATE TABLE IF NOT EXISTS user_signal_access (
    telegram_user_id BIGINT NOT NULL,
    signal_id BIGINT NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (telegram_user_id, signal_id)
);

CREATE TABLE IF NOT EXISTS runtime_health (
    component TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_success_at TIMESTAMPTZ,
    last_error_at TIMESTAMPTZ,
    duration_seconds NUMERIC,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS signal_alert_state (
    symbol TEXT PRIMARY KEY,
    side TEXT NOT NULL,
    confidence NUMERIC NOT NULL,
    entry NUMERIC,
    stop NUMERIC,
    tp1 NUMERIC,
    tp2 NUMERIC,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payment_claims (
    tx_hash TEXT PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payment_invoices (
    id BIGSERIAL PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL,
    expected_amount NUMERIC(20, 6) NOT NULL,
    base_amount NUMERIC(20, 6) NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    tx_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    paid_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS payment_invoices_one_open
    ON payment_invoices (telegram_user_id)
    WHERE status = 'open';

CREATE UNIQUE INDEX IF NOT EXISTS payment_invoices_open_amount
    ON payment_invoices (expected_amount)
    WHERE status = 'open';

CREATE TABLE IF NOT EXISTS access_state (
    id INTEGER PRIMARY KEY,
    data JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS fsm_storage (
    bot_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    thread_id BIGINT NOT NULL DEFAULT 0,
    business_connection_id TEXT NOT NULL DEFAULT '',
    destiny TEXT NOT NULL DEFAULT 'default',
    state TEXT,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (bot_id, chat_id, user_id, thread_id, business_connection_id, destiny)
);

CREATE TABLE IF NOT EXISTS scanner_cooldowns (
    kind TEXT NOT NULL,
    alert_key TEXT NOT NULL,
    last_sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (kind, alert_key)
);
