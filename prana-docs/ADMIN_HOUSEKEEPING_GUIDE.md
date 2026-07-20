# PRANA Admin Housekeeping Guide

> Reference for OA-Admin and Portal Admin (PA) self-service account-maintenance
> actions in the Portal. For engineers: endpoint contracts. For support/ops:
> what each button does and who can press it.

All actions below follow the standard HTTP handler contract (validate → DB
write → Kafka publish → return 200) and are fully audited — every action
publishes a Kafka event consumed by `AuditConsumer`, which writes an
`audit_event` row and dual-writes it to Immudb (tamper-evident ledger, see
[`KAFKA_REDIS_ARCHITECTURE.md`](KAFKA_REDIS_ARCHITECTURE.md) §8). CISOs can
see every one of these actions in the OA Activity Audit screen.

PA actions that touch employee PII are a deliberate, narrow exception to
PA's normal "zero employee PII" boundary (see `pa_admin.py` docstring) —
each requires a mandatory `reason` field, logged with the action.

---

## 1. Reset employee TOTP

| | OA-Admin | Portal Admin |
|---|---|---|
| Endpoint | `POST /v1/org/employees/reset-totp` | `POST /admin/employees/reset-totp` |
| Scope | Own tenant only | Any tenant (platform override) |
| Requires `reason` | No | Yes |

Clears the employee's `totp_secret_enc` and forces re-enrollment on next
login. Use when an employee has lost their authenticator app/device.

## 2. Reset employee password

| | OA-Admin | Portal Admin |
|---|---|---|
| Endpoint | `POST /v1/org/employees/reset-password` | `POST /admin/employees/reset-password` |
| Scope | Own tenant only | Any tenant (platform override) |
| Requires `reason` | No | Yes |

Generates a one-time temporary password (returned in the response — shown
once to the admin, never logged) and sets `force_reset = TRUE` so the
employee must set a new password on next login.

## 3. PA-to-PA unlock

| Endpoint | `POST /admin/pa-users/unlock` |
|---|---|
| Who | Any active Portal Admin |
| Requires `reason` | No |

Unlocks a locked-out fellow Portal Admin account. This is the "someone
else holds the keys" recovery path referenced in `auth_pa.py` — a locked
PA cannot unlock themselves, only another active PA can.

## 4. Un-mark alumni / reactivate

| Endpoint | `POST /v1/org/employees/{employee_uuid}/reactivate` |
|---|---|
| Who | OA-Admin |
| Precondition | Employee status must currently be `ALUMNI` |

Reverses `mark_alumni` — clears `dol` and `push_window_expires`, sets
status back to `ACTIVE`, and records a `REJOINED` career event. Use when
an employee was marked alumni by mistake, or genuinely rejoins.

## 5. Bulk "sign out everywhere"

| Endpoint | `POST /v1/org/employees/{employee_uuid}/revoke-sessions` |
|---|---|
| Who | OA-Admin, CISO |

Revokes every active session for the employee in one action (e.g. after a
lost/stolen device report), instead of revoking sessions one at a time.

## 6. Bulk-revoke document shares

| Endpoint | `POST /v1/org/employees/{employee_uuid}/revoke-shares` |
|---|---|
| Who | OA-Admin, CISO |

Revokes every active document share link the employee has created —
immediately invalidates any outstanding share URLs and OTP sessions.

## 7. Bulk employee CSV import

| Endpoint | `POST /v1/org/employees/import` |
|---|---|
| Who | OA-Operator (and above) |
| Limits | 500 rows per file |
| Required columns | `nik`, `full_name`, `doj` |

Creates employees in bulk from a CSV. Each row is processed independently
— a bad row (missing field, bad date, duplicate NIK) is recorded as
`{"row": i, "error": <code>}` in the response without aborting the rest
of the batch.

## 8. Employee record merge/dedupe

| Endpoint | `POST /admin/employees/merge` |
|---|---|
| Who | Portal Admin only |
| Requires `reason` | Yes |

For PAN-typo duplicate identities — two `employee_user` rows that are
actually the same person. Re-points every table with a direct FK to
`employee_user_id` onto the canonical record inside one transaction, then
marks the duplicate `status = 'MERGED'` (never deletes it — see migration
`prana-db/migrations/038_employee_merge.sql`). Tables keyed by
`employee_master.employee_uuid` (documents, career events, etc.) are
untouched, since `employee_uuid` itself doesn't change in a merge.

**This is irreversible** — there is no "unmerge." Confirm identity match
carefully before running.

## 9. Resend OA welcome email

| Endpoint | `POST /v1/org/users/{oa_user_id}/resend-welcome` |
|---|---|
| Who | OA-Admin |

Re-triggers the `OA_WELCOME` email template via `NotifConsumer` — for when
the original welcome email bounced or the invite link expired.

---

## Explicitly not built

**Impersonate / "view as employee"** was considered and rejected as a
housekeeping tool — it's a genuine privacy risk (an admin viewing an
employee's vault as them) and isn't part of this feature set.
