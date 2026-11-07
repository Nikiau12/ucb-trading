-- Additive only: existing signals and their lifecycle deadlines are untouched.
ALTER TABLE signals ADD COLUMN IF NOT EXISTS strategy_metadata JSONB;
CREATE UNIQUE INDEX IF NOT EXISTS signals_group_decision_unique
    ON signals ((strategy_metadata->>'version'), (strategy_metadata->>'decision_key'))
    WHERE strategy_metadata->>'decision_key' IS NOT NULL;
