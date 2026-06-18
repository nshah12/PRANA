# PRANA External Integrations Rules
# Auto-loaded when editing any integration service file

## Integration inventory

| System | Direction | Protocol | Auth | Purpose |
|--------|-----------|----------|------|---------|
| HRMS (SAP/Keka/Darwinbox/Zoho) | Inbound | REST API | HMAC-signed API key | Push documents to PRANA |
| AWS SES | Outbound | AWS SDK | IAM role | OA user emails, OTP emails |
| SMS (MSG91 / Exotel) | Outbound | REST | API key | Employee OTP delivery |
| WhatsApp WABA | Outbound | REST | Bearer token | Document routed notifications |
| EPFO (PF portal) | Outbound | Scrape/API | UAN + password (employer) | PF statement verification |
| AWS KMS | Outbound | AWS SDK | IAM role | DEK encryption/decryption |
| AWS S3 / MinIO | Outbound | AWS SDK / S3-compat | IAM / access key | Document storage |
| AWS Textract | Outbound | AWS SDK | IAM role | OCR fallback |
| Tesseract | Local | subprocess | none | OCR primary |
| Qdrant | Outbound | REST | API key | Vector embeddings (prana-ask) |
| Temporal | Outbound | gRPC SDK | mTLS | Workflow orchestration |

---

## HRMS Inbound Integration

### Auth contract (never change without partner notice)
```
Header: X-PRANA-Key-ID: {api_key_id}
Header: X-PRANA-Signature: HMAC-SHA256(request_body_bytes, signing_secret)
```
- `tenant_id` comes from `api_key.tenant_id` — NEVER from request body
- Verify signature before any processing — reject 401 if mismatch
- `api_key.key_hash` = SHA256(api_key_id) — never store plaintext key

### HRMS push endpoint behaviour
```
validate signature → validate payload → S3 put → INSERT document → kafka.publish(DOC_INGESTED) → 202
```
Return 202 immediately. Never wait for pipeline completion.

### HRMS error responses
HRMS systems have retry logic. Make endpoints idempotent:
- Duplicate document_id → return 200 (not 409) with existing status
- Include `request_id` in every response for HRMS-side logging

---

## SMS Integration (Employee OTP)

### Provider: MSG91 (primary) / Exotel (fallback)
- Never hardcode provider — use `platform_config.sms_provider`
- OTP is 6 digits, valid 10 minutes (from `platform_config.otp_ttl_minutes`)
- Phone format: always E.164 (`+919000000001`) — store and send with country code
- Never log OTP value — only log `otp_sent: true` with request_id

### Retry rules
- 1 retry after 30s on network failure
- No retry on 4xx (bad number, DND) — log and surface to user
- Circuit breaker: if 5 consecutive failures → fallback to Exotel

### Rate limiting
- Max 3 OTP requests per phone per 10 minutes (enforce in DB, not just memory)
- Block phone after 10 OTP requests in 1 hour → require support intervention

---

## Email Integration (AWS SES)

### Who sends what
| Trigger | Template | Recipient |
|---------|---------|-----------|
| OA user created | `OA_WELCOME` | New OA user (work email) |
| Document routed | `DOC_ROUTED` | Employee (personal email if provided) |
| Exception raised | `EXCEPTION_ALERT` | OA-Operator |
| Elevation approved | `ELEVATION_APPROVED` | OA-Operator |
| DPDP erasure complete | `ERASURE_COMPLETE` | Employee |

- All email dispatch via `NotifConsumer` — NEVER directly in HTTP handler
- Template IDs in `platform_config` — never hardcode template strings in code
- SES sending identity: verify domain `prana.in` in ap-south-1
- Bounce/complaint handling: SES SNS → webhook → flag employee email as invalid

### Never send to
- Work email after employee marks as alumni (employer no longer valid contact)
- Any email that has bounced or complained (check `email_suppression` table)

---

## EPFO (Provident Fund) Integration

### What it does
- Verifies PF balance and contribution history from EPFO portal
- Used in Stage 04 (Resolution) to cross-verify UAN against employee identity
- UAN stored encrypted in `employee_master.uan` (not PAN — UAN is less sensitive)

### How to call
- EPFO has no public API — use EPFO unified portal scraping or third-party UAN verification service
- Credentials: employer's EPFO login — stored in `tenant_config.epfo_*` encrypted fields
- Never cache EPFO responses > 24 hours — data changes with each payroll run
- Timeout: 30s — EPFO portal is slow. Always async, never in HTTP path.

### Data handling
- PF balance amount: extract for verification ONLY — never store the raw amount
- Store: `pf_verified: true/false`, `uan_match: true/false` — not the balance figure
- Privacy contract applies: no raw ₹ figures stored

---

## WhatsApp WABA Integration

### Use cases
- Document routed notification: "Your salary slip for April is ready in PRANA"
- Exception alert to employee: "Your document needs attention"

### Rules
- Message templates must be pre-approved by Meta — never freeform messages
- Template IDs in `platform_config.whatsapp_template_*`
- Phone number = same as SMS (`+91` E.164 format)
- If WhatsApp delivery fails → fallback to SMS → fallback to email (in that order)
- Opt-out: respect `employee_user.whatsapp_opt_out = TRUE` — never send if opted out

---

## General Integration Rules (all external calls)

### Timeouts — always set explicit timeouts
| Integration | Connect timeout | Read timeout |
|-------------|----------------|-------------|
| SMS | 5s | 10s |
| SES | 5s | 15s |
| EPFO | 10s | 30s |
| KMS | 3s | 10s |
| Textract | 10s | 120s |
| Qdrant | 3s | 30s |

### Retries
- Idempotent operations (GET, KMS decrypt): retry up to 3x with exponential backoff
- Non-idempotent (SMS send, email send): retry only once with dedup key
- Never retry on 4xx — these are client errors, retrying won't help

### Circuit breakers
- After 5 consecutive failures on any integration → open circuit for 60s
- Log circuit state changes as audit events
- Fallback: SMS → Email, Textract → Tesseract, primary KMS → secondary KMS

### Secrets — never in code
All integration credentials in environment variables:
```
SMS_API_KEY, SES_REGION, EPFO_ENCRYPT_KEY,
WHATSAPP_TOKEN, QDRANT_API_KEY
```
Rotate via AWS Secrets Manager — never manual env var changes in prod.

### Never call external integrations from HTTP path
All outbound calls (SMS, email, WhatsApp, EPFO) via Kafka consumers:
- HTTP handler → kafka.publish(event) → NotifConsumer → external call
- Exception: KMS and S3 (synchronous, required for document handling)
