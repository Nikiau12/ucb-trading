ALTER TABLE signal_lifecycle
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;

ALTER TABLE signal_lifecycle
    ADD COLUMN IF NOT EXISTS entry_path_checked_at TIMESTAMPTZ;

ALTER TABLE signal_lifecycle
    DROP CONSTRAINT IF EXISTS signal_lifecycle_status_check;

ALTER TABLE signal_lifecycle
    ADD CONSTRAINT signal_lifecycle_status_check
    CHECK (status IN (
        'replay_pending', 'waiting_entry', 'active', 'tp1_reached',
        'tp2_reached', 'stopped', 'expired', 'cancelled_before_entry'
    ));

ALTER TABLE signal_update_deliveries
    DROP CONSTRAINT IF EXISTS signal_update_deliveries_event_type_check;

ALTER TABLE signal_update_deliveries
    ADD CONSTRAINT signal_update_deliveries_event_type_check
    CHECK (event_type IN (
        'tp1_reached', 'stop_reached', 'cancelled_before_entry'
    ));

-- Force one minute-level historical audit for every setup that is still
-- waiting when this release is deployed.
UPDATE signal_lifecycle
SET entry_path_checked_at = NULL
WHERE status = 'waiting_entry';
