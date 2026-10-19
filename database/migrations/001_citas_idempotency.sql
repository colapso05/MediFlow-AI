ALTER TABLE citas
    ADD COLUMN IF NOT EXISTS idempotency_key UUID;

ALTER TABLE citas
    ADD COLUMN IF NOT EXISTS idempotency_fingerprint CHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS citas_idempotency_key_idx
    ON citas (idempotency_key)
    WHERE idempotency_key IS NOT NULL;