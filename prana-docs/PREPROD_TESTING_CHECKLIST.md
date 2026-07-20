# PRANA Pre-Prod Testing & Go-Live Checklist

Prerequisite: pre-prod is infra-identical to production (see
`ENVIRONMENT_CONFIG.md`) and has completed the bootstrap sequence there
(schema applied fresh, Portal Admin bootstrapped, no dev seed data).

Everything below tests the **real onboarding path**, not dev seed shortcuts.
Any dev seed script (`dev_seed*.sql`, `reset_dev.py`) reaching pre-prod means
you're testing the seed script, not the product.

## 0. Infra smoke test (before any functional testing)

- [ ] `GET /health` on prana-api returns 200 (liveness)
- [ ] `GET /health/ready` reports every dependency reachable: YugabyteDB,
      Redis, Kafka, Temporal, S3, KMS — not just "process is up"
- [ ] All 21 Kafka topics exist in the MSK cluster (`prana-api/kafka/producer.py`
      is the authoritative list) — topic auto-creation is normally off in prod-grade
      Kafka, so a missing topic fails silently at publish time otherwise
- [ ] All 20 Kafka consumer processes are running and connected (check consumer
      group lag, not just process status)
- [ ] Temporal worker processes registered on every task queue
      (`ingestsvc-queue`, `auth-queue`, `vault-queue`, `admin-queue`,
      `analytics-queue`, `insight-queue`, `secops-queue`, `safety-queue`,
      `resolution-queue`, `resolution-low-priority-queue`, `compliance-queue`,
      `hrms-queue`) — a workflow started on a queue nothing polls silently
      never progresses (this exact bug shipped once this session — see git log
      "Fix systemic task_queue mismatches")
- [ ] `schema.sql` applied with zero errors (this is now a required CI gate,
      not just a manual check — see §7)

## 1. Auth — all 3 login surfaces, all 7 roles

- [ ] `/admin/login` — bootstrapped Portal Admin logs in, TOTP QR setup on
      first login, subsequent logins require live TOTP code
- [ ] `/org/login` — each of the 5 OA roles (oa_admin, oa_operator, chro, cfo,
      ciso) created via real tenant onboarding, logs in, TOTP setup flow works
- [ ] `/emp/login` — employee created via real HRMS push or self-upload flow,
      mobile OTP delivery actually arrives (real SMS provider, not `dev` console-log)
- [ ] Wrong password / wrong role / expired session all return the correct
      error code (message-taxonomy code, not a raw exception)
- [ ] Account lockout after threshold failed attempts (OA: 5, Portal Admin: 3
      — stricter per `prana-portal/CLAUDE.md`)
- [ ] Session revocation actually invalidates the JWT immediately (Redis
      blocklist, not just DB flag)

## 2. Tenant onboarding — the path dev seeds never exercise

- [ ] PA creates a tenant application via the real `/admin/tenants` POST
- [ ] `DomainVerificationWorkflow` actually polls DNS TXT and transitions the
      tenant on real verification (not skipped/stubbed)
- [ ] `TenantProvisioningWorkflow` creates the tenant row, a real KMS KEK, and
      the first OA-Admin account
- [ ] First OA-Admin's `force_reset` flow works (set password → TOTP setup)
- [ ] Kong API key HMAC registration actually completes for HRMS integration
      (this is exactly what `api_key.kong_consumer_registered` tracks — verify
      it flips to `TRUE`, don't just check the row exists)

## 3. Document pipeline — all 6 stages, at least one document per doc type

For each of the 18 seeded `doc_type_field_manifest` doc types (or however many
you plan to support at launch):

- [ ] Upload via Portal (OA-Operator) and via HRMS API push — both paths
- [ ] Pipeline progresses `QUEUED → ENCRYPTING → SCANNING → EXTRACTING →
      RESOLVING → ROUTED` — verify via SSE, not just final DB state
- [ ] Encryption boundary: `pan_token`/`enc_pan` correctly derived, raw PAN
      never lands in `document.extracted_fields` or logs
- [ ] Extraction confidence uses the real seeded manifest (this is the exact
      gap closed this session — without seeded rows, every doc type falls
      through to the unclassified queue)
- [ ] Identity resolution ladder: exact `pan_token`, exact employee_id, fuzzy
      name+DOJ, embedding cosine (note: no ANN index in this pgvector build —
      confirm cosine search still returns correct results via sequential scan,
      just slower)
- [ ] Exception queue: an intentionally-unresolvable document raises an
      exception, OA-Admin resolves it via the real UI, `exception_resolved`
      signal reaches the waiting workflow
- [ ] CSAM/virus scan path: a known-bad test file (EICAR test string for virus;
      do NOT use real CSAM material — use NudeNet/PhotoDNA's documented test
      vectors) triggers quarantine / `CSAMReportingWorkflow`, not a silent pass

## 4. DPDP compliance — all 5 statutory flows, real SLA timers

- [ ] Erasure request → `ErasureConfirmationWorkflow` → confirm `audit_event`
      rows survive (7-year retention) while PII is actually erased
- [ ] Export request → `DataExportWorkflow` completes within the configured
      72-hour SLA (or trigger it early for testing — don't wait 72 real hours)
- [ ] Correction request flow
- [ ] Consent withdrawal is immediate — verify processing actually stops for
      that purpose within the same request, not eventually
- [ ] Grievance flow: auto-ack within 48 hours, escalation path if unresolved

## 5. Security & anomaly detection

- [ ] Each of the 6 anomaly rules fires on a synthetic trigger:
      `IMPOSSIBLE_TRAVEL`, `BULK_DOC_ACCESS`, `BRUTE_FORCE`,
      `CROSS_TENANT_QUERY`, `PRE_EXIT_BULK`, `SHARE_ENUM`
- [ ] `bulk_access_auto_lock_enabled` / `brute_force_auto_lock_enabled` ship
      `false` by design — confirm this is the value you actually want at
      launch, don't assume
- [ ] CISO sees full IP in `document_access_log`; employee sees city-level
      only — verify via both role's actual API response, not just code review
- [ ] `AuditIntegrityVerificationWorkflow` catches a manually-tampered
      Immudb/`audit_event` mismatch (this is the whole point of the dual-write
      — prove it actually alerts)
- [ ] Cross-tenant isolation: attempt to access another tenant's document/
      employee by guessing an ID — confirm 403/404, not data leakage

## 6. Notifications — real delivery, not console logs

- [ ] Email (real SES/SMTP sandbox identity, not prod domain yet) — OA welcome,
      doc routed, exception alert, elevation approved, erasure complete
- [ ] SMS (real Exotel/MSG91 sandbox) — employee OTP
- [ ] WhatsApp (real WABA sandbox, approved templates) — doc routed notification
- [ ] Fallback chain actually falls back: force WhatsApp failure → confirm SMS
      fires → force SMS failure → confirm email fires
- [ ] Portal bell notifications appear in near-real-time (SSE, not polling)

## 7. Non-functional gates

- [ ] **Fresh-schema CI gate** — `schema.sql` applies to a throwaway empty
      database with zero errors, as part of CI on every PR that touches it.
      This is not optional: this exact gap (nobody had run `schema.sql` fresh
      in months) is what caused this whole reconciliation effort. Automate
      what was done manually this session.
- [ ] **Load test** — realistic concurrent upload volume for your expected
      launch tenant size; watch YugabyteDB tablet hotspotting, Kafka consumer
      lag, Temporal task queue backlog
- [ ] **Chaos test** — kill Kafka, kill Redis, kill Temporal, kill YugabyteDB
      one at a time mid-operation; confirm graceful degradation (e.g.
      `/health/ready` correctly reports the dependency down) and correct
      recovery on restart, not silent data loss
- [ ] **Backup/restore drill** — take a real YugabyteDB backup, restore it to
      a separate cluster, confirm the app boots against the restore
- [ ] **Secrets audit** — run `Settings.assert_production_ready()`'s check
      manually against pre-prod's actual env vars before go-live; every
      forbidden placeholder value must be absent
- [ ] **Security scan** — dependency vulnerability scan (`pip-audit`/`npm
      audit`), and a focused pass on the IDOR/authZ sweep areas already
      covered in this codebase's history (cross-tenant reads, role checks)

## 8. Go/no-go for a real organization

Only after every section above is green:

- [ ] Legal/compliance sign-off on DPDP flows (§4) and CSAM reporting (§3)
- [ ] Grievance Officer configured for the real tenant
      (`tenant_config.grievance_officer_*`)
- [ ] Real HRMS integration credentials verified against the actual partner
      system (Darwinbox/Keka/SAP/etc.), not a mock
- [ ] Rollback plan documented: how do you take the tenant back offline if
      something breaks in the first week, without touching other tenants'
      data (multi-tenant blast-radius containment)
- [ ] On-call/incident response owns `service_incident` and `incident` tables
      — confirm someone is actually watching the PA Meta Dashboard /
      IncidentRegister day one, not just that the tables exist
