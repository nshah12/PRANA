# PRANA Security Rules
# Auto-loaded always — security rules apply everywhere
# ENFORCEMENT: scripts/enforce_rules.py — SEC-01, SEC-02, SEC-03, SEC-04
# Run /enforce before any PR merge. Violations block deployment.

## Privacy Contract (NEVER violate)
- LLM input = full document data
- LLM output = insights ONLY — no raw ₹ salary, no PAN, no NIK
- Raw figures NEVER stored in DB
- Raw figures NEVER surfaced in any UI (mobile, portal, chatbot)

## PAN / NIK handling
- `pan_token` = HMAC-SHA256(PAN, platform_secret) — dedup key, safe to store
- `enc_pan` = FF3-1 FPE(PAN, employee_DEK) — reversible, stored encrypted
- No plaintext PAN/NIK ever in DB, logs, cache, or API response
- Cache key = `pan_token` only — never plaintext PAN

## Encryption stack
- Passwords: Argon2id (time=2, memory=65536, parallelism=2)
- TOTP secret + employee mobile number: real AWS KMS (platform-wide auth CMK,
  `resolve_platform_auth_kek_arn` / `KMSService.encrypt_value`/`decrypt_value`)
  — NOT a static app secret and NOT a tenant KEK. Both fields must stay
  decryptable regardless of tenant context (they're login credentials, not
  tenant-owned data), so they can't use per-tenant KEKs like PAN does; and a
  leaked static secret would decrypt every user's TOTP/mobile platform-wide in
  one shot with no audit trail, so they don't use `resolve_auth_dek` either.
  See `services/employee_service.py`'s `auth_kek_arn` docstring for the full
  reasoning. `resolve_auth_dek` (static, non-KMS) remains scoped to HRMS API-key
  signing secrets only.
- Document DEK: KMS envelope encryption (tenant KEK, AWS KMS ap-south-1)
- `temp_password_hash` takes priority over `password_hash` in login — must clear to NULL after force reset

## Auth & tenant isolation
- `tenant_id` ALWAYS from JWT claims — never from request body or URL params
- `user_id` ALWAYS from JWT claims — never trusted from client
- Check record ownership before returning — does this user own this document/record?
- Multi-tenant tables: RLS enforced + always WHERE tenant_id = $1

## Sensitive data rules
- Never log: PAN, passwords, OTP codes, tokens, DEKs
- Never return: password hashes, secrets, DEKs in API responses
- Mask sensitive fields in error messages
- Password-protected docs: processed in-memory, nothing persisted, session wiped on expiry (10 min)

## HTTP security
- Sensitive operations: POST not GET (GET params appear in server logs)
- Auth tokens: httpOnly cookies or Authorization header — never URL params
- Input validation at system boundaries — not internally

## CISO visibility rules
- CISO sees full IP address in access logs
- Employee sees city only — two separate response shapes, never the same endpoint
