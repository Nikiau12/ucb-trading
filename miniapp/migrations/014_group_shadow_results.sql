-- One exchange-independent, modelled result per signal and accounting version.
-- This does not update signals, lifecycle decisions, subscriptions or orders.
CREATE TABLE IF NOT EXISTS group_shadow_results (
    signal_id BIGINT NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    model_version TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    catalog_version TEXT NOT NULL,
    asset_group TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('long', 'short')),
    signal_created_at TIMESTAMPTZ NOT NULL,
    lifecycle_updated_at TIMESTAMPTZ NOT NULL,
    lifecycle_status TEXT NOT NULL,
    entered_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    outcome TEXT NOT NULL,
    cost_status TEXT NOT NULL,
    gross_r NUMERIC,
    slippage_r NUMERIC,
    fee_r NUMERIC,
    funding_r NUMERIC,
    net_r NUMERIC,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    retry_after TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (signal_id, model_version)
);

CREATE INDEX IF NOT EXISTS group_shadow_results_group_idx
    ON group_shadow_results (strategy_version, catalog_version, asset_group, side, signal_created_at);

CREATE INDEX IF NOT EXISTS group_shadow_results_retry_idx
    ON group_shadow_results (retry_after) WHERE retry_after IS NOT NULL;
