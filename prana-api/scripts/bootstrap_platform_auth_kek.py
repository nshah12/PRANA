"""
bootstrap_platform_auth_kek.py — Create the ONE platform-wide auth CMK.

This CMK encrypts mobile numbers (employee_user.enc_mobile) and TOTP secrets
(employee_user/oa_user/portal_admin.totp_secret_enc). Unlike tenant KEKs
(created per-tenant at tenant onboarding) or the old static auth_encryption_key
secret, this key is provisioned exactly ONCE per environment, before that.

Run from prana-api/:
    python scripts/bootstrap_platform_auth_kek.py

Prints the resulting ARN — set it as PLATFORM_AUTH_KEK_ARN (dev: docker-compose
env var; prod: Secrets Manager / deployment config) before any code path that
encrypts/decrypts mobile numbers or TOTP secrets is exercised.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.encryption_service import KMSService

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
KMS_ENDPOINT_URL = os.environ.get("KMS_ENDPOINT_URL", "")  # LocalStack in dev


def main() -> None:
    kms = KMSService(
        region=AWS_REGION,
        access_key_id=AWS_ACCESS_KEY_ID,
        secret_access_key=AWS_SECRET_ACCESS_KEY,
        endpoint_url=KMS_ENDPOINT_URL,
    )
    arn = kms.create_platform_auth_kek()
    print("Platform auth CMK created.")
    print(f"ARN: {arn}")
    print()
    print("Set this before running any employee-creation, login, or TOTP-setup flow:")
    print(f"  PLATFORM_AUTH_KEK_ARN={arn}")


if __name__ == "__main__":
    main()
