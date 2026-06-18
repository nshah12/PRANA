import pyotp

from services.encryption_service import aes_decrypt


class TOTPService:
    """
    RFC 6238 TOTP: 30-second window, 6 digits, ±1 window drift allowed.
    totp_secret is stored AES-256-GCM encrypted in DB as totp_secret_enc.
    """

    # ±1 window = 90-second validity window to handle clock drift
    _VALID_WINDOW = 1

    def verify(self, code: str, totp_secret_enc: str, dek: bytes) -> bool:
        """
        Decrypt TOTP secret and verify the provided code.
        Returns True only if code matches current or adjacent window.
        """
        secret = aes_decrypt(totp_secret_enc, dek)
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=self._VALID_WINDOW)

    def generate_secret(self) -> str:
        """Generate a new base32 TOTP secret for TOTP setup."""
        return pyotp.random_base32()

    def provisioning_uri(self, secret: str, account: str, issuer: str = "PRANA") -> str:
        """Returns the otpauth:// URI for QR code display during TOTP setup."""
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=account, issuer_name=issuer)

    def verify_backup_code(self, provided: str, code_hashes: list[str]) -> tuple[bool, str | None]:
        """
        Verify a backup code. Returns (matched, matched_hash).
        Caller must mark the matched backup_code row as used=TRUE immediately.
        """
        import hashlib
        h = hashlib.sha256(provided.encode()).hexdigest()
        if h in code_hashes:
            return True, h
        return False, None

    def generate_backup_codes(self, prefix: str, count: int = 8) -> list[tuple[str, str]]:
        """
        Generate count backup codes. Returns [(plaintext, sha256_hash), ...].
        Plaintext is shown once to the user — only hash is stored.
        Format: PREFIX-XXXX-XXXX
        """
        import secrets
        import hashlib
        codes = []
        for _ in range(count):
            part1 = secrets.token_hex(2).upper()
            part2 = secrets.token_hex(2).upper()
            plaintext = f"{prefix}-{part1}-{part2}"
            h = hashlib.sha256(plaintext.encode()).hexdigest()
            codes.append((plaintext, h))
        return codes
