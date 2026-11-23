-- Only future lifecycle transitions populate this reason; do not amend history.
ALTER TABLE signal_lifecycle ADD COLUMN IF NOT EXISTS cancellation_reason TEXT;

CREATE INDEX IF NOT EXISTS user_signal_access_signal_recipient_idx
    ON user_signal_access (signal_id, telegram_user_id);
