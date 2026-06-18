-- Migration 008: public-facing submission tables
-- contact_inquiry      — landing page contact form
-- self_service_application — org self-registration
-- org_registration_otp — ephemeral OTP tokens (email verification)

CREATE TABLE IF NOT EXISTS contact_inquiry (
  id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  name          VARCHAR(100) NOT NULL,
  email         VARCHAR(150) NOT NULL,
  org           VARCHAR(200),
  enquiry_type  VARCHAR(50),
  message       TEXT,
  status        VARCHAR(20)  NOT NULL DEFAULT 'NEW',   -- NEW | REVIEWED | REPLIED
  ip_address    INET,
  submitted_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contact_inquiry_submitted ON contact_inquiry (submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_contact_inquiry_status    ON contact_inquiry (status);

-- ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS self_service_application (
  id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  org_name        VARCHAR(200) NOT NULL,
  domain          VARCHAR(100) NOT NULL,
  entity_type     VARCHAR(50),
  industry        VARCHAR(50),
  headcount_band  VARCHAR(20),
  contact_name    VARCHAR(100) NOT NULL,
  contact_email   VARCHAR(150) NOT NULL,
  contact_mobile  VARCHAR(20),
  message         TEXT,
  how_heard       VARCHAR(50),
  agreed_to_dpa   BOOLEAN      NOT NULL DEFAULT FALSE,
  email_verified  BOOLEAN      NOT NULL DEFAULT FALSE,
  status          VARCHAR(20)  NOT NULL DEFAULT 'PENDING', -- PENDING | REVIEWED | APPROVED | REJECTED
  review_notes    TEXT,
  submitted_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  reviewed_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ssa_submitted ON self_service_application (submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_ssa_status    ON self_service_application (status);
CREATE INDEX IF NOT EXISTS idx_ssa_email     ON self_service_application (contact_email);

-- ─────────────────────────────────────────────────────────────────
-- Ephemeral OTP tokens — row expires and is deleted post-verify.
-- Redis is preferred in production; this table is a fallback for
-- environments where Redis TTL cannot be relied on.

CREATE TABLE IF NOT EXISTS org_registration_otp (
  token       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  email       VARCHAR(150) NOT NULL,
  otp_hash    VARCHAR(64)  NOT NULL,   -- SHA-256(otp) — never store plaintext
  form_data   JSONB,                   -- partial form captured at init step
  expires_at  TIMESTAMPTZ  NOT NULL,
  verified    BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reg_otp_email ON org_registration_otp (email);
