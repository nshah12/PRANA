-- 034_pan_token_version.sql
-- Adds pan_token_version to both tables that store pan_token.
-- All existing rows receive version=1 (current HMAC-SHA256 scheme).
-- When platform_secret is rotated, a new version integer is introduced and
-- pan_token_version is updated lazily on next employee login, avoiding a
-- table-locking mass-recompute of all pan_token values.

ALTER TABLE employee_user
  ADD COLUMN pan_token_version SMALLINT NOT NULL DEFAULT 1;

ALTER TABLE employee_master
  ADD COLUMN pan_token_version SMALLINT NOT NULL DEFAULT 1;
