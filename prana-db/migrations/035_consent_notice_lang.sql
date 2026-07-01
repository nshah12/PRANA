-- 035_consent_notice_lang.sql
-- Adds DPDP Act Section 5(3) audit columns to employee_consent.
-- Section 5(3) requires consent notices to be available in all 22 scheduled languages.
-- notice_language records which language the employee was shown.
-- notice_hash is SHA-256 of the exact rendered notice text — proves what was agreed to.

ALTER TABLE employee_consent
  ADD COLUMN notice_language CHAR(5)     NOT NULL DEFAULT 'en',
  ADD COLUMN notice_hash     VARCHAR(64);

-- notice_language: BCP 47 tag — 'en', 'hi', 'te', 'ta', 'mr', 'bn', 'gu', etc.
-- notice_hash: nullable for existing rows (pre-migration consents); required for new ones.
