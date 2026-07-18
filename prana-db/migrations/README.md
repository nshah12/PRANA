# prana-db/migrations/ — historical reference only

**These files are no longer authoritative and no longer run against any
environment.** `prana-db/schema.sql` is the single source of truth for the
database schema. Every table, column, and index these files ever added has
been folded into `schema.sql` directly (see its "LAYER 15: RECONCILIATION
(2026-07-18)" section for the batch that was reconciled in one pass, plus
earlier ad-hoc edits made directly to `schema.sql` over time).

## Why this directory stopped being used

No migration runner ever existed in this codebase — `prana-db/db-init.sh`
(the actual dev bootstrap, invoked by `docker-compose`'s `db-init` service)
only ever ran `schema.sql` plus three seed files. It never touched this
directory. `prana-api/main.py` has no migration-running code either, despite
`prana-db/CLAUDE.md` historically claiming migrations run at API startup —
that was aspirational documentation, not real behavior.

Meanwhile `schema.sql` was edited directly, in place, every time a feature
needed a new table or column. The two sources drifted for a long time: some
migration files described tables that no longer matched what `schema.sql`
actually created (different column names, different status enums — e.g.
`dpdp_grievance` and `salary_band`), and some genuinely-new tables (e.g.
`service_incident`, `notification_log`, `contact_inquiry`) were never added
to `schema.sql` at all, so they silently didn't exist on any freshly
initialized database.

This surfaced for real on 2026-07-18: after a DB volume wipe and
reinitialization via `db-init.sh`, Portal Admin's `GET /admin/tenants` and
`GET /admin/incidents` both returned 500 (`tenant.industry` and
`service_incident` didn't exist). Tracing that back led to applying every
migration file here against the live DB one at a time, discovering the full
extent of the drift, and folding the net-new, still-needed pieces into
`schema.sql` — which is recorded below.

## Per-file reconciliation status

| File | Status |
|------|--------|
| `001_initial_schema.sql` | Superseded — this is the original full-schema baseline; `schema.sql` already covers everything in it (and more). Never re-run. |
| `002_chro_cfo_tables.sql` | Folded in — `compliance_obligation`/`insight_cache`/`storage_request` already existed; `employee_user.consent_status` already existed. |
| `003_dpdp_compliance.sql` | Superseded — `schema.sql`'s `dpdp_grievance` was independently redesigned (`raised_at`/`RAISED..ESCALATED_TO_DPB` instead of this file's `opened_at`/`OPEN..CLOSED`). Consent tracking superseded by the separate `employee_consent` table (per-tenant, per-purpose model). |
| `004_career_insights.sql` | Partially folded in — `career_event.insight_generated_at`/`insight_model_version` added to `schema.sql` LAYER 15. `salary_band` in `schema.sql` was independently redesigned (`p25`/`p50`/`p75`/`sample_count` instead of this file's `p25_index`/`cohort_size`/etc.) — not applicable. |
| `005_document_access_log_index.sql` | Superseded — `document_access_log` in `schema.sql` uses `accessed_at`, not this file's `occurred_at`; equivalent indexes (`idx_dal_employee`, `idx_dal_tenant`, etc.) already exist under different names. |
| `006_missing_partitioned_tables_dev.sql` | Superseded — described non-partitioned dev fallbacks for `audit_event`/`anomaly_event`; `schema.sql` now creates them properly partitioned with real dev partitions (see LAYER 9 fix below). |
| `007_tenant_enterprise_profile.sql` | Folded in — `schema.sql` LAYER 15 (`tenant.industry`, `.sla_tier`, `.brand_name`, etc.). **This is the fix for the original `/admin/tenants` 500.** |
| `008_public_submissions.sql` | Folded in — `contact_inquiry`, `self_service_application`, `org_registration_otp` added to `schema.sql` LAYER 15. |
| `009_document_comment.sql` | Superseded — `document.upload_comment`/`.original_filename` already existed in `schema.sql`. |
| `010_chro_report.sql` | Superseded — `chro_report` already existed in `schema.sql`. |
| `011_service_incidents.sql` | Folded in — `service_incident` added to `schema.sql` LAYER 15. **This is the fix for the original `/admin/incidents` 500.** |
| `012_employee_device_auth.sql` | Folded in — `device_registration` added to `schema.sql` LAYER 15. |
| `013_hrms_connector_config.sql` | Superseded — `hrms_connector_config` and its indexes already existed in `schema.sql`. |
| `014_chro_audit_grade.sql` | Folded in — `compliance_obligation` statutory columns + 4 CHRO alert `platform_config` keys added to `schema.sql` LAYER 15 (column name fixed: this file's `default_value` → the table's real `config_value`). |
| `015_digest_query_indexes.sql` | Superseded — equivalent indexes on `document`/`document_access_log` already exist under different names in `schema.sql`. |
| `016_tenant_profile_fields.sql` | Duplicate of `007` — same columns, already folded in once. |
| `017_notification_incident_tables.sql` | Folded in — `notification_log` and `incident` added to `schema.sql` LAYER 15. |
| `018_doc_type_field_manifest.sql` | Folded in — `doc_type_field_manifest` added to `schema.sql` LAYER 15 (`unclassified_queue` already existed separately). |
| `019_dpdp_compliance_tables.sql` | Superseded — `employee_consent` already existed; `compliance_obligation` columns it adds were already covered by `014`'s fold-in. |
| `020_employee_doc_types.sql` | Data-only, already applied directly to the live DB (4 platform-default `doc_type_field_manifest` rows for BONUS_LETTER/GRATUITY_LETTER/FORM_12B/FORM_26AS; column name fixed: `min_confidence_threshold` → the table's real `confidence_threshold`). Not re-seeded by `schema.sql` — re-seed manually if a fresh DB needs these 4 rows. |
| `021_unclassified_queue.sql` | Superseded — `unclassified_queue` already existed in `schema.sql`. |
| `022_api_key_kong_flag.sql` | Superseded — `api_key.kong_consumer_registered` already existed. |
| `023_alumni_network.sql` | Folded in — `alumni_outreach` added to `schema.sql` LAYER 15. |
| `024_comp_benchmarking.sql` | Folded in — `comp_contribution`, `peer_benchmark_result` added to `schema.sql` LAYER 15. |
| `025_alumni_per_org_consent.sql` | Superseded by `026` — created `alumni_consent`, then `026` dropped it in favor of adding `tenant_id` to `employee_consent` directly. Net effect already in `schema.sql`. |
| `026_fix_employee_consent_tenant_scope.sql` | Folded in — `employee_consent.tenant_id`/`.share_mobile`/`.share_email`/`.notice_language`/`.notice_hash` added to `schema.sql` LAYER 15. |
| `027_alumni_outreach_reply.sql` | Folded in — `alumni_outreach.reply_body` included directly in the LAYER 15 table definition. |
| `028_gamification.sql` | Folded in — `badge_definition`, `employee_badge`, `career_score`, `employee_streak` added to `schema.sql` LAYER 15 (seed data for the 10 default badges not re-added — re-seed manually if needed). |
| `029_hrms_connector_definition.sql` | Folded in — `hrms_connector_definition`, `hrms_sync_log`, and `hrms_connector_config.connector_definition_id`/`.field_mapping` added to `schema.sql` LAYER 15. |
| `030_hrms_webhook_secret.sql` | Folded in — `hrms_connector_config.webhook_secret` included directly in the LAYER 15 `ALTER TABLE`. |
| `031_audit_event_error_code.sql` | Superseded — already applied directly to the live `audit_event` table. |
| `032_document_verification_code.sql` | Superseded — already applied directly to the live `document` table. |
| `033_document_statutory_hold.sql` | Superseded — `document.statutory_hold_*`/`.employee_visible`/`.employer_visible` and their index already existed in `schema.sql`. |
| `034_pan_token_version.sql` | Superseded — already applied directly to the live DB. |
| `035_consent_notice_lang.sql` | Superseded by `026`'s fold-in (`employee_consent.notice_language`). |
| `036_hnsw_embedding_index.sql` | **Not applicable in this environment** — this YugabyteDB's pgvector build (`0.4.4-yb-1.1`) supports neither `ivfflat` nor `hnsw` access methods. `schema.sql` now documents this and falls back to a sequential scan on `employee_master.name_embedding`, which is fine at current data volume. Revisit if the pgvector build is ever upgraded. |
| `037_manifest_scoring_weights.sql` | Folded in — `doc_type_field_manifest.signal_weights`/`.usage_count` included directly in the LAYER 15 table definition. |
| `038_employee_merge.sql` | Superseded — `employee_user.merged_into` and its index already existed. |
| `039_audit_role_revoke.sql` | Superseded — `schema.sql`'s own LAYER 14 already creates `prana_app_role` and REVOKEs UPDATE/DELETE on `audit_event`; this file was a duplicate of that, safe to re-run (idempotent) but adds nothing. |
| `040_error_event.sql` | Folded in — `error_event` added to `schema.sql` LAYER 15. |
| `041_severity_sla_policy.sql` | Superseded — `sla_policy`, `severity_classification_rule` and their seed rows already existed in `schema.sql`. |
| `042_anomaly_detection_support.sql` | Partially superseded — `share_otp_attempt` already existed; the 8 `platform_config` keys it seeds were already present (added directly to `schema.sql` in earlier work). `idx_em_tenant_dol` already existed. Nothing left to fold in. |
| `043_document_batch.sql` | Superseded — `document_batch` already existed. |
| `044_document_legal_hold.sql` | Superseded — `document.legal_hold_active`/`.legal_hold_reason` already existed. |
| `045_audit_archive_log.sql` | Partially folded in — `audit_archive_log` table already existed; the 2 `platform_config` keys (`audit_archival_cutoff_days`, `audit_archival_batch_size`) added to `schema.sql` LAYER 15 (value_type fixed: this file's invalid `'COUNT'` → the table's valid `'INTEGER'`). |
| `046_webhook_delivery_log.sql` | Superseded — `webhook_delivery_log` already existed. |
| `047_employee_insight.sql` | Superseded — `employee_insight` already existed. |

## Separately fixed in `schema.sql` during this reconciliation (not from any migration file)

- **`audit_event`/`anomaly_event`**: both were `PARTITION BY RANGE(...)` tables
  whose primary key didn't include the partition column — invalid DDL that
  Postgres/YugabyteDB reject outright (`insufficient columns in PRIMARY KEY
  constraint definition`). Neither table actually existed on a fresh
  `db-init.sh` run. Fixed with composite primary keys
  (`event_id, occurred_at`) and (`anomaly_id, detected_at`).
- **`audit_event`/`anomaly_event`/`kms_key_log`/`pa_platform_summary`**: all
  four are partitioned parents, but `schema.sql` never created any child
  partitions for them — a partitioned table with zero partitions rejects
  every `INSERT`. Added dev partitions (2025/2026/2027 + a `DEFAULT` catch-all
  for the range-partitioned ones, 4-way hash split for `pa_platform_summary`).
- **`idx_emp_embedding` (`ivfflat`)** and **3 indexes with `INET` as the
  leading column** (`idx_lal_ip`, `idx_share_otp_attempt_ip`, `idx_dal_ip`):
  removed — this YugabyteDB build doesn't support either the `ivfflat` access
  method or indexing directly on an `INET` column. Queries fall back to
  sequential scans, acceptable at current data volume.

## If you need to add a new table or column

Edit `schema.sql` directly. Do not add a new file here — this directory is
frozen as historical reference for how the schema got to its current state,
not a place for new work.
