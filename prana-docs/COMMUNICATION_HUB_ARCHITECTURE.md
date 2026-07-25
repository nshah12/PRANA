# PRANA — Communication Hub Architecture

> **Status: BUILT and DECIDED — same "DECIDED, not optional" treatment as `KAFKA_REDIS_ARCHITECTURE.md`.**
> Live-run verified end-to-end 2026-07-24 (real Kafka events pushed through the actual
> running stack, not just mocked tests). See §11 for the current done-vs-pending state —
> most of this doc is built and confirmed working; a few items remain genuinely open.

---

## 1. Why (current-state problem, verified against real code on 2026-07-23)

Every domain event that needs to reach a human today decides its **channel** itself, in
one of two inconsistent, redundant ways:

**Path A — inline per-handler logic.** `NotifConsumer` (`prana-api/kafka/consumers/notif_consumer.py`,
listens on `prana.notifications`) has ~15 `_handle_*` methods, each hardcoding its own
channel choice: `_handle_anomaly` decides P0/P1 → email+bell, P2 → bell-only, P3 → nothing;
`_handle_employee_welcome` decides SMS-if-mobile-present + email-if-email-present; and so
on. Sixteen different business events, sixteen different hand-written channel decisions.

**Path B — callers pick a channel and skip NotifConsumer entirely.** Four call sites
already publish straight to a per-channel topic instead of `prana.notifications`:
`kafka/consumers/oa_user_consumer.py:125,175`, `kafka/consumers/statutory_consumer.py:101`,
`services/alumni_service.py:437,457`, `services/analytics_service.py:119` — each one calls
`kafka.notify_email()` or `kafka.notify_bell()` directly, deciding the channel itself.

**Both paths converge on the same channel dispatch, but not consistently.** The five
per-channel consumers (`EmailConsumer`, `SMSConsumer`, `PushConsumer`, `WhatsAppConsumer`,
`BellConsumer` — one per topic in the table below) each call
`NotificationService.notify(channel=<hardcoded to match their own topic>)` — the exact same
method `NotifConsumer` also calls, just reached by a different route.
`EmailConsumer`'s own docstring says "Replaces the email logic from old NotifConsumer" —
this looks like a migration that was started (splitting `NotifConsumer` into per-channel
consumers) and never finished; `NotifConsumer` was never decommissioned, so today both the
old and new paths are live simultaneously.

**Net effect:**
- No single place decides "for message kind X, which channel(s)." That decision is
  scattered across ~20 call sites in 6 different files.
- No vendor failover anywhere. `SMSService`/`EmailService` each pick **one** vendor from
  config and stop — if it fails, the message is simply lost (logged, not retried,
  no fallback). `.claude/rules/integrations.md` already *describes* a fallback policy
  ("WhatsApp fails → SMS → email", "5 consecutive MSG91 failures → Exotel") that was never
  implemented in code anywhere.
- No per-tenant vendor choice. Every tenant gets whatever `sms_provider`/`email_provider`
  the whole platform is configured with.
- IVR doesn't exist as a channel at all yet.

## 2. Target architecture

```
                              ┌─────────────────────────────────────────┐
Any producer                 │        Communication Hub                │
(consumer, service,          │        (prana.communications.events)    │
Temporal activity)           │                                          │
                              │  1. Look up channel policy for this     │
   kafka.communication_      │     NotificationTemplate                │
   requested({               │     (tenant_config → platform_config    │
     template_id,             ────►  fallback — same resolution order   │
     recipient_id,           │     already used everywhere else)       │
     recipient_type,         │  2. For each decided channel, publish    │
     tenant_id,               ────►  to that channel's own topic        │
     template_data,          │                                          │
   })                        └───────────┬───────────┬───────────┬──────┘
                                          │           │           │
                              prana.notifications.{email,sms,whatsapp,ivr,portal_bell}
                                          │           │           │
                              ┌───────────▼───┐  ┌────▼────┐ ┌────▼─────┐
                              │ EmailConsumer │  │SMSConsumer│ │IVRConsumer│  ... (channel adapters)
                              │  ↓            │  │  ↓        │ │  ↓        │
                              │ EmailService  │  │SMSService │ │IVRService │
                              │ (vendor chain,│  │(vendor    │ │(vendor    │
                              │  circuit      │  │ chain,    │ │ chain,    │
                              │  breaker)     │  │ breaker)  │ │ breaker)  │
                              └───────────────┘  └───────────┘ └───────────┘
```

**No producer ever names a channel.** It names a `NotificationTemplate` (the same 23-member
enum already in `prana-api/messages.py`) and a recipient. The Hub — not the caller — decides
single- or multi-channel based on config. This is the one rule that matters:
**nothing outside the Hub and the channel adapters may call a channel vendor SDK, or
construct `EmailService`/`SMSService`/`WhatsAppService`/`IVRService` directly.** Enforced,
not just documented — see §6.

### 2.1 Kafka topics — 1 new, 4 reused, 1 renamed in spirit (not literally)

| Topic | Change | Consumer |
|---|---|---|
| `prana.communications.events` | **NEW** — replaces `prana.notifications` as the intake topic | `CommunicationHubConsumer` (renamed/repurposed from `NotifConsumer`) |
| `prana.notifications.email` | unchanged | `EmailConsumer` (becomes a real channel adapter, stops calling `NotificationService.notify()`) |
| `prana.notifications.sms` | unchanged | `SMSConsumer` (ditto) |
| `prana.notifications.whatsapp` | unchanged | `WhatsAppConsumer` (ditto — also becomes the first *real* WhatsApp implementation; today it's a stub) |
| `prana.notifications.portal_bell` | unchanged | `BellConsumer` (ditto — portal bell has no vendor, so no failover needed here, just a DB write) |
| `prana.notifications.ivr` | **NEW** | `IVRConsumer` (**NEW**) |
| `prana.notifications.push` | **unchanged, out of scope for this doc** | `PushConsumer` — push notifications aren't a "vendor" channel in the SES/SMS/IVR sense (they go through Expo/FCM, already device-token-based, no vendor-chain question) — leave as-is |

`prana.notifications` (the old intake topic) is retired once every existing producer moves
to `communication_requested()`. `TOPIC_NOTIF` constant and every direct-channel publish
(`notify_email()`/`notify_bell()`/etc. called from *outside* the Hub) are deleted — see
migration plan §7.

## 3. Channel policy — who decides "email, or email+SMS, or all three"

New table `notification_channel_policy` — same single-table, nullable-`tenant_id`,
partial-unique-index shape already used by `setup_checklist_item` (not
`severity_classification_rule`'s domain/priority shape, and deliberately not
`platform_config`/`tenant_config`'s two-table split — a plain `UNIQUE(template_id,
tenant_id)` doesn't actually work here, since Postgres/Yugabyte treat `NULL` as distinct
for uniqueness, so two platform-default rows for the same template would silently be
allowed; `setup_checklist_item`'s partial-index technique is what closes that):

```sql
CREATE TABLE notification_channel_policy (
  policy_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  template_id   VARCHAR(60)  NOT NULL,      -- NotificationTemplate member, e.g. 'ANOMALY_P0_ALERT'
  tenant_id     UUID         REFERENCES tenant(tenant_id) ON DELETE CASCADE,  -- NULL = platform default
  channels      TEXT[]       NOT NULL,      -- e.g. ARRAY['email','portal_bell']
  updated_by    UUID,
  updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX uidx_channel_policy_platform ON notification_channel_policy(template_id)
  WHERE tenant_id IS NULL;
CREATE UNIQUE INDEX uidx_channel_policy_tenant ON notification_channel_policy(template_id, tenant_id)
  WHERE tenant_id IS NOT NULL;
```

Resolution (override, not `setup_checklist_item`'s additive union): `SELECT channels FROM
notification_channel_policy WHERE template_id=$1 AND tenant_id=$2` → if no row, fall back to
`WHERE template_id=$1 AND tenant_id IS NULL` (the platform default row, one per
`NotificationTemplate` member, seeded at migration time from today's inline logic — e.g.
`ANOMALY_P0_ALERT` seeds to `{email, portal_bell}`, `ANOMALY_P2_ALERT` seeds to
`{portal_bell}`). Same tenant-then-platform-fallback *order* as every other config lookup in
this codebase, just expressed against a dedicated table instead of `platform_config`/
`tenant_config` — a plain scalar `TEXT` column can't hold an ordered channel list cleanly,
which is why this isn't just another `platform_config` row the way vendor chains are (§4).

PA and OA-Admin both get a settings screen for this — in scope for the first build, not
deferred. See §8.

## 4. Vendor chain + circuit breaker (per channel, per tenant)

New config keys, read via the existing `ConfigService.get(key, tenant_id)` (tenant →
platform fallback, nothing new):

| Key | Example value | Default (platform) |
|---|---|---|
| `email_vendor_chain` | `["ses", "smtp"]` | `["ses"]` |
| `sms_vendor_chain` | `["msg91", "exotel", "aws"]` | `["aws", "exotel", "msg91"]` |
| `whatsapp_vendor_chain` | `["waba"]` | `["waba"]` (single vendor for v1 — see §8) |
| `ivr_vendor_chain` | `["exotel", "ozonetel"]` | `["exotel", "ozonetel"]` |

Each channel adapter (`EmailService`, `SMSService`, new `IVRService`, new `WhatsAppService`)
gets the same shape of change:

```python
async def send(self, tenant_id: str, ...) -> tuple[bool, Optional[str]]:
    chain = await self._config.get_list(f"{self.CHANNEL_KEY}_vendor_chain", tenant_id)
    for vendor in chain:
        if await self._circuit_open(vendor):
            continue   # skip a vendor that's already tripped
        sent, error = await self._dispatch(vendor, ...)
        if sent:
            return True, None
        await self._record_failure(vendor)   # trips breaker after N consecutive failures
    return False, "all vendors in chain exhausted"
```

**Circuit breaker state lives in Redis** (`circuit:{channel}:{vendor}` → failure count +
open-until timestamp) — matches how this codebase already uses Redis for exactly this kind
of ephemeral, cross-pod-instance state (JWT revocation, rate limiting), not a new mechanism.
Per `integrations.md`'s already-documented (never-built) rule: open after 5 consecutive
failures, stay open 60s, matching the "General Integration Rules" section's existing
circuit-breaker text.

**Cross-channel fallback is a Hub-level decision, not a channel-adapter one.** If the Hub
decided `[whatsapp, sms]` for a message and the WhatsApp adapter reports its *entire* vendor
chain exhausted, the Hub — which already published to both topics independently — doesn't
need to do anything extra for this case since SMS was already dispatched in parallel. True
sequential cross-channel fallback (only try SMS *if* WhatsApp fully failed) needs the Hub to
wait for a delivery-result event before deciding to fan out to the next channel — flagged in
§8 as a v2 concern, not required for the first build unless you want it now.

## 5. IVR — new channel

`IVRService` (new), same shape as `SMSService`/`EmailService`. Exotel and Ozonetel both
expose an IVR-campaign/call API (initiate outbound call, play a message or connect to a
flow) alongside their SMS APIs — configured the same way SMS already is
(`ivr_vendor_chain`, plus `exotel_ivr_flow_id`/`ozonetel_*` settings analogous to
`exotel_sid`/`exotel_api_key`). Scope for v1: outbound call triggered by a
`NotificationTemplate`, same interface as every other channel
(`send(to=phone, subject=..., body=...)` — `subject` maps to nothing for IVR, `body` maps to
the flow/message ID to play, not raw text-to-speech content, since neither vendor's
outbound-call API takes freeform text for a triggered notification call).

## 6. Enforcement — `COMM-01`

New `enforce_rules.py` check, same style as `KAFKA-01`:

- **Blocks**: any `boto3.client("ses"/"sns", ...)`, any WhatsApp/Exotel/Ozonetel/MSG91 SDK
  import or raw `httpx` call to those vendor domains, or any `EmailService()` /
  `SMSService()` / `WhatsAppService()` / `IVRService()` construction, **outside**
  `services/email_service.py`, `services/sms_service.py`, `services/whatsapp_service.py`,
  `services/ivr_service.py`, and the Hub's own consumer files.
- **Also blocks**: any `kafka.notify_email()`/`notify_sms()`/`notify_whatsapp()`/
  `notify_bell()` call from anywhere except `CommunicationHubConsumer` itself (this is what
  closes Path B from §1 — nobody else gets to publish straight to a channel topic).
- Exempt: test files (same as every other rule).

## 7. Migration plan (concrete, file-by-file)

1. `kafka/producer.py`: add `communication_requested(event)` → publishes to
   `prana.communications.events`. Remove `notify_email()`/`notify_sms()`/`notify_push()`/
   `notify_whatsapp()`/`notify_bell()` as public methods callable from outside — fold their
   bodies into `CommunicationHubConsumer` only.
2. `kafka/consumers/notif_consumer.py` → rename/rewrite as `communication_hub_consumer.py`.
   Delete every `_handle_*` method's inline channel decision; replace with one lookup against
   `notification_channel_policy` + fan-out publish to the decided channel topic(s).
3. The 4 direct-callers found in §1 (`oa_user_consumer.py`, `statutory_consumer.py`,
   `alumni_service.py`, `analytics_service.py`) switch from `kafka.notify_email()`/
   `notify_bell()` to `kafka.communication_requested()` with the right `template_id`.
4. `kafka/consumers/{email,sms,whatsapp,bell}_consumer.py`: stop calling
   `NotificationService.notify()`. Each becomes a thin adapter: read `notification_log`
   write itself (or keep `NotificationService` around *only* for the `notification_log`
   write helper, stripped of all channel-dispatch logic — smaller decision, flag for
   discussion) → call its own `{Channel}Service.send(...)`.
5. New: `services/whatsapp_service.py`, `services/ivr_service.py`,
   `kafka/consumers/ivr_consumer.py`. `services/sms_service.py`/`email_service.py` gain the
   vendor-chain-loop + circuit-breaker shape from §4 (currently: pick one vendor from a
   single config string, no chain, no breaker).
6. `prana-db/schema.sql`: add `notification_channel_policy` (§3). Migration script seeds one
   platform-default row per `NotificationTemplate` member from today's inline decisions
   (documented 1:1 in `prana-docs/wireframes/notification_incident_matrix.html`, which is
   already the authoritative source for "which channels does each template use today").
7. `config.py`: add `{channel}_vendor_chain` platform defaults (§4), `exotel_ivr_*`/
   `ozonetel_*` settings.
8. `scripts/enforce_rules.py`: add `COMM-01` (§6).
9. TDD throughout, per this repo's standing rule — every new/changed file gets real
   invocation tests, not source-inspection-only ones (the lesson from this session's
   Temporal-schedule sweep applies here too: a test that never actually calls the vendor
   dispatch code can't catch a wrong import or wrong argument).
10. New PA + OA-Admin router endpoints and portal screens per §8 (in scope for this build,
    not deferred).

## 8. Portal UI — one screen per role, not one shared screen

Same split this codebase already uses everywhere else a platform-vs-tenant boundary exists
(CISO sees full IP, employee sees city-level only; PA sees every tenant, OA-Admin sees its
own) — reused here, not invented fresh. Two dedicated screens, backed by the same
`notification_channel_policy` table and `{channel}_vendor_chain` config keys, each showing
a different slice:

### 8.1 Platform Admin — `prana-portal/src/pages/pa/CommunicationSettings.tsx`

Mirrors `IncidentPolicyConfig.tsx`'s existing tab layout. Full control, platform-wide:

- **Channel Policy tab** — one row per `NotificationTemplate` (all 23), editable
  channel-set, applies as the platform default (`tenant_id IS NULL` row).
- **Vendor Chains tab** — per channel (email/SMS/WhatsApp/IVR), ordered vendor list +
  which vendors are actually enabled (have credentials configured) — an OA-Admin can only
  ever choose among vendors PA has turned on here.
- **Vendor Credentials tab** — API keys/secrets per vendor (`exotel_sid`, `msg91_auth_key`,
  etc.). **Never exposed to OA-Admin, at all** — same secrets-are-platform-only boundary
  already applied to KMS/HMAC keys elsewhere in this system.

Backing endpoints (`pa_admin.py`, mirrors the existing `sla-policy`/`severity-rules`
pattern): `GET/PATCH /admin/communications/channel-policy`,
`GET/PATCH /admin/communications/vendor-chains`,
`GET/PATCH /admin/communications/vendor-credentials`.

### 8.2 OA-Admin — `prana-portal/src/pages/oa/CommunicationSettings.tsx`

Mirrors `HRMSSettings.tsx`'s existing pattern (a dedicated OA-side settings screen for one
integration domain, separate from the generic `OrgSettings.tsx`). Scoped-down, tenant-only:

- **Channel Policy tab** — same 23 rows, but editing here writes a `tenant_id`-scoped
  override row, never touches the platform-default row. An OA-Admin can narrow channels
  (e.g. turn off WhatsApp for their org) or reorder among what's available — cannot invent a
  channel PA hasn't enabled platform-wide.
- **Vendor Chain preference tab** — reorder/disable among the vendors PA already enabled
  (§8.1's Vendor Chains tab is the ceiling; this is the tenant's choice within it). No
  credential fields at all — an OA-Admin never sees or sets a vendor secret.

Backing endpoints, alongside the existing `org_settings.py` (same file, new routes —
same pattern as that file already having both `/settings` and `/profile`):
`GET/PATCH /v1/org/communications/channel-policy`,
`GET/PATCH /v1/org/communications/vendor-chains`.

## 9. Immudb audit trail for config changes

Checked against real code first: PA's *existing* comparable config-editing endpoints
(`PATCH /admin/sla-policy/{severity}`, `POST/PATCH /admin/severity-rules*` in
`pa_admin.py`) publish **no** audit event today — they only set `updated_by`/`updated_at`
columns, which aren't tamper-evident (a compromised app credential could rewrite either).
Given how security-sensitive "who gets alerted, on which channel" is, the Hub's config
writes don't repeat that gap, and the pre-existing gap in `sla-policy`/`severity-rules` gets
retrofitted alongside it rather than left as a wider inconsistency (§10.3).

| Action | Immudb-audited? | Mechanism |
|---|---|---|
| Channel policy changed (PA default or OA-Admin override) | **Yes** | `kafka.tenant_event({"event_type": "COMM_CHANNEL_POLICY_UPDATED", "tenant_id": ..., "template_id": ..., "old_channels": [...], "new_channels": [...], "actor_id": ...})` |
| Vendor chain changed (PA default or OA-Admin override) | **Yes** | Same helper, `event_type="COMM_VENDOR_CHAIN_UPDATED"` |
| Vendor credential rotated (PA only) | **Yes** | Same helper, `event_type="COMM_VENDOR_CREDENTIAL_ROTATED"` — payload never contains the secret itself, same as `KEK_ROTATED` logging the rotation without the key material |
| Routine message dispatch (an email/SMS actually sent) | **No** | Stays in `notification_log` only — operational volume, not a security-relevant state change; matches `notify_email()`/etc. being explicitly out of Immudb scope today (`KAFKA_REDIS_ARCHITECTURE.md` §8.2) |
| Circuit breaker trips (a vendor going down) | **No** | Redis state only, same class as other ops-health signals |

### 10.1 Why `tenant_event()` and not a new mechanism

`kafka.tenant_event()` already publishes to `TOPIC_AUDIT` → `AuditConsumer` →
`audit_event` row → dual-written to Immudb — the exact pipeline `KAFKA_REDIS_ARCHITECTURE.md`
§8 documents. No new plumbing, three new event types flowing through the existing one. For
PA's platform-default edits (no tenant), `tenant_id` is `None` in the payload — already a
supported case (`AUDIT_INTEGRITY_MISMATCH` does exactly this today).

### 10.2 `KAFKA_REDIS_ARCHITECTURE.md` §8.2 update

Once built, the three new event types get added to that doc's existing scope table under
`tenant_event()`'s "Yes" row (alongside `TENANT_CREATED`, `TENANT_CONFIG_UPDATED`,
`API_KEY_CREATED/REVOKED`, `KEK_ROTATED`) — that table is the authoritative "what reaches
Immudb" reference and must stay accurate, not just this doc.

### 10.3 Retrofit: `sla-policy` / `severity-rules` (pre-existing gap, not new scope creep)

`update_sla_policy` and `create_severity_rule`/`update_severity_rule` in `pa_admin.py` gain
the same `kafka.tenant_event(tenant_id=None, event_type="SLA_POLICY_UPDATED" /
"SEVERITY_RULE_CREATED" / "SEVERITY_RULE_UPDATED", ...)` call, immediately after their
existing DB write, mirroring the pattern being built fresh for §10's three new event types.
No behavior change to the endpoints themselves — purely additive audit coverage.

## 10. Explicitly out of scope for v1 (flagging, not deciding silently)

- **WhatsApp multi-vendor.** WABA (WhatsApp Business API, via Meta directly or a BSP like
  Gupshup/Twilio) is the only real option most Indian deployments use; a second WhatsApp
  vendor isn't obviously useful the way a second SMS/IVR vendor is. Chain shape is there
  (`whatsapp_vendor_chain`) in case you want one later, but v1 ships with one entry.
- **True sequential cross-channel fallback** (wait for WhatsApp's actual delivery result
  before deciding to also try SMS, vs. today's proposal of "Hub fans out to all decided
  channels in parallel"). Sequential fallback needs delivery-status callbacks per vendor
  (WABA and most SMS gateways support delivery webhooks; IVR less reliably), which is a
  bigger lift — flagging as a real v2, not silently downgrading it into what's built now.

## 11. Current status (2026-07-24) — done vs. pending

Verified by actually restarting the running dev stack and pushing real events through it
(topics, DB, Redis) — not inferred from source reading or mocked tests alone. See
`prana-docs/PREPROD_TESTING_CHECKLIST.md` §0 for why that distinction matters here; three of
the "done" items below only fully worked after live-run-only bugs (never caught by any
mocked unit test) were found and fixed the same day — listed under §11.3 so they're not lost.

### 11.1 Done and live-verified

| Item | Evidence |
|---|---|
| `CommunicationHubConsumer` (§2, §7.2) | Real event published to `prana.communications.events` and `prana.notifications`, consumed with zero lag, correctly fanned out to per-channel topics |
| `notification_channel_policy` + resolution (§3) | Live query returned real policy row (`DOC_ROUTED` → `{push, whatsapp}`) |
| Vendor chain + circuit breaker (§4) | `EmailService`/`SMSService`/`WhatsAppService`/`IVRService` all read `{channel}_vendor_chain` via `ConfigService.get_list()` |
| `IVRService` (§5) | Rewritten against Ozonetel's real KooKoo API (GET `outbound.php`, real param names, XML-body success check) — was previously unverified against real docs |
| `COMM-01` enforcement (§6) | Active in `scripts/enforce_rules.py`, passes clean |
| Migration (§7) — all 10 steps | `notif_consumer.py` retired, 4 direct-callers migrated, new consumers registered in `main.py`, schema/config additions all present |
| PA + OA-Admin Communication Settings screens (§8) | Channel Policy, Vendor Chains, and Vendor Credentials tabs all built; Vendor Credentials tab edits a real field via a real `PATCH` endpoint (was read-only/cosmetic when first built — fixed same session) |
| Immudb audit trail (§9) incl. §10.3 retrofit | `COMM_CHANNEL_POLICY_UPDATED`/`COMM_VENDOR_CHAIN_UPDATED`/`COMM_VENDOR_CREDENTIAL_ROTATED` all publish via `tenant_event()`; `sla-policy`/`severity-rules` retrofitted alongside |
| Vendor-chain cache staleness | `ConfigService.invalidate()`/`invalidate_all()` now called from `update_vendor_chain()` — a platform-default edit no longer serves a stale chain to every tenant for up to 5 min. Verified live against the real Redis container, not just mocks |
| WhatsApp template variables | `WhatsAppConsumer` now actually passes `template_data` through as ordered `template_params` — was fetched and silently discarded before |

### 11.2 Explicitly out of scope for v1 (§10, unchanged — deliberate, not forgotten)

- WhatsApp multi-vendor — chain shape exists, ships with one entry (`waba`)
- True sequential cross-channel fallback — Hub fans out in parallel today, no delivery-callback-driven sequencing
- **Push channel — still a stub**, no real FCM/APNs backend (`services/notification_service.py` logs a stub dispatch). This was declared out of scope for *this doc's* vendor-chain rewrite (§2.1) because push has no vendor-chain question — but that's a scoping statement about this redesign, not a claim that push works. It doesn't. `prana-docs/wireframes/notification_incident_matrix.html` previously marked Push-involving rows as fully "Active"/"YES" — corrected 2026-07-24 to show which channel in each row is real vs. stub.
- No real external vendor account has been exercised end-to-end (Meta WABA production token/template, real Ozonetel/Exotel/MSG91 account, real SES domain) — everything above is verified against the real internal pipeline (Kafka → Hub → channel adapter → vendor client construction), not against a live third-party API call. That step needs real credentials supplied by you; it can't be completed unilaterally.

### 11.3 Live-run-only bugs found and fixed 2026-07-24 (not caught by any mocked test)

These aren't Communication Hub design gaps, but they were blocking a genuine live run of it,
so they're logged here rather than only in git history:

- `prana-db/kafka-init.sh` never provisioned `prana.communications.events` /
  `prana.notifications.ivr` — the exact class of gap this script's own comments already
  warned about (`prana.cache.invalidation` had the same issue previously).
- `employee_user.whatsapp_opt_out` was queried by `WhatsAppConsumer` but never existed in
  `schema.sql` — every real WhatsApp dispatch crashed. Column added.
- `employee_user.enc_mobile` was typed `VARCHAR(100)` — too small for real KMS ciphertext
  output. Widened to `TEXT` (matches `totp_secret_enc`'s existing correct type).
- The dev database itself was schema-drifted from `schema.sql` (still had a legacy plaintext
  `mobile` column instead of `mobile_token`/`enc_mobile`) — added the real columns and
  backfilled all 510 existing rows via the app's actual KMS/HMAC code.
- Root logger had no handler configured anywhere in `prana-api` — every `log.info()` call
  across every Kafka consumer, including every dispatch confirmation, was silently dropped.
  Fixed via `logging.basicConfig` + new `log_level` setting.
