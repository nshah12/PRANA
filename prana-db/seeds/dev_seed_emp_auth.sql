-- Dev seed patch: employee_user test credentials for auth testing
-- Run AFTER dev_seed.sql
-- Employee 001 — fully activated, password + TOTP ready
--
-- Login details:
--   Mobile:   +919000000001   (or just: 9000000001)
--   Email:    emp001@test.prana
--   Password: DevEmp@123
--   TOTP secret (add to Google Authenticator / Authy):
--     EU7WKZ66KHJKHQJY3UUPZKJOYPWJNFE4
--   TOTP URI (scan this QR):
--     otpauth://totp/PRANA:Dev%20Employee%20001?secret=EU7WKZ66KHJKHQJY3UUPZKJOYPWJNFE4&issuer=PRANA
--
-- totp_secret_enc below is AES-256-GCM-encrypted under the CURRENT
-- resolve_auth_dek() (services/encryption_service.py), derived from
-- platform_hmac_secret in dev. If that secret ever changes, this ciphertext
-- will fail to decrypt (cryptography.exceptions.InvalidTag) — regenerate it
-- with: aes_encrypt('EU7WKZ66KHJKHQJY3UUPZKJOYPWJNFE4', resolve_auth_dek(get_settings()))

UPDATE employee_user
SET
  password_hash       = '$argon2id$v=19$m=65536,t=2,p=2$baYcXT1/UniSJz2fTYDqFw$GDKNb23LwWjCbZLx8aH9yyifEEL9CG6cClG6dk3Xsgk',
  totp_secret_enc     = 'cnawEDwo/pA9hJp/UUun5EMk0aoEMy5drGsGnC/Imy6CaOkbBYnUZKBOyDD9Rj00DSHY/AmtI1u4JK8B',
  totp_configured_at  = NOW(),
  consent_status      = 'GRANTED',
  force_reset         = FALSE,
  status              = 'ACTIVE',
  email               = 'emp001@test.prana'
WHERE employee_user_id = '30000000-0000-0000-0000-000000000001';

-- Employee 002 — force_reset=TRUE (tests first-login password change flow)
--   Mobile:   +919000000002
--   Password: TempPass@999  (must be changed on first login)
UPDATE employee_user
SET
  password_hash       = '$argon2id$v=19$m=65536,t=2,p=2$baYcXT1/UniSJz2fTYDqFw$GDKNb23LwWjCbZLx8aH9yyifEEL9CG6cClG6dk3Xsgk',
  force_reset         = TRUE,
  consent_status      = 'PENDING',
  status              = 'ACTIVE',
  email               = 'emp002@test.prana'
WHERE employee_user_id = '30000000-0000-0000-0000-000000000002';
