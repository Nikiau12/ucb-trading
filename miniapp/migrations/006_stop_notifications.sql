ALTER TABLE signal_update_deliveries
    DROP CONSTRAINT IF EXISTS signal_update_deliveries_event_type_check;

ALTER TABLE signal_update_deliveries
    ADD CONSTRAINT signal_update_deliveries_event_type_check
    CHECK (event_type IN ('tp1_reached', 'stop_reached'));
