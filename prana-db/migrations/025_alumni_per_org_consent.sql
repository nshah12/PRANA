-- Migration 025: Per-org alumni consent
-- Replaces the global alumni_visibility purpose in employee_consent.
-- Employee explicitly opts in per past employer — and controls whether to share mobile + email.
-- CHRO of that org can then see full contact details and download a CSV.

CREATE TABLE alumni_consent (
  consent_id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_user_id  UUID         NOT NULL REFERENCES employee_user(employee_user_id) ON DELETE CASCADE,
  tenant_id         UUID         NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
  granted           BOOLEAN      NOT NULL DEFAULT FALSE,
  share_mobile      BOOLEAN      NOT NULL DEFAULT TRUE,
  share_email       BOOLEAN      NOT NULL DEFAULT TRUE,
  granted_at        TIMESTAMPTZ,
  withdrawn_at      TIMESTAMPTZ,
  updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_alumni_consent UNIQUE (employee_user_id, tenant_id)
);

CREATE INDEX idx_alumni_consent_emp    ON alumni_consent(employee_user_id);
CREATE INDEX idx_alumni_consent_tenant ON alumni_consent(tenant_id) WHERE granted = TRUE;

-- Drop old alumni_outreach table and recreate without consent_id dependency
-- (it already linked via employee_user_id + tenant_id — no FK to old consent row)
-- No structural change needed to alumni_outreach.

COMMENT ON TABLE alumni_consent IS
  'Per-employer alumni visibility consent. Employee explicitly grants each past employer '
  'access to their contact details (mobile, email) for rehiring/network outreach. '
  'DPDP-controlled: employee can withdraw at any time. Withdrawal is immediate — '
  'CHRO list for that tenant no longer includes the employee on next query.';
