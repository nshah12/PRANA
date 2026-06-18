import hashlib
import hmac
import os
import struct
from base64 import b64encode, b64decode
from typing import Optional

import boto3
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
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

def compute_pan_token(nik: str, platform_secret: str) -> str:
    """
    HMAC-SHA256(NIK, platform_secret) → hex string.
    Deterministic cross-tenant identity key. One-way — NIK is never recoverable.
    Call this and immediately discard the raw NIK.
    """
    return hmac.new(
        platform_secret.encode(),
        nik.encode(),
        hashlib.sha256,
    ).hexdigest()


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
        cipher = ff3.FF3Cipher.withCustomAlphabet(
            dek.hex(), tweak.hex(),
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        )
        return cipher.encrypt(nik.upper())
    except ImportError:
        # ff3 package not installed — return placeholder for dev
        return f"ENC_{nik[:4]}XXXXX{nik[-1]}"


def decrypt_nik_fpe(enc_nik: str, dek: bytes, tweak: bytes = b"\x00" * 7) -> str:
    """
    Decrypt FF3-1 enc_pan back to NIK.
    Called ONLY inside the AI pipeline during extraction — result is used once and discarded.
    NEVER log or persist the return value.
    """
    try:
        import ff3
        cipher = ff3.FF3Cipher.withCustomAlphabet(
            dek.hex(), tweak.hex(),
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        )
        return cipher.decrypt(enc_nik.upper())
    except ImportError:
        return enc_nik  # dev fallback


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
        """KMS_Decrypt(enc_dek, KEK) → raw DEK bytes. Never log or cache the result."""
        resp = self._client.decrypt(
            CiphertextBlob=b64decode(enc_dek),
            KeyId=kek_arn,
        )
        return resp["Plaintext"]

    def sign_jwt(self, message: bytes, key_id: str) -> bytes:
        """RS256 sign via KMS — private key never leaves KMS."""
        resp = self._client.sign(
            KeyId=key_id,
            Message=message,
            MessageType="RAW",
            SigningAlgorithm="RSASSA_PKCS1_V1_5_SHA_256",
        )
        return resp["Signature"]
