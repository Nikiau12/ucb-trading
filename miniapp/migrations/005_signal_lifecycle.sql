CREATE TABLE IF NOT EXISTS signal_lifecycle (
    signal_id BIGINT PRIMARY KEY REFERENCES signals(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'waiting_entry',
    entry_expires_at TIMESTAMPTZ NOT NULL,
    holding_expires_at TIMESTAMPTZ,
    max_holding_seconds INTEGER NOT NULL DEFAULT 604800,
    entry_hit_at TIMESTAMPTZ,
    tp1_hit_at TIMESTAMPTZ,
    tp2_hit_at TIMESTAMPTZ,
    stop_hit_at TIMESTAMPTZ,
    expired_at TIMESTAMPTZ,
    last_price NUMERIC,
    last_checked_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (status IN ('replay_pending', 'waiting_entry', 'active', 'tp1_reached', 'tp2_reached', 'stopped', 'expired'))
);

CREATE INDEX IF NOT EXISTS signal_lifecycle_active_idx
    ON signal_lifecycle (status, entry_expires_at, holding_expires_at);

CREATE TABLE IF NOT EXISTS signal_update_deliveries (
    signal_id BIGINT NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    telegram_user_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    PRIMARY KEY (signal_id, telegram_user_id, event_type),
    CHECK (event_type IN ('tp1_reached')),
    CHECK (status IN ('pending', 'sent', 'failed'))
);

CREATE INDEX IF NOT EXISTS signal_update_deliveries_pending_idx
    ON signal_update_deliveries (status, next_attempt_at)
    WHERE status IN ('pending', 'failed');

INSERT INTO signal_lifecycle (
    signal_id, status, entry_expires_at, max_holding_seconds
)
SELECT
    s.id,
    'replay_pending',
    s.created_at + INTERVAL '12 hours',
    1209600
FROM signals s
WHERE s.source IN ('scanner', 'manual')
  AND s.created_at >= NOW() - INTERVAL '14 days'
  AND s.entry IS NOT NULL
  AND s.stop IS NOT NULL
  AND s.tp1 IS NOT NULL
  AND s.tp2 IS NOT NULL
  AND EXISTS (
      SELECT 1 FROM user_signal_access a WHERE a.signal_id = s.id
  )
ON CONFLICT (signal_id) DO NOTHING;
