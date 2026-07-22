-- Migration 037: AUTO_DETECT scoring improvements — usage frequency + signal weighting
--
-- PURPOSE:
--   usage_count     — bumped each time a manifest's doc_type is confirmed via
--                      successful pipeline routing (prana-api's internal
--                      /internal/pipeline/routed callback). Used to tie-break
--                      AUTO_DETECT scoring toward doc_types this tenant
--                      actually handles most often, and to order/cap the
--                      manifest set considered per detection attempt.
--
--   signal_weights  — parallel array to classification_signals giving each
--                      signal group a relative discriminative weight (e.g. a
--                      signal combining "uan_number" + "pf_number" is far more
--                      specific to PF_ACKNOWLEDGEMENT than a generic
--                      "employee_name" + "employer_name" pair, but both fired
--                      equally under the old unweighted scoring).
--                      Empty array (default) == all signals weighted equally
--                      (1.0) — fully backward compatible with existing rows.
--
-- ROLLBACK:
--   ALTER TABLE doc_type_field_manifest DROP COLUMN IF EXISTS usage_count;
--   ALTER TABLE doc_type_field_manifest DROP COLUMN IF EXISTS signal_weights;
--   DROP INDEX IF EXISTS idx_manifest_usage;

ALTER TABLE doc_type_field_manifest
  ADD COLUMN IF NOT EXISTS usage_count    INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS signal_weights JSONB   NOT NULL DEFAULT '[]';

CREATE INDEX IF NOT EXISTS idx_manifest_usage
  ON doc_type_field_manifest (tenant_id, usage_count DESC);
