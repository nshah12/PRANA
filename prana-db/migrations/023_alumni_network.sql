-- Migration 023: Alumni Network
-- Adds alumni consent tracking and outreach message log.
-- employee_consent already has purpose column — alumni_visibility is a new purpose value.
-- No schema change to employee_consent needed.

-- Outreach messages: CHRO → alumni (brokered via PRANA, employee never exposes contact)
CREATE TABLE IF NOT EXISTS alumni_outreach (
  outreach_id       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         UUID         NOT NULL REFERENCES tenant(tenant_id),
  employee_uuid     UUID         NOT NULL REFERENCES employee_master(employee_uuid),
  employee_user_id  UUID         NOT NULL REFERENCES employee_user(employee_user_id),
  sent_by_oa_user   UUID         NOT NULL REFERENCES oa_user(oa_user_id),
  subject           VARCHAR(200) NOT NULL,
  body_text         TEXT         NOT NULL,
  -- body_text is plain text; no HTML injection vector
  status            VARCHAR(20)  NOT NULL DEFAULT 'SENT',
                    -- SENT | READ | REPLIED | IGNORED | OPTED_OUT
  sent_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  read_at           TIMESTAMPTZ,
  replied_at        TIMESTAMPTZ,
  CONSTRAINT chk_outreach_status CHECK (status IN ('SENT','READ','REPLIED','IGNORED','OPTED_OUT')),
  CONSTRAINT chk_outreach_body   CHECK (LENGTH(body_text) <= 2000)
);
CREATE INDEX idx_alumni_outreach_tenant   ON alumni_outreach(tenant_id, sent_at DESC);
CREATE INDEX idx_alumni_outreach_employee ON alumni_outreach(employee_user_id, sent_at DESC);

-- Track how many outreach messages per tenant per employee per 30-day window
-- (enforced in application, index supports the count query)
CREATE INDEX idx_alumni_outreach_window
  ON alumni_outreach(tenant_id, employee_user_id, sent_at DESC);

-- New consent purposes (documented; employee_consent table already accepts free-text purpose)
-- purpose = 'alumni_visibility'      : employee opts in to CHRO seeing their alumni profile
-- purpose = 'peer_benchmark'         : already planned; used for comp bands
-- purpose = 'gender_equity_signal'   : future; separate sensitive-data consent

COMMENT ON TABLE alumni_outreach IS
  'CHRO-to-alumni messages brokered by PRANA. Employee contact details never exposed to CHRO.';
