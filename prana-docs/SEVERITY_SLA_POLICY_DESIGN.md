# Incident Severity, SLA & Anomaly-Detection Policy — Design Proposal

> **STATUS: COMPLETE (2026-07-16).** User directed full scope: §3.2's originally-deferred
> rules included, auto-lock built and shipping config-gated off. See §11 for a verified,
> current snapshot — do not assume anything below this line is done until §11 confirms it.

## 11. Current Implementation Status (verified 2026-07-16 — read this before relying on any claim above)

**Live and tested today:**
- `sla_policy` + `severity_classification_rule` tables (migration 041) — PA-editable,
  seeded with today's real values, verified idempotent (re-run inserts 0 rows) and
  applies cleanly on a fresh DB (42 tables, full `schema.sql` apply tested end-to-end).
- `SeverityPolicyService` — the shared rule evaluator + SLA lookup. `incident_service.py`,
  `error_threshold_service.py`, `health_service.py` all refactored to read from it —
  zero hardcoded severity/SLA constants left in those three files.
- `workflows/activities.py`'s `CROSS_TENANT_UPLOAD_ATTEMPT` now resolves severity via
  policy instead of a literal `"P0"`.
- `security_consumer.py`'s phantom `security_incident` table reference is gone — it now
  writes the real `incident` table via `IncidentService`, and persists `anomaly_event`
  itself (idempotent on `anomaly_id`) for every event-driven anomaly, since Kafka
  publishers don't write that row themselves.
- `security_consumer.py` (`P3` default) vs `notif_consumer.py` (`P2` default) severity
  disagreement — fixed; both resolve via the same `ANOMALY_RULE` `DEFAULT` policy row.
- **6 anomaly detection rules, real SQL, running on `AnomalyDetectionWorkflow`'s existing
  5-minute batch schedule** (`services/anomaly_detection_service.py`), every query
  validated against a live YugabyteDB instance (window functions, JSONB dedup, the lot):
  `BULK_DOC_ACCESS`, `BRUTE_FORCE`, `OFF_HOURS_ACCESS`, `IMPOSSIBLE_TRAVEL`, `SHARE_ENUM`,
  `PRE_EXIT_BULK`. All 6 read their own occurrence/window threshold from
  `severity_classification_rule` — PA can retune any of them without a deploy.
- `CROSS_TENANT_QUERY` — `services/tenant_isolation_guard.py`, a synchronous
  publish-only guard (never writes DB directly, per the HTTP handler contract). **Wired
  into exactly 2 endpoints** as a representative rollout, not a sweep:
  `GET /v1/ingest/status/{document_id}` (document ownership) and
  `POST /v1/org/exceptions/{id}/resolve` (employee-record ownership). Every other
  `WHERE id=$1 AND tenant_id=$2` ownership check across the API (there are dozens) is
  **not** wired to this guard — extending coverage is a scoped follow-up, not silently
  done here, because retrofitting every router in one pass without dedicated review is
  itself a risk on security-sensitive code.
- `PRIVILEGE_ESCALATION` — synchronous, in `OAUserConsumer` on `ROLE_CHANGED` events
  (published by `routers/oa_users.py`'s `change-role` endpoint, which now does exactly
  the one Kafka publish the HTTP handler contract allows — no direct writes). Flags a
  jump to a higher-ranked role (`oa_operator` < `chro`/`cfo`/`ciso` < `oa_admin`) **or**
  any self-change regardless of direction. Publishes into the same
  `SecurityConsumer` → `anomaly_event` → incident pipeline as everything else.
- `apply_policy_lock` / `release_policy_lock` / `notify_policy_lock`
  (`workflows/security.py`, backed by new `services/account_lock_service.py`) — real
  bodies. `apply_policy_lock` is idempotent (activity retry returns the existing OPEN
  lock rather than double-locking), writes `account_status_event`
  (`event_type='POLICY_LOCK'`, `scheduled_unlock_at` set), and flips
  `employee_user`/`oa_user.status` to `LOCKED`. `release_policy_lock` is idempotent
  against `routers/ciso.py`'s manual-unlock endpoint racing it (that endpoint reverses
  the lock directly without signalling the running workflow — `release_policy_lock`
  no-ops if `reversed_by_event_id` is already set). `get_security_config` — also a bare
  stub until now — is fixed too, since every workflow in this file that reads a
  duration/schedule from config depended on it (`PolicyLockWorkflow`,
  `TOTPLockoutWorkflow`, `AnomalyDetectionWorkflow`, `KMSKeyRotationWorkflow`,
  `HMACSecretRotationWorkflow` were all silently broken on first activity call before
  this fix).
- The auto-lock trigger exists: `SecurityConsumer._maybe_auto_lock`, called from
  `_handle_anomaly` after incident creation. Starts `PolicyLockWorkflow` (workflow ID
  `policy-lock-{rule_name}-{actor_id}`, `auth-queue`) when a `BULK_DOC_ACCESS` or
  `BRUTE_FORCE` anomaly names a lockable `actor_user_type` (`employee` or `oa_user`) and
  the corresponding config flag (`bulk_access_auto_lock_enabled` /
  `brute_force_auto_lock_enabled`, both seeded `false`) is enabled. `THIRD_PARTY` actors
  (HRMS API keys) are never targeted — no local account to lock.
- `detect_bulk_doc_access()` now selects `actor_type` and `detect_brute_force()` now
  selects `login_attempt_log.user_type` (was previously omitted from the SELECT even
  though the column exists) — both feed `actor_user_type` through
  `anomaly_detection_service.py`'s `_raise_anomaly`/`_publish_anomaly` into the
  `ANOMALY_DETECTED` Kafka event, which is what the auto-lock trigger reads to know
  which table to lock.
- PA backend endpoints: `GET/PATCH /admin/sla-policy*`, `GET/POST/PATCH
  /admin/severity-rules*` (`routers/pa_admin.py`, backed by new CRUD methods on
  `SeverityPolicyService`).
- PA frontend: `prana-portal/src/pages/pa/IncidentPolicyConfig.tsx` — SLA & Auto-Incident
  tab (per-severity SLA minutes, auto-create toggle, description) and Classification
  Rules tab (domain filter, inline edit, new-rule form). Nav entry under Security &
  Compliance.
- Docs updated: `workflows/CLAUDE.md` (PolicyLockWorkflow correction bullet),
  `KAFKA_REDIS_ARCHITECTURE.md` §10 (this system's canonical architecture summary).
- Full suite verified: 1342 prana-api tests + 757 prana-portal tests passing, `tsc`
  clean, `enforce_rules.py` clean (0 errors).

**Not yet built — permanently out of scope for this pass, tracked separately:**
- A pre-existing, unrelated bug found while implementing the auto-lock trigger:
  `kafka/consumers/auth_consumer.py` and `kafka/consumers/oa_user_consumer.py` both call
  `start_workflow("AccountLockWorkflow", ...)` — a workflow name that is never defined
  anywhere (only `PolicyLockWorkflow` exists). Both call sites swallow the resulting
  exception, so the consecutive-login-failure and OA-user-lock auto-workflow paths have
  been dead code independent of anything in this design. Flagged as a separate follow-up
  task, not folded into this change (different trigger path, different param shape).

**Explicitly, permanently out of scope for this design** (not deferred, not planned):
- Anything beyond rule-based thresholds — no ML/statistical anomaly scoring anywhere.
- `SHARE_ENUM` only catches *failed* OTP attempts against distinct tokens from one IP —
  a successful-but-suspicious share access (e.g. an OTP correctly guessed or leaked) is
  invisible to this rule; there is no behavioral signal for that today.
- Retrofitting `CROSS_TENANT_QUERY` checks into every ownership-scoped query in the API —
  the guard exists and is proven correct, but 2-endpoint coverage is intentional, not
  partial-by-accident.
- `run_anomaly_detection_batch`'s 6 rules are batch-scanned on a 5-minute cadence
  (`platform_anomaly_check_minutes`) — none of them are real-time/streaming detection;
  an anomaly can be up to ~5 minutes old before it's caught (`CROSS_TENANT_QUERY` and
  `PRIVILEGE_ESCALATION` are the two genuinely real-time exceptions, since they're
  event-driven off an HTTP request / Kafka event, not batch-scanned).

## 1. Problem statement

PA asked for a frontend to define what counts as P0 vs P1 vs P2 vs P3, and the SLA
hierarchy per severity. Investigating that surfaced a much bigger gap than "add a config
screen": severity and SLA values are hardcoded in Python across *six* different files, two
of them actively disagree with each other, one writes to a database table that doesn't
exist, and the "anomaly detection engine" that's supposed to be the primary source of P0-P3
security incidents is an unimplemented stub. None of this was invented for this doc — every
claim below is a direct file:line citation, verified by reading the code.

### 1.1 Hardcoded severity / SLA sites (real, working)

| File:line | What | Values |
|---|---|---|
| `services/incident_service.py:20-24` | `_SLA_MAP` — severity → ack SLA | P0=30min, P1=4hr, P2=24hr, P3=72hr |
| `services/incident_service.py:81` | which severities auto-create an incident | hardcoded `("P0","P1")` |
| `services/error_threshold_service.py:24-31,64-83` | error_event → incident severity classification | security paths→P1 (1st occurrence), compliance paths→P2 (3-in-10min), novel bug→P2 (1st occurrence), noise→P3 (10-in-15min) |
| `services/health_service.py:25-27` | per-service severity when a health check fails | prana-api=P1, prana-ai=P2, prana-ask=P3 |
| `workflows/activities.py:247` | `CROSS_TENANT_UPLOAD_ATTEMPT` anomaly severity | hardcoded literal `"P0"` |

### 1.2 Broken / unimplemented (found while scoping, in scope per your direction)

| File:line | Problem |
|---|---|
| `kafka/consumers/security_consumer.py:84-103` | `_handle_anomaly` INSERTs into `security_incident` — **this table does not exist anywhere in `schema.sql`**. The INSERT throws at runtime; the surrounding `except Exception: log.exception(...)` silently swallows it. Dead code. |
| `kafka/consumers/security_consumer.py:86` vs `kafka/consumers/notif_consumer.py:125` | Same `ANOMALY_DETECTED` event, two different hardcoded default severities if the event doesn't carry one (`"P3"` vs `"P2"`) — currently harmless only because nothing publishes this event live. |
| `workflows/security.py:55-56` | `run_anomaly_detection_batch` — the activity `AnomalyDetectionWorkflow` calls every `platform_anomaly_check_minutes` (Pattern 4, Continue-As-New) — is a bare `...` stub. No anomaly detection actually runs today. |
| `workflows/security.py:34-77` (broadly) | `apply_policy_lock`, `release_policy_lock`, and most of this file's other activities are also stubs — `PolicyLockWorkflow` exists as a real Pattern-2 shell but has nothing to call. |

**What this means concretely:** apart from the one synchronous `CROSS_TENANT_UPLOAD_ATTEMPT`
check, PRANA currently detects *zero* security anomalies automatically. The CISO "Live threat
feed" and PA "Security Incident Register" only ever show whatever a human manually flags, or
that one cross-tenant-upload check. `BULK_ACCESS_ANOMALY` — referenced in
`prana-portal/CLAUDE.md`'s CISO dashboard example — is not implemented anywhere in `prana-api`.

---

## 2. Severity & SLA policy — two new tables

### 2.1 `sla_policy` — one row per severity

```sql
CREATE TABLE sla_policy (
    severity              VARCHAR(2)  PRIMARY KEY,          -- P0 | P1 | P2 | P3
    sla_minutes            INTEGER     NOT NULL,
    auto_create_incident   BOOLEAN     NOT NULL DEFAULT FALSE,
    description             TEXT,
    updated_by               UUID,
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
Seeded with today's real values so behavior doesn't change until PA edits it:
`P0=30/auto=true`, `P1=240/auto=true`, `P2=1440/auto=false`, `P3=4320/auto=false`.

Replaces `incident_service.py`'s `_SLA_MAP` dict and the hardcoded
`if severity not in ("P0","P1")` auto-create gate.

### 2.2 `severity_classification_rule` — one small rule engine, reused by every domain

```sql
CREATE TABLE severity_classification_rule (
    rule_id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    domain                  VARCHAR(30) NOT NULL,   -- ERROR_OBSERVABILITY | HEALTH_CHECK | ANOMALY_RULE
    match_type               VARCHAR(20) NOT NULL,   -- PREFIX | EXACT | DEFAULT
    match_value               VARCHAR(200),            -- NULL when match_type = DEFAULT (wildcard)
    occurrence_threshold      INTEGER,                  -- NULL = matches on first occurrence
    window_minutes             INTEGER,                  -- paired with occurrence_threshold
    severity                    VARCHAR(2)  NOT NULL,
    priority                     INTEGER     NOT NULL DEFAULT 100,  -- lower = evaluated first, first match wins
    is_active                     BOOLEAN     NOT NULL DEFAULT TRUE,
    description                    TEXT,
    updated_by                      UUID,
    updated_at                       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Evaluation algorithm** (one function, reused by all three domains):
```
for rule in active_rules(domain) ordered by priority ASC:
    matched = (rule.match_type == DEFAULT)
           or (rule.match_type == PREFIX and value.startswith(rule.match_value))
           or (rule.match_type == EXACT  and value == rule.match_value)
    if not matched: continue
    if rule.occurrence_threshold is not None:
        if occurrence_count < rule.occurrence_threshold: continue
        if rule.window_minutes is not None and span > rule.window_minutes: continue
    return rule.severity
return None   # no match — caller's existing "don't promote" behavior
```

This single algorithm reproduces all three currently-hardcoded rule sets exactly (verified
by hand against each one) — it's a generalization, not a new behavior:

- **`domain=ERROR_OBSERVABILITY`** (replaces `error_threshold_service.py`'s constants):
  `PREFIX /auth/ → P1` (prio 10), `PREFIX /totp/ → P1` (prio 10), `EXACT AuthConsumer → P1`
  (prio 10), `EXACT verify_audit_integrity → P1` (prio 10), `PREFIX /v1/dpdp/, occurrence≥3/
  window≤10min → P2` (prio 20), `PREFIX /v1/ingest/, occurrence≥3/window≤10min → P2` (prio 20),
  `DEFAULT, occurrence≥1 → P2` (prio 90, "novel bug"), `DEFAULT, occurrence≥10/window≤15min →
  P3` (prio 95, "noise").
- **`domain=HEALTH_CHECK`** (replaces `health_service.py`'s `HEALTH_TARGETS`):
  `EXACT prana-api → P1`, `EXACT prana-ai → P2`, `EXACT prana-ask → P3` (no threshold — always
  matches on the service name).
- **`domain=ANOMALY_RULE`** (replaces the scattered anomaly literals, §1.2's conflict, AND
  becomes the detection-threshold config for §3's new engine):
  `EXACT CROSS_TENANT_UPLOAD_ATTEMPT → P0` (prio 10, replaces `activities.py:247`'s literal),
  plus one row per detection rule in §3 (`EXACT BULK_DOC_ACCESS → P1`, `EXACT BRUTE_FORCE →
  P1`, `EXACT OFF_HOURS_ACCESS → P2`, `EXACT IMPOSSIBLE_TRAVEL → P0`), plus
  `DEFAULT → P3` (prio 99) as the single shared fallback — this is what fixes the
  `security_consumer.py` P3 / `notif_consumer.py` P2 disagreement: both consumers call the
  same lookup instead of keeping their own conflicting default.

The `occurrence_threshold`/`window_minutes` columns on the `ANOMALY_RULE` rows do double duty
as the actual detection thresholds (see §3) — PA editing "BULK_DOC_ACCESS, occurrence≥50,
window≤10min" in the policy screen *is* editing when that anomaly fires, not just its
severity once it does. One screen, one mental model, instead of a separate "detection
threshold" config surface.

### 2.3 Service refactors (read-only changes to existing files, no behavior change until PA edits policy)

- `incident_service.py` — `_SLA_MAP` dict → `sla_policy` table read; hardcoded auto-create
  check → `sla_policy.auto_create_incident`.
- `error_threshold_service.py` — `_classify()` → generic rule evaluator against
  `domain='ERROR_OBSERVABILITY'`.
- `health_service.py` — `HEALTH_TARGETS` severity field → rule evaluator against
  `domain='HEALTH_CHECK'`.
- `workflows/activities.py:247` — literal `"P0"` → rule evaluator against
  `domain='ANOMALY_RULE', match_value='CROSS_TENANT_UPLOAD_ATTEMPT'`.
- `kafka/consumers/security_consumer.py` and `notif_consumer.py` — both stop hardcoding their
  own default; both call the same rule evaluator for `domain='ANOMALY_RULE'` against
  `event.get("rule_name")`.

---

## 3. Anomaly detection engine — implementing `run_anomaly_detection_batch` for real

The `anomaly_event` table's schema comment already names 8 canonical rules:
`IMPOSSIBLE_TRAVEL | BULK_DOC_ACCESS | SHARE_ENUM | OFF_HOURS_ACCESS | BRUTE_FORCE |
CROSS_TENANT_QUERY | PRE_EXIT_BULK | PRIVILEGE_ESCALATION`. I'm proposing to implement the
**4 with clean, already-existing signal columns**, and explicitly defer the other 4 rather
than guess at logic for data that may not exist in the shape I'd need.

### 3.1 Implementing now

| Rule | Signal source | Detection logic |
|---|---|---|
| `BULK_DOC_ACCESS` | `document_access_log` (indexed on `(tenant_id, accessed_at)`) | same `actor_id` has ≥ N accesses within the configured window |
| `BRUTE_FORCE` | `login_attempt_log` | same identifier (`user_id` or attempted email/phone) has ≥ N `outcome='FAILURE'` rows within the window |
| `OFF_HOURS_ACCESS` | `document_access_log.accessed_at` | access outside a configured business-hours window (IST), for OA actors specifically (employees viewing their own vault at 2am isn't anomalous; an OA-Operator downloading documents at 2am is) |
| `IMPOSSIBLE_TRAVEL` | `login_attempt_log.geo_lat/geo_lon` + `attempted_at` | two successful logins for the same user within a time delta that implies a travel speed exceeding a configured km/h threshold (haversine distance / time delta) |

Each becomes a query in the (currently-stub) `run_anomaly_detection_batch` activity, run on
`AnomalyDetectionWorkflow`'s existing Continue-As-New loop. Each finding writes an
`anomaly_event` row (`rule_name` = the values above) with severity resolved via §2.2's
`domain='ANOMALY_RULE'` lookup, then publishes `security_event({"event_type":
"ANOMALY_DETECTED", "rule_name": ..., "severity": ...})` — **carrying the resolved severity
explicitly this time**, which is what actually fixes the consumer disagreement (§1.2) at the
source, not just papering over it downstream.

New `platform_config` keys (all currently missing, confirmed): `bulk_doc_access_threshold`
(default 50) / `bulk_doc_access_window_minutes` (10) — mirrored by the `ANOMALY_RULE` rule
row so PA edits them in one place, not two; `brute_force_threshold` (5) /
`brute_force_window_minutes` (15); `off_hours_start_hour` (22) / `off_hours_end_hour` (6),
IST; `impossible_travel_speed_kmh` (900, roughly commercial flight speed — a slower delta is
plausible travel, not anomalous).

### 3.2 Explicitly deferred, not implemented in this pass

| Rule | Why deferred |
|---|---|
| `SHARE_ENUM` | Needs per-recipient share-token access-attempt tracking (failed OTP attempts against different tokens from the same IP). `share_token`/`document_access_log` don't currently record *failed* OTP attempts distinctly from successful views — would need a schema addition first. |
| `CROSS_TENANT_QUERY` | Distinct from `CROSS_TENANT_UPLOAD_ATTEMPT` (already handled) — this would mean detecting cross-tenant *read* attempts, which requires auditing query-level tenant filters, not just logged access rows. No existing signal captures an attempted-but-blocked cross-tenant read. |
| `PRE_EXIT_BULK` | Requires correlating bulk access with an employee's *known upcoming exit date* — `employee_master`'s exit-related fields weren't confirmed to exist in the form needed; needs a follow-up schema check before designing detection logic. |
| `PRIVILEGE_ESCALATION` | Requires a role-change audit trail for `oa_user`/`portal_admin` — not confirmed to exist as a queryable event stream distinct from generic `audit_event` rows. |

Each stays as a named-but-unmatched `rule_name` — if one is manually reported (e.g. a CISO
flags something as `SHARE_ENUM` by hand later), the `ANOMALY_RULE` `DEFAULT → P3` fallback
still assigns it a sane severity even without automated detection.

### 3.3 `apply_policy_lock` — implementing the currently-stub lockout activity

`BULK_DOC_ACCESS` and `BRUTE_FORCE` are the two rules where an automatic account lock is a
reasonable response (this is what `prana-portal/CLAUDE.md`'s `BULK_ACCESS_ANOMALY` UI text
was written for, but never had a backend). `PolicyLockWorkflow` (Pattern 2, already a real
shell) is the existing mechanism — `apply_policy_lock` just needs a real body: write
`account_status_event(event_type='POLICY_LOCK', reason_code=rule_name, ...)`, set the
account's effective lock state, and `release_policy_lock` reverses it (either via the
workflow's timer or an OA-Admin unlock action, both already-designed paths per
`prana-portal/CLAUDE.md`'s "Unlock now" button).

**Risk flag, explicitly**: auto-locking accounts based on new detection thresholds carries
real risk of false positives (e.g. an OA-Operator legitimately bulk-downloading documents for
a compliance audit). Recommend: lock behavior stays **disabled by default** (a
`bulk_access_auto_lock_enabled` / `brute_force_auto_lock_enabled` platform_config boolean,
default `false`) — anomaly detection and incident creation ship active, but auto-lock is
opt-in until a tenant/PA has watched real detection output and is confident in the
thresholds. This is a deliberate, conservative default; happy to make it default-on if you'd
rather.

---

## 4. Fixing the phantom `security_incident` table

`security_consumer.py`'s `_handle_anomaly` gets rewritten to route into the **existing**
`incident` table via `IncidentService.create_incident(incident_type="SECURITY_ANOMALY", ...)`
— the same table every other incident track already uses — instead of the nonexistent
`security_incident` table. No new table for this; it was always meant to be the one that
exists, going by every other consumer of anomaly severity in this codebase.

---

## 5. PA-facing API + UI

### 5.1 New `pa_admin.py` endpoints
```
GET   /admin/sla-policy                        → 4 rows
PATCH /admin/sla-policy/{severity}              → { sla_minutes, auto_create_incident }
GET   /admin/severity-rules?domain=...          → list, filterable
POST  /admin/severity-rules                     → create a new rule
PATCH /admin/severity-rules/{rule_id}           → edit / toggle is_active
DELETE /admin/severity-rules/{rule_id}          → remove a custom rule
```

### 5.2 New PA screen: `prana-portal/src/pages/pa/IncidentPolicyConfig.tsx`
Two tabs, same shell pattern as the recently-built Errors tab:
- **SLA & Auto-Incident** — 4-row editable table (severity, minutes, auto-create toggle).
- **Classification Rules** — table filterable by domain (Errors / Health / Anomalies),
  add/edit/deactivate a rule, with the occurrence/window fields shown only when relevant.

New PA nav entry + i18n codes, same conventions as every other screen built this session.

---

## 6. What ships together vs. what's still out of scope

**Shipped (superseded by §11 — read that section for the verified final state):** §2 (SLA +
rule tables, all 3 existing domains refactored to read from them), §3.1 **and** §3.2 (all 6
anomaly rules with real detection — user directed full scope, the original §3.2 deferral
was overridden), §3.3 (policy-lock activity, auto-lock **off** by default), §4
(phantom-table fix), §5 (PA config UI).

**Explicitly still out of scope, flagged not silently dropped:** `TOTPLockoutWorkflow`'s
other stub activities in `workflows/security.py` not related to policy-lock; any change to
how `AnomalyDetectionWorkflow`'s schedule interval itself is tuned
(`platform_anomaly_check_minutes` already exists as a config-driven value with a seeded
default of "5" — not redesigned, just used as-is via the now-real `get_security_config`).
