-- Migration 012: device_registration table for mobile trust-based biometric auth
-- device_credential (existing) is reserved for future FIDO2/WebAuthn.
-- device_registration is the simpler trust model: OS handles biometric, we trust the result.

CREATE TABLE IF NOT EXISTS device_registration (
  device_id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id     UUID         NOT NULL REFERENCES employee_user(employee_user_id) ON DELETE CASCADE,
  platform             VARCHAR(10)  NOT NULL CHECK (platform IN ('ANDROID', 'IOS')),
  device_name          VARCHAR(100),
  device_fingerprint   VARCHAR(128),                          -- SHA-256 of device identifiers
  push_token           TEXT,                                   -- FCM / APNs token
  biometric_enrolled   BOOLEAN      NOT NULL DEFAULT FALSE,
  enrolled_at          TIMESTAMPTZ,
  last_used_at         TIMESTAMPTZ,
  registered_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  revoked              BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_dr_employee ON device_registration(employee_user_id) WHERE revoked = FALSE;
CREATE INDEX IF NOT EXISTS idx_dr_fingerprint ON device_registration(device_fingerprint) WHERE revoked = FALSE;

-- ROLLBACK:
-- DROP TABLE IF EXISTS device_registration;
