# Application Error Observability — Design Proposal

> **STATUS: APPROVED 2026-07-15 — IMPLEMENTED 2026-07-16.** All 11 steps of §9's
> implementation plan are complete: capture (HTTP + Kafka + Temporal), storage, threshold
> promotion, Portal UI, message taxonomy, and docs. Full test suite green
> (1272 passed prana-api, 747 passed prana-portal), `enforce_rules.py` clean.
> This is the 4th track of PRANA's incident system, alongside the business-event
> track already agreed (`ANOMALY_DETECTED`, `AUDIT_INTEGRITY_MISMATCH`, etc.).
> It exists to close the gap identified 2026-07-15: **no caught or uncaught
> exception anywhere in prana-api currently produces a durable, visible, or
> actionable trace.** Verified empirically — see "Problem Statement."
>
> **Approved decisions (§10 resolved):**
> 1. In-house (§3–§7), not a third-party SaaS tool (§8 rejected).
> 2. Security/crypto-path errors ARE promoted to P1 incident on first occurrence — see §5's
>    finalized path list.
> 3. Thresholds finalized as originally proposed: 3-in-10-min for compliance-critical
>    endpoints, 10-in-15-min for everything else.
> 4. UI: Option B — fold into the existing `SecurityIncidentRegister.tsx` /
>    `IncidentRegister.tsx` screens as a new tab, not a standalone page.
> 5. Full v1 scope — all three capture layers (HTTP, Kafka consumers, **and Temporal
>    activities**) ship together. Temporal activities are NOT deferred to a phase 2.

---

## 1. Problem Statement (what's actually true today, verified not assumed)

Three distinct exception paths exist in prana-api, and all three are dead ends:

| Path | Where | What happens today | Verified how |
|---|---|---|---|
| **A. Global HTTP catch-all** | `main.py:330`, `@app.exception_handler(Exception)` | Returns generic `500 {"error": "INFRA_SERVICE_UNAVAILABLE"}`. Zero logging call in the handler body. Registering a custom `Exception` handler also **replaces** Starlette's own `ServerErrorMiddleware`, which is what would otherwise have logged it — so this isn't a gap in an otherwise-logged path, it actively suppresses the framework default. | Live test: raised a `RuntimeError` through the real app via `httpx`+`ASGITransport`, captured all logging output with a root-logger handler attached. Output contained zero trace of the exception — only an unrelated httpx access line. |
| **B. Explicit `except Exception: log.exception(...)`** | ~70 occurrences across `kafka/consumers/*.py`, several `services/*.py` | `log.exception()` genuinely fires and *would* produce a traceback — but no logging is configured anywhere in the FastAPI/Kafka-consumer process (`main.py` never calls `logging.basicConfig()`; the only call to it anywhere in the repo is in `workflows/worker.py`, a *separate* Temporal-worker process). Python falls back to the built-in "handler of last resort," which prints unstructured text to `stderr`. | Verified: same log line, with and without a manually-attached handler, to confirm the difference is purely "is anything listening," not "does logging fire." |
| **C. Silent `except Exception: pass`** | At least 2 confirmed in `routers/public.py` (e.g. Kafka-publish failure on credential verification), likely more among the 70 bare-except blocks | Nothing. No log call, no trace, no evidence the failure ever happened. | Direct code read. |

**Consequence:** `IncidentService` (the business-event incident track) is never invoked from any of these three paths — it's only ever called from deliberately hand-written business logic reacting to a *named event* (`ANOMALY_DETECTED`). A real production bug — a null-pointer crash, a bad migration, a broken integration — currently has a 0% chance of generating any signal an OA-Admin, CISO, or PA would ever see, unless someone happens to be live-tailing `docker logs` at the exact moment it happens.

Separately noted: the documented error response contract in `CLAUDE.md` (`{"error": "CODE", "message": "...", "request_id": "uuid"}`) is not actually honored by the global handler today — it returns `{"error": ...}` with no `request_id` field, because there's no request-ID generation/propagation mechanism in the app at all. This design proposes fixing that as a prerequisite (§3.1).

---

## 2. Design Goals

1. **Nothing is invisible.** Every exception on every one of the three paths above gets captured somewhere durable.
2. **Not everything is an incident.** A single transient network blip that succeeds on retry should not page anyone. Alert fatigue is a real failure mode — this design must actively resist creating one.
3. **Reuses the existing incident machinery**, not a parallel system. Once something crosses from "logged error" to "worth a human," it becomes a row in the *same* `incident` table, with the *same* P0–P3 severity/SLA policy already agreed in the business-event track. This document only decides **when** that promotion happens and **what severity** it gets — not a new escalation model.
4. **No PII leakage into error data.** PRANA's privacy contract is absolute (no raw PAN/salary anywhere outside the encryption boundary) — an error-capture system that dumps exception context is a plausible new leak vector if not designed carefully. This gets its own section (§6).
5. **In-house, matching existing architecture.** No new third-party SaaS dependency (Sentry, Datadog, etc.) by default — PRANA has consistently built this class of thing itself (`NotificationService`, `IncidentService`, `HealthService`, `ImmudbService`) on YugabyteDB + Kafka + Temporal. §8 discusses the trade-off explicitly since this is a real option, not dismissed lightly.

---

## 3. Data Model

### 3.1 Prerequisite: request correlation ID

Nothing below is useful without a stable ID to correlate "this HTTP request" → "this log line" → "this error row" → "this incident." Today there is no `X-Request-ID` generation/propagation anywhere in `main.py`.

**Proposed:** a `RequestIDMiddleware` (added first in the middleware stack) that:
- Reads `X-Request-ID` from the incoming request if the caller (Kong, a test, a partner integration) already set one.
- Otherwise generates a UUID.
- Stores it on `request.state.request_id`.
- Echoes it back as a response header `X-Request-ID` on every response, including error responses.
- Global exception handler includes it in the JSON body: `{"error": "INFRA_SERVICE_UNAVAILABLE", "request_id": "..."}`, finally matching the documented contract.

Kafka consumers don't have an HTTP request, so they get their own correlation concept: `event_id` (already present on most Kafka events per `kafka/producer.py`) doubles as the correlation key for consumer-side errors.

### 3.2 New table: `error_event`

```sql
CREATE TABLE error_event (
  error_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  fingerprint       VARCHAR(64)  NOT NULL,   -- sha256(exception_type + top_frame_location + normalized_message)
  exception_type    VARCHAR(200) NOT NULL,   -- e.g. "RuntimeError", "asyncpg.UniqueViolationError"
  message           TEXT,                    -- str(exc), truncated to 2000 chars, PII-scrubbed (see §6)
  traceback         TEXT,                    -- standard traceback.format_exc() text — frames + line numbers only,
                                              -- NEVER local variable values (see §6 — this is the PII guardrail)
  source            VARCHAR(30)  NOT NULL,   -- HTTP | KAFKA_CONSUMER | TEMPORAL_ACTIVITY
  source_detail     VARCHAR(200),            -- route path, consumer class name, or activity name
  request_id        UUID,                    -- correlates to the HTTP request (§3.1), NULL for consumer/activity errors
  event_id          UUID,                    -- correlates to the Kafka event (consumer errors only)
  tenant_id         UUID         REFERENCES tenant(tenant_id),  -- NULL for platform-level errors
  actor_type        VARCHAR(30),             -- mirrors audit_event's actor_type vocabulary
  actor_id          UUID,
  occurrence_count  INTEGER      NOT NULL DEFAULT 1,   -- incremented, not a new row, on repeat fingerprint (§4)
  first_seen_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  last_seen_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  status            VARCHAR(20)  NOT NULL DEFAULT 'NEW',
                     -- NEW | ACKNOWLEDGED | RESOLVED | IGNORED
                     -- IGNORED = engineer has marked a known-benign recurring warning as noise
  linked_incident_id UUID        REFERENCES incident(incident_id),  -- set when/if this graduates (§5)
  resolved_by       UUID,
  resolved_at       TIMESTAMPTZ,
  resolution_note   TEXT
);
CREATE UNIQUE INDEX idx_error_event_fingerprint_open ON error_event(fingerprint)
  WHERE status IN ('NEW', 'ACKNOWLEDGED');  -- one open row per fingerprint; resolved ones can recur as a new row
CREATE INDEX idx_error_event_last_seen ON error_event(last_seen_at DESC);
CREATE INDEX idx_error_event_tenant ON error_event(tenant_id, last_seen_at DESC) WHERE tenant_id IS NOT NULL;
```

**Retention:** this is operational/debugging data, not a compliance audit trail — it does *not* inherit `audit_event`'s 7-year retention requirement. Proposed: 90 days hot in YugabyteDB, then purge (no cold-tier archival needed — nobody needs a 3-year-old stack trace). A `platform_config` key (`error_event_retention_days`, default 90) governs this, consistent with the "never hardcode durations" rule.

---

## 4. Capture Mechanism (the "collection" half of your question)

New service: `services/error_observability_service.py` (zero Temporal imports, matching every other service in this codebase).

```python
class ErrorObservabilityService:
    async def record(self, *, exc: Exception, source: str, source_detail: str,
                      request_id=None, event_id=None, tenant_id=None,
                      actor_type=None, actor_id=None) -> str:
        """
        Upsert by fingerprint: new fingerprint -> INSERT (status=NEW).
        Existing open fingerprint -> UPDATE occurrence_count += 1, last_seen_at = NOW().
        Returns error_id.
        """
```

Three call sites, one per path identified in §1:

**A. HTTP layer** — `main.py`'s `unhandled_exception_handler` calls `ErrorObservabilityService.record(source="HTTP", source_detail=request.url.path, request_id=request.state.request_id, tenant_id=<from JWT if present>, ...)` before returning the same generic 500 response. Client-facing behavior is unchanged (never leak internals) — only the previously-nonexistent server-side trace changes.

**B. Kafka consumer layer** — a shared helper (`kafka/error_capture.py`), called from each consumer's outer `except Exception:` block instead of (or in addition to) the current bare `log.exception(...)`:
```python
except Exception as exc:
    await record_consumer_error(db_pool, consumer_name="NotifConsumer",
                                 event_type=etype, event_id=event.get("event_id"), exc=exc)
    log.exception("NotifConsumer error event_type=%s", etype)  # keep — stderr trace is still useful for live debugging
```
This is a mechanical, repeatable change across the ~20 consumers — same shape every time, not bespoke per consumer.

**C. Temporal activity layer — in scope for v1 (approved, not deferred).** Even though Temporal Web UI shows activity failures/retries natively, that visibility lives in the Temporal cluster's own UI, not PRANA's incident register — a CISO/PA reviewing incidents in the Portal would still miss it. A shared activity wrapper/interceptor records to `error_event` on final failure (after retries are exhausted, not on every transient retry attempt — a Temporal activity retry succeeding on attempt 2 is not an error worth surfacing, only permanent failure after `RetryPolicy.maximum_attempts` is exhausted). Implementation approach: a Temporal `Interceptor` (`ActivityInboundInterceptor.execute_activity`) that catches the final `ApplicationError`/exception before it propagates back to the workflow, records it via `ErrorObservabilityService`, then re-raises unchanged — so workflow behavior (retries, compensation, signals) is completely unaffected. `source="TEMPORAL_ACTIVITY"`, `source_detail=activity.info().activity_type`.

**Silent `except: pass` blocks (§1, path C):** these need to be found and either (a) converted to `except Exception as exc: await record(...)` where swallowing is genuinely correct behavior (e.g., "logging failure must never block the verification response" — the swallow is right, but it should still be *recorded*), or (b) left alone where a truly expected, non-error condition is being caught (e.g. `except ImportError: pass` for optional dependency detection in `main.py` — not every bare except is a bug). This needs a manual audit pass, not a mechanical find-replace — I'll enumerate the actual list for your review before touching any of them, if this design is approved.

---

## 5. When does a logged error become an `incident`? (avoiding alert fatigue)

This is the crux of "not everything is an incident." Proposed rule set, evaluated by a new scheduled workflow (§7):

| Condition | Action |
|---|---|
| Fingerprint touches a security/crypto/audit-critical path — **APPROVED finalized list** (§10 decision 2): `routers/auth_employee.py`, `routers/auth_oa.py`, `routers/auth_pa.py`, `routers/totp_setup.py`, `services/encryption_service.py`, `services/jwt_service.py`, `services/audit_integrity_service.py`, `workflows/audit_integrity.py`, `kafka/consumers/auth_consumer.py` | **Immediate incident on first occurrence**, severity **P1**. Can't wait for a pattern — a crypto-path exception is inherently high-stakes even once. |
| Fingerprint causes repeated 5xx on a compliance-critical endpoint (`/v1/dpdp/*`, `/v1/ingest/*`) | Incident after **3 occurrences within 10 minutes**, severity **P2**. |
| Fingerprint is genuinely new (never seen in the last 7 days) anywhere else | Incident after **1 occurrence**, severity **P2** — novel bugs deserve a look even before a pattern emerges; recurring *known* issues don't need to re-alert every time. |
| Everything else (routine consumer/background errors, including Temporal activity permanent failures per §4C) | Incident only after **occurrence_count crosses 10 within 15 minutes** — suggests systemic breakage, not one flaky message. Severity **P3**. |
| Any `error_event` row a human manually promotes via the UI (§7) | Immediate incident, severity chosen by the human at promotion time. |

When promoted: `IncidentService.create_incident(incident_type="APPLICATION_ERROR", severity=..., title=f"{exception_type} in {source_detail}", source_table="error_event", source_id=error_id)`, and `error_event.linked_incident_id` is set. From that point on, it's identical to every other incident — same SLA table, same escalation, same CISO/PA UI (§7) — this design doesn't invent a second incident lifecycle.

**Deliberately not proposed:** auto-resolving these incidents when the error stops recurring. Per the existing SLA framework, `service_incident` (health checks) auto-resolves because "is the service up" is a clean binary. "Did a bug get fixed" is not — silence for 20 minutes doesn't mean the underlying cause is gone. These always require an explicit resolution note, like P0/P1 security incidents do.

---

## 6. Privacy Guardrails (non-negotiable, per CLAUDE.md's Privacy Contract)

- **Never capture request/response bodies.** Only `exception_type`, `str(exc)` (truncated), and the standard `traceback.format_exc()` text.
- **Never capture local variable values.** Python's default traceback format already excludes these (it's frame/line info only, not a variable dump) — this design deliberately does *not* upgrade to a richer introspection library (e.g. `traceback_with_variables`) specifically because that class of tool is a realistic PAN/salary leak vector if a crypto or extraction function throws mid-computation with sensitive data still in scope.
- **Message scrubbing:** before writing `message`/`traceback` to the table, run the same never-log guardrail already established for OTPs/tokens/DEKs (`.claude/rules/security.md`: "Never log: PAN, passwords, OTP codes, tokens, DEKs") — regex-scrub anything PAN-shaped, JWT-shaped, or matching a known secret-field name, replacing with `[REDACTED]`. This needs to be a shared utility, not per-call-site discipline (per-call-site is exactly how the *current* gap happened).
- **90-day retention** (§3.2) limits exposure window even if something imperfect slips through scrubbing.

---

## 7. Visibility (Portal UI) — APPROVED: Option B

Folded into the existing PA/CISO incident-register screens as a new tab, reusing the existing
page shell rather than a standalone page:
- `prana-portal/src/pages/pa/SecurityIncidentRegister.tsx` gains an "Errors" tab alongside its
  existing incident list, backed by new `/admin/errors` endpoints (list, acknowledge, ignore,
  resolve, promote-to-incident) in `routers/pa_admin.py`.
- `prana-portal/src/pages/pa/IncidentRegister.tsx` (the health-incident page — currently broken,
  see the earlier session finding that it calls nonexistent `/pa/incidents*` paths instead of the
  real `/admin/incidents*`) gets that routing bug fixed as part of this work, since this design
  touches the same screen family anyway.
- CISO gets read/acknowledge/resolve access via a matching tab on
  `prana-portal/src/pages/ciso/SecurityIncidents.tsx`, backed by `/v1/ciso/errors`, tenant-scoped
  (CISO only sees `error_event` rows where `tenant_id` matches their own tenant or is NULL for
  platform-level errors visible to everyone).

New backend endpoints: list, acknowledge, ignore, resolve, promote-to-incident — same shape as
the existing `IncidentService` endpoints already in `pa_admin.py`/`ciso.py`.

---

## 8. Explicitly considered and not defaulted to: third-party error tracking (Sentry-class tools)

Worth being honest about the trade-off rather than silently picking the harder path:

| | In-house (this design) | Sentry-class SaaS |
|---|---|---|
| Matches existing architecture | Yes — same pattern as every other PRANA service | No — first third-party SaaS dependency of this kind |
| Stack trace grouping/fingerprinting quality | Basic (hash-based, as designed here) | Much more sophisticated, battle-tested |
| Alerting/on-call integrations (PagerDuty, Slack) | None — would need building | Built-in |
| Data residency / DPDP compliance | Stays in YugabyteDB, ap-south-1 | Depends on vendor region config, another vendor DPA to review |
| Implementation effort | Everything in §3–§7 | Mostly configuration + SDK install |

**APPROVED: in-house.** Matches PRANA's existing architecture and keeps everything in
ap-south-1 for DPDP data-residency reasons. §3–§7 stand as the implementation; §8 (Sentry-class
SaaS) is rejected for this iteration.

---

## 9. Implementation Plan (approved, in progress)

1. `RequestIDMiddleware` + fix the global handler's response contract (§3.1)
2. `error_event` table (migration + schema.sql)
3. `ErrorObservabilityService` (TDD)
4. Wire into HTTP global handler (§4A)
5. Wire into Kafka consumers via shared helper (§4B) — mechanical, ~20 call sites
6. Wire into Temporal activities via interceptor (§4C) — in scope for v1, not deferred
7. Manual audit of silent `except: pass` blocks — enumerate for review, don't auto-convert
8. `ErrorThresholdEvaluationWorkflow` (Pattern 3, Temporal Schedule) implementing §5's promotion rules
9. Portal UI (§7 — Option B, folded into existing incident registers), including fixing
   `IncidentRegister.tsx`'s pre-existing `/pa/incidents*` routing bug
10. Message taxonomy entries for the new `APPLICATION_ERROR` incident type + any new UI strings
11. Docs: `KAFKA_REDIS_ARCHITECTURE.md`, `workflows/CLAUDE.md` updated to reference this track

---

## 10. Decisions Log (resolved 2026-07-15)

| # | Decision | Resolution |
|---|---|---|
| 1 | In-house vs. Sentry-class SaaS | **In-house** (§3–§7); §8 rejected |
| 2 | Security/crypto-path first-occurrence severity | **Approved** — finalized file list in §5 |
| 3 | Noise thresholds (3-in-10-min / 10-in-15-min) | **Approved as originally proposed**, no tuning |
| 4 | UI placement | **Option B** — fold into existing `SecurityIncidentRegister.tsx` / `IncidentRegister.tsx` |
| 5 | v1 capture-layer scope | **Everything** — HTTP + Kafka + Temporal activities all ship together, no phase 2 deferral |
