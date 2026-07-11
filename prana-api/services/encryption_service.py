import hashlib
import hmac
import os
import struct
import threading
from base64 import b64encode, b64decode
from typing import Callable, Optional

import boto3
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cachetools import TTLCache
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Argon2id params per PRANA spec: time=2, memory=65536, parallelism=2
_ph = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)


# ── Password hashing ───────────────────────────────────────────────────────────

def hash_password(plaintext: str) -> str:
    return _ph.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plaintext)
    except VerifyMismatchError:
        return False


def password_needs_rehash(hashed: str) -> bool:
    return _ph.check_needs_rehash(hashed)


# ── NIK / PAN token ───────────────────────────────────────────────────────────

# ── PAN token versioning ──────────────────────────────────────────────────────
# Version registry allows key rotation without invalidating all existing tokens.
# Existing rows keep their version number; new rows use the current default.
# On secret rotation: bump _CURRENT_PAN_TOKEN_VERSION, add a new algorithm entry,
# update pan_token_version lazily on next employee login.

_PAN_TOKEN_ALGOS: dict[int, Callable[[str, str], str]] = {
    1: lambda nik, secret: hmac.new(secret.encode(), nik.encode(), hashlib.sha256).hexdigest(),
}
_CURRENT_PAN_TOKEN_VERSION = 1


def register_pan_token_version(version: int, algo: Callable[[str, str], str]) -> None:
    """Register a new PAN token algorithm. Call during service startup for version > 1."""
    _PAN_TOKEN_ALGOS[version] = algo


def compute_pan_token(nik: str, platform_secret: str, version: int = 1) -> str:
    """
    HMAC-based cross-tenant deduplication key. One-way — NIK is never recoverable.
    Version 1 = HMAC-SHA256(NIK, platform_secret).
    Call this and immediately discard the raw NIK.
    """
    algo = _PAN_TOKEN_ALGOS.get(version)
    if not algo:
        raise ValueError(f"Unknown pan_token version: {version}")
    return algo(nik, platform_secret)


# ── KMS DEK cache ─────────────────────────────────────────────────────────────
# Caches decrypted DEK bytes in process memory to avoid a KMS round-trip on every
# document access. TTL=300s matches the Temporal activity heartbeat window.
# Cache key is a truncated SHA-256 of the ciphertext (enc_dek) — never the DEK itself.
# Max 1000 DEKs ≈ 32KB footprint. Cleared on process exit automatically.

_DEK_CACHE: TTLCache = TTLCache(maxsize=1000, ttl=300)
_DEK_LOCK = threading.Lock()


def _dek_cache_key(enc_dek: str) -> bytes:
    """Derive a short opaque cache key from the ciphertext. Never the plaintext DEK."""
    return hashlib.sha256(enc_dek.encode()).digest()[:16]


def clear_dek_cache() -> None:
    """Clear the DEK cache. Used in tests and for emergency key rotation."""
    with _DEK_LOCK:
        _DEK_CACHE.clear()


# ── Format-Preserving Encryption (FF3-1) ──────────────────────────────────────
# Per NIST SP 800-38G. Used for enc_pan so it remains visually PAN-shaped.
# Full FF3-1 requires a dedicated library (e.g. ff3 package).
# This module wraps it; the underlying call is: ff3.FF3Cipher(key, tweak).encrypt(nik)

def encrypt_nik_fpe(nik: str, dek: bytes, tweak: bytes = b"\x00" * 7) -> str:
    """
    FF3-1 Format-Preserving Encryption of NIK using the employee DEK.
    Output is same length and character class as input PAN (10 chars, AAAANNNNNA).
    """
    try:
        import ff3
    except ImportError as e:
        # NEVER degrade to a plaintext-derived placeholder (finding H2) — that would
        # leak the PAN. A missing crypto primitive is a hard failure.
        raise RuntimeError("ff3 package is required for FPE encryption of NIK/PAN") from e
    cipher = ff3.FF3Cipher.withCustomAlphabet(
        dek.hex(), tweak.hex(),
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    )
    return cipher.encrypt(nik.upper())


def decrypt_nik_fpe(enc_nik: str, dek: bytes, tweak: bytes = b"\x00" * 7) -> str:
    """
    Decrypt FF3-1 enc_pan back to NIK.
    Called ONLY inside the AI pipeline during extraction — result is used once and discarded.
    NEVER log or persist the return value.
    """
    try:
        import ff3
    except ImportError as e:
        raise RuntimeError("ff3 package is required for FPE decryption of NIK/PAN") from e
    cipher = ff3.FF3Cipher.withCustomAlphabet(
        dek.hex(), tweak.hex(),
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    )
    return cipher.decrypt(enc_nik.upper())


# ── AES-256-GCM ───────────────────────────────────────────────────────────────

def aes_encrypt(plaintext: str, key: bytes) -> str:
    """
    AES-256-GCM encrypt. Returns base64(nonce + tag + ciphertext).
    Used for totp_secret_enc, signing_secret_enc, ctc_annual (via DEK).
    """
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return b64encode(nonce + ct).decode()


def aes_decrypt(token: str, key: bytes) -> str:
    """AES-256-GCM decrypt. Inverse of aes_encrypt."""
    raw = b64decode(token)
    nonce, ct = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None).decode()


# ── DEK generation ────────────────────────────────────────────────────────────

def generate_dek() -> bytes:
    """Generate a 256-bit Data Encryption Key. Must be wrapped via KMS before storing."""
    return os.urandom(32)


# ── Auth encryption key (TOTP secrets + HRMS signing secrets) ──────────────────

_ZERO_KEY = b"\x00" * 32


def resolve_auth_dek(settings) -> bytes:
    """
    Return the 32-byte AES-256 key used to encrypt/decrypt TOTP secrets and HRMS
    signing secrets. Replaces the former hardcoded all-zero `dev_dek` (finding C1).

    - If settings.auth_encryption_key is set: use it (64 hex chars or base64 → 32 bytes).
      Rejects wrong length and the all-zero key.
    - Else in production: raise (a real key is mandatory; assert_production_ready also guards this).
    - Else (dev/test): derive a stable, NON-ZERO key from platform_hmac_secret so local
      dev works without AWS while never falling back to an all-zero key.
    """
    raw = getattr(settings, "auth_encryption_key", "") or ""
    if raw:
        try:
            key = bytes.fromhex(raw)
        except ValueError:
            key = b64decode(raw)
        if len(key) != 32:
            raise ValueError("auth_encryption_key must decode to exactly 32 bytes")
        if key == _ZERO_KEY:
            raise ValueError("auth_encryption_key must not be all-zero")
        return key

    if getattr(settings, "is_production", False):
        raise RuntimeError("auth_encryption_key is required in production")

    # Dev/test only: deterministic, non-zero derivation. NOT for production.
    return hashlib.sha256(b"prana-auth-dek-v1:" + settings.platform_hmac_secret.encode()).digest()


# ── AWS KMS envelope encryption ───────────────────────────────────────────────

class KMSService:
    """
    Envelope encryption via AWS KMS.
    Blast radius: DEK compromise = 1 employee. KEK compromise = 1 tenant.
    KMS key ARN is stored in tenant.kek_arn — never hardcoded here.
    """

    def __init__(self, region: str, access_key_id: str = "", secret_access_key: str = ""):
        kwargs: dict = {"region_name": region}
        if access_key_id:
            kwargs["aws_access_key_id"] = access_key_id
            kwargs["aws_secret_access_key"] = secret_access_key
        self._client = boto3.client("kms", **kwargs)

    def wrap_dek(self, dek: bytes, kek_arn: str) -> str:
        """KMS_Encrypt(DEK, KEK) → base64 ciphertext stored as enc_dek."""
        resp = self._client.encrypt(KeyId=kek_arn, Plaintext=dek)
        return b64encode(resp["CiphertextBlob"]).decode()

    def unwrap_dek(self, enc_dek: str, kek_arn: str) -> bytes:
        """
        KMS_Decrypt(enc_dek, KEK) → raw DEK bytes.
        Result is cached in-process for 5 minutes (TTL=300s) to avoid per-request KMS
        round-trips. Cache is keyed by SHA-256(enc_dek) — never by the plaintext DEK.
        """
        cache_key = _dek_cache_key(enc_dek)
        with _DEK_LOCK:
            cached = _DEK_CACHE.get(cache_key)
        if cached is not None:
            return cached

        resp = self._client.decrypt(
            CiphertextBlob=b64decode(enc_dek),
            KeyId=kek_arn,
        )
        dek: bytes = resp["Plaintext"]
        with _DEK_LOCK:
            _DEK_CACHE[cache_key] = dek
        return dek

    def sign_jwt(self, message: bytes, key_id: str) -> bytes:
        """RS256 sign via KMS — private key never leaves KMS."""
        resp = self._client.sign(
            KeyId=key_id,
            Message=message,
            MessageType="RAW",
            SigningAlgorithm="RSASSA_PKCS1_V1_5_SHA_256",
        )
        return resp["Signature"]
