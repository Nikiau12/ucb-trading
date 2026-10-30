CREATE TABLE IF NOT EXISTS bingx_referrals (
    telegram_user_id BIGINT PRIMARY KEY,
    bingx_uid TEXT NOT NULL CHECK (bingx_uid ~ '^[0-9]{6,20}$'),
    referral_code TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'verified', 'rejected')),
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    reviewed_by BIGINT
);

CREATE UNIQUE INDEX IF NOT EXISTS bingx_referrals_uid_code_unique
    ON bingx_referrals (bingx_uid, referral_code);

CREATE INDEX IF NOT EXISTS bingx_referrals_status_submitted_idx
    ON bingx_referrals (status, submitted_at);
