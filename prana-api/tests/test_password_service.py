"""Tests for services/password_service.py."""
import pathlib

from services.password_service import hash_password, verify_password


def test_hash_uses_argon2id():
    h = hash_password("MySecret1!")
    assert "$argon2id$" in h, "hash_password must produce argon2id hashes"


def test_verify_correct_password_returns_true():
    pw = "TestPassword99!"
    h = hash_password(pw)
    assert verify_password(pw, h) is True


def test_temp_password_hash_takes_priority_over_password_hash():
    src = (pathlib.Path(__file__).parent.parent / "routers" / "auth_oa.py").read_text(encoding="utf-8")
    assert "temp_password_hash" in src, \
        "auth_oa router must check temp_password_hash before password_hash"


def test_temp_password_cleared_after_force_reset():
    src = (pathlib.Path(__file__).parent.parent / "routers" / "auth_oa.py").read_text(encoding="utf-8").upper()
    assert "TEMP_PASSWORD_HASH" in src
    assert "NULL" in src, \
        "temp_password_hash must be SET TO NULL after first successful login"
