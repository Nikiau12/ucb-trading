-- Additive migration. History and existing calculation parameters are preserved.
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS signal_groups JSONB;

CREATE TABLE IF NOT EXISTS bingx_accounts (
    telegram_user_id BIGINT PRIMARY KEY REFERENCES user_profiles(telegram_user_id),
    credentials TEXT NOT NULL,
    key_hint TEXT NOT NULL,
    balance NUMERIC,
    balance_checked_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_trade_tracking (
    telegram_user_id BIGINT NOT NULL,
    signal_id BIGINT NOT NULL REFERENCES signals(id),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'exited')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    exited_at TIMESTAMPTZ,
    position_id TEXT,
    tp1_order_id TEXT,
    execution_checked_at TIMESTAMPTZ,
    execution_state TEXT NOT NULL DEFAULT 'unverified',
    PRIMARY KEY (telegram_user_id, signal_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_tracked_market_side_per_user
    ON user_trade_tracking (telegram_user_id, symbol, side) WHERE status = 'active';

ALTER TABLE signal_update_deliveries DROP CONSTRAINT IF EXISTS signal_update_deliveries_event_type_check;
ALTER TABLE signal_update_deliveries ADD CONSTRAINT signal_update_deliveries_event_type_check
    CHECK (event_type IN ('tp1_reached','tp2_reached','stop_reached','cancelled_before_entry','tp1_filled'));

-- Receiving a signal is not consent to ongoing trade notifications.
UPDATE signal_update_deliveries SET status='sent', last_error='tracking_opt_in_required'
    WHERE status IN ('pending','failed');
