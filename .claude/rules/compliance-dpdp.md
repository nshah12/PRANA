# PRANA DPDP Act 2023 Compliance Rules
# Auto-loaded when editing prana-api/routers/compliance.py, prana-api/routers/dpdp.py

## DPDP Act 2023 — 5 employee rights PRANA must honour

| Right | Endpoint | Workflow | SLA |
|-------|---------|---------|-----|
| **Erasure** | POST `/dpdp/erasure-request` | `ErasureWorkflow` | 30 days |
| **Export** | POST `/dpdp/export-request` | `DataExportWorkflow` | 72 hours |
| **Correction** | POST `/dpdp/correction-request` | `CorrectionWorkflow` | 15 days |
| **Consent withdrawal** | POST `/dpdp/consent/withdraw` | `ConsentWithdrawalWorkflow` | Immediate |
| **Grievance** | POST `/dpdp/grievance` | `GrievanceWorkflow` | 48 hours acknowledgement |

## Erasure rules (most complex)
- Erases: `employee_user`, `employee_master`, `document` (soft delete + S3 delete)
- Does NOT erase: `audit_event` rows (7-year legal retention overrides erasure right)
- Does NOT erase: documents under active legal hold
- Sends confirmation email via SES after completion
- `pan_token` is retained for cross-tenant dedup integrity — only PII fields are erased

## Consent model
- Consent is per-tenant per-purpose — not a single global flag
- `consent_log` table tracks every grant and withdrawal with timestamp
- Processing is only lawful if `consent_log` has an active grant for that purpose
- Withdrawal is immediate — no grace period
- After withdrawal: stop all processing for that purpose, notify relevant services via Kafka

## Audit log retention
- **7 years** — non-negotiable, legal requirement
- Hot (queryable): YugabyteDB `audit_event` table — last 2 years
- Cold (archival): Apache Iceberg on S3 — older than 2 years
- Migration to cold: `AuditArchivalWorkflow` runs on schedule
- **Never delete audit_event rows** — even on erasure request

## Grievance Officer
- Every tenant must have a Grievance Officer configured in `tenant_config.grievance_officer_*`
- Grievance acknowledgement within 48 hours — `GrievanceWorkflow` sends auto-ack
- Resolution within 30 days — escalates to Portal Admin if unresolved

## What NOT to do
- Never process employee data after consent withdrawal for that purpose
- Never erase audit logs even if employee requests it — explain the legal exception
- Never skip the Temporal workflow for compliance actions — they need audit trails and retry
- Never hardcode SLA days — always from `platform_config.dpdp_erasure_sla_days` etc.
