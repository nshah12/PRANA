-- Migration 038: Employee record merge/dedupe support
--
-- PURPOSE:
--   merged_into — set on a duplicate employee_user row once PA merges it into
--                 a canonical employee_user_id (e.g. a PAN-typo led to two
--                 identities for the same physical person). The duplicate row
--                 is never deleted (7-year audit trail, FK history) — it is
--                 marked status='MERGED' with merged_into pointing at the
--                 surviving canonical row. All other tables that referenced
--                 the duplicate's employee_user_id are re-pointed to the
--                 canonical id as part of the same merge transaction.
--
-- ROLLBACK:
--   ALTER TABLE employee_user DROP COLUMN IF EXISTS merged_into;
--   DROP INDEX IF EXISTS idx_eu_merged_into;

ALTER TABLE employee_user
  ADD COLUMN IF NOT EXISTS merged_into UUID REFERENCES employee_user(employee_user_id);

CREATE INDEX IF NOT EXISTS idx_eu_merged_into
  ON employee_user (merged_into) WHERE merged_into IS NOT NULL;
