# PRANA Document Sharing & Watermarking Rules
# Auto-loaded when editing prana-api/routers/vault.py or share_access.py

## Share token flow
```
Employee creates share → POST /vault/share → returns {share_token, otp_channel}
Recipient visits share URL → GET /share/{token} → prompted for OTP
Recipient enters OTP → POST /share/{token}/verify → 10-min session
Recipient views document → watermarked, read-only, no download
Session expires → access revoked automatically
```

## Share token rules
- TTL: from `platform_config.share_otp_ttl_minutes` (default 10) — never hardcoded
- OTP: 6 digits, sent via SMS or email to recipient
- Token stored in Redis with TTL — `share:{token}` namespace
- Max active shares per document: from `platform_config.share_max_active`
- Share can be revoked by employee at any time: DELETE /vault/share/{token}

## Watermark rules
- Applied server-side on every document access — never client-side
- Watermark content: recipient name + access timestamp + share token (last 8 chars)
- `document_access_log.watermark_applied = TRUE` for every share access
- Employee own access: watermark with employee name + timestamp
- NEVER serve unwatermarked document bytes to any external party

## Access log — every access is recorded
Every call to get document bytes writes to `document_access_log`:
```python
# Required fields — never skip any
document_id, employee_user_id, employee_uuid, tenant_id,
actor_type, actor_id, access_type,  # VIEW | DOWNLOAD | SHARE
access_channel,  # MOBILE | PORTAL | SHARE_LINK
ip_address, session_id, watermark_applied, accessed_at
```
`ip_address` is NOT NULL — always capture, never skip.

## Password-protected documents
- Employee provides password in time-limited session (10 minutes max)
- Decryption in-memory ONLY — never write decrypted bytes to disk or cache
- Session object wiped on expiry — no residual data
- If session expires mid-view: force re-authentication, never extend automatically
- `platform_config.password_doc_session_minutes` controls TTL — never hardcode 10

## CISO visibility
- CISO can see full IP address in `document_access_log`
- Employee sees city-level only (derived from IP, never raw IP)
- Two separate API response shapes — never reuse same endpoint for both
- `document_access_log.is_flagged` — CISO can flag suspicious access for review
