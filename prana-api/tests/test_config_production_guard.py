"""Tests for production fail-closed secret guard (config.Settings.assert_production_ready).

Security contract (findings C2/C3): in production the app must REFUSE to start on
placeholder/dev-default secrets. Outside production the guard is a no-op so local dev
and CI keep working with their throwaway defaults.
"""
import pytest

from config import Settings


def _prod(**over) -> Settings:
    """A production Settings with all real (non-default) secrets, overridable per-test."""
    base = dict(
        app_env="production",
        platform_hmac_secret="a-real-strong-platform-secret-01",
        db_password="a-real-db-password",
        ai_service_secret="a-real-ai-secret",
        ask_service_secret="a-real-ask-secret",
        immudb_password="a-real-immudb-password",
        auth_encryption_key="ab" * 32,                       # 32 bytes hex, non-zero
        jwt_kms_key_id="arn:aws:kms:ap-south-1:123:key/abc",
    )
    base.update(over)
    return Settings(**base)


def test_is_production_true_only_for_production():
    assert _prod().is_production is True
    assert Settings(app_env="development").is_production is False
    assert Settings(app_env="test").is_production is False


def test_prod_ready_with_all_real_secrets_passes():
    _prod().assert_production_ready()  # must not raise


def test_prod_rejects_dev_platform_secret():
    with pytest.raises(RuntimeError) as e:
        _prod(platform_hmac_secret="dev_secret").assert_production_ready()
    assert "platform_hmac_secret" in str(e.value)


def test_prod_rejects_dev_db_password():
    with pytest.raises(RuntimeError) as e:
        _prod(db_password="yugabyte").assert_production_ready()
    assert "db_password" in str(e.value)


def test_prod_rejects_dev_service_secrets():
    with pytest.raises(RuntimeError):
        _prod(ai_service_secret="dev-secret").assert_production_ready()
    with pytest.raises(RuntimeError):
        _prod(ask_service_secret="dev-secret").assert_production_ready()


def test_prod_rejects_dev_immudb_password():
    with pytest.raises(RuntimeError) as e:
        _prod(immudb_password="immudb").assert_production_ready()
    assert "immudb_password" in str(e.value)


def test_prod_rejects_missing_auth_encryption_key():
    with pytest.raises(RuntimeError) as e:
        _prod(auth_encryption_key="").assert_production_ready()
    assert "auth_encryption_key" in str(e.value)


def test_prod_rejects_missing_jwt_kms_key():
    with pytest.raises(RuntimeError) as e:
        _prod(jwt_kms_key_id="").assert_production_ready()
    assert "jwt_kms_key_id" in str(e.value)


def test_prod_error_lists_all_violations_at_once():
    """Operator should see every misconfiguration in one shot, not fix-one-at-a-time."""
    with pytest.raises(RuntimeError) as e:
        _prod(platform_hmac_secret="dev_secret", db_password="yugabyte",
              auth_encryption_key="").assert_production_ready()
    msg = str(e.value)
    assert "platform_hmac_secret" in msg
    assert "db_password" in msg
    assert "auth_encryption_key" in msg


def test_non_production_never_raises_even_with_dev_defaults():
    # Both dev and test run entirely on dev defaults — guard must be a no-op.
    Settings(app_env="development").assert_production_ready()
    Settings(app_env="test").assert_production_ready()
