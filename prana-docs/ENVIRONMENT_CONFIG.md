# PRANA Environment Configuration

**One codebase, one `schema.sql`, one set of scripts — across dev, pre-prod, and
production.** The only thing that differs per environment is *configuration
values* (env vars / secrets), never code, never a duplicated folder of scripts.
See the "why" for this in `prana-db/migrations/README.md` — the last time two
sources of truth existed for the same thing (`schema.sql` vs `migrations/`),
they silently drifted apart for months and broke production-shaped testing.

## The rule

| Environment | Code | Schema | Scripts | Config |
|---|---|---|---|---|
| dev | same repo, same commit path as prod | same `schema.sql` | same scripts | `.env` / `docker-compose.yml` defaults |
| pre-prod | **identical artifact** promoted from CI | same `schema.sql` | same scripts | pre-prod env vars / Secrets Manager |
| production | **identical artifact** promoted from pre-prod | same `schema.sql` | same scripts | prod env vars / Secrets Manager |

If pre-prod and production ever run different code, different schema, or
different scripts, pre-prod passing proves nothing about production. Build the
artifact once in CI, deploy that exact artifact to pre-prod, run the test
suite (see `PREPROD_TESTING_CHECKLIST.md`) against it, then **promote the same
artifact** to production — don't rebuild.

## Config sources, in resolution order

1. **`prana-api/config.py` (`Settings`, pydantic-settings)** — every tunable
   has a dev-safe default. Real values come from environment variables (12-factor).
2. **`platform_config` / `tenant_config` DB tables** — *runtime* config
   (durations, feature-flag thresholds, SLA windows) that operators can change
   without a redeploy. Same rows exist in every environment via `schema.sql`;
   only the *values* an operator later tunes might differ.
3. **AWS Secrets Manager / SSM Parameter Store** — where real secrets actually
   live in pre-prod and production. Env vars in ECS/EKS task definitions
   reference secret ARNs, not literal values.

## `config.py` fields that MUST differ between dev and pre-prod/production

`Settings.assert_production_ready()` already enforces the security-critical
half of this list in code — it refuses to boot in production if any of these
are still dev placeholders. Treat pre-prod as if this guard applies there too,
even though the flag only trips on `app_env == "production"`.

| Field | Dev default | Pre-prod / Prod |
|---|---|---|
| `app_env` | `development` | `staging` (pre-prod) / `production` |
| `db_user` / `db_password` | `prana_app_role` / `prana_app_role` | Real `prana_app_role` credentials from Secrets Manager. **Never** `yugabyte`/`postgres`/`root` — those bypass the `audit_event` REVOKE (migration 039 / schema.sql LAYER 14). |
| `platform_hmac_secret` | `dev_secret` | Real HMAC key from Secrets Manager — this is the PAN/NIK tokenization key; rotating it breaks every existing `pan_token` |
| `auth_encryption_key` | empty (derived) | Required — 32-byte AES-256 key from Secrets Manager/KMS |
| `jwt_kms_key_id` | empty (local PEM) | Required — KMS CMK ARN; prod signs JWTs via KMS, not a local private key file |
| `ai_service_secret` / `ask_service_secret` | `dev-secret` | Real shared secrets between prana-api ↔ prana-ai/prana-ask |
| `immudb_password` | `immudb` | Real credential |
| `s3_endpoint_url` | MinIO (`http://localhost:9010`) | empty string → real AWS S3 |
| `kafka_bootstrap_servers` | `localhost:9092` | Real MSK broker list, per-region |
| `temporal_host` / `temporal_namespace` | `localhost:7233` / `prana-dev` | Real Temporal cluster endpoint / `prana-preprod` or `prana-prod` namespace |
| `cors_origins` | includes `localhost`, `github.io` demo | Real `prana.in` origins only — `effective_cors_origins` already strips dev origins when `is_production`, but pre-prod should be configured with its real origin too, not left on dev defaults |
| `smtp_host` | empty (console-logs OTP) | Real SMTP relay — **pre-prod must NOT be empty if you're testing OTP delivery**, but should point at a sandboxed provider, not the real SES prod identity |
| `sms_provider` | `dev` (console log) | `exotel` or `msg91` — same sandbox-vs-real caveat as SMTP |
| `ncmec_report_url` | empty (logs instead of reporting) | Required in production — this is a legal CSAM-reporting obligation, not optional |

## Things that must be *provisioned*, not configured (infra, not env vars)

These are Terraform/AWS-console concerns — a pre-prod or prod environment
without them isn't "unconfigured," it's **not built yet**:

- YugabyteDB cluster (dual-region for prod: `ap-south-1` + `ap-south-2`)
- AWS MSK cluster + the 21 topics from `prana-api/kafka/producer.py` (topic
  auto-creation is normally disabled in production Kafka — provision explicitly)
- ElastiCache Redis (Global Datastore for prod's cross-region CRDT sync)
- Immudb deployment
- KMS customer-managed keys (platform secret + per-tenant KEKs)
- S3 buckets (`prana-documents-*`, `prana-staging-*`) with correct bucket policies
- Kong API Gateway routes + the HMAC-signed API key mechanism for HRMS partners
- Temporal cluster + task queues (`ingestsvc-queue`, `auth-queue`, etc. — see
  `prana-api/workflows/CLAUDE.md`)

## Bootstrap sequence for a brand-new environment (pre-prod or production)

Run once, in order, after infra above exists:

1. Apply `prana-db/schema.sql` to the empty database (`ysqlsh -f schema.sql`,
   or via whatever CI job wraps this). This alone gives you: 82 tables, 43
   `platform_config` defaults, 21 `severity_classification_rule` rows, 4
   `sla_policy` rows, 18 `doc_type_field_manifest` platform defaults, 10
   `badge_definition` rows, the `prana_app_role` DB role + grants/REVOKEs.
2. `python prana-api/scripts/bootstrap_portal_admin.py --email admin@prana.in`
   — creates the first Portal Admin account. Refuses to run if `portal_admin`
   already has any rows (idempotent-safe against accidental re-runs).
3. Deploy `prana-api`, `prana-ai`, `prana-ask` containers with real env vars /
   secret references.
4. Verify `/health/ready` on prana-api actually reports every dependency
   (DB, Redis, Kafka, Temporal, S3, KMS) reachable — don't just check `/health`
   (liveness only).
5. Log in as the bootstrapped Portal Admin, complete TOTP setup.
6. Onboard exactly one real (or realistic pilot) tenant through the actual
   onboarding flow — **not** a seed script — to prove `TenantProvisioningWorkflow`
   / `DomainVerificationWorkflow` actually work end-to-end. See
   `PREPROD_TESTING_CHECKLIST.md`.

Never run anything from `prana-db/seeds/dev_seed*.sql` against pre-prod or
production — those are dev/test-only by explicit design (`prana-db/CLAUDE.md`),
and running them would fabricate fake employees/tenants in an environment
meant to prove the real onboarding path.
