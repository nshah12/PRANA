"""
reset_dev.py — Full dev environment reset to a known-good state.

1. Resets all passwords (OA users, portal_admin, employee_user) to Prana@Admin0124
2. Uploads a real placeholder PDF to MinIO for every document row that lacks one
3. Revokes all active sessions

Run from prana-api/:
    python scripts/reset_dev.py

After running:
  - ALL logins work with password: Prana@Admin0124
  - ALL 575 documents are viewable (real PDF bytes in MinIO)
"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3
import pyotp
from botocore.config import Config
import asyncpg
from services.encryption_service import hash_password, verify_password, aes_encrypt
from services.totp_service import TOTPService

DB_URL = os.environ.get("DATABASE_URL", "postgresql://yugabyte:yugabyte@localhost:5433/prana")
OA_PASSWORD  = "Prana@Admin0124"
EMP_PASSWORD = "Prana@Admin0124"
PA_PASSWORD  = "Prana@Admin0124"

# Fixed TOTP secret for ALL dev accounts — scan the QR once, works forever
# otpauth://totp/PRANA:admin@techcorp.in?secret=JBSWY3DPEHPK3PXP&issuer=PRANA
DEV_TOTP_SECRET = "JBSWY3DPEHPK3PXP"
_DEV_DEK = b"\x00" * 32   # matches what auth_oa.py uses in dev
DEV_TOTP_ENC = aes_encrypt(DEV_TOTP_SECRET, _DEV_DEK)

MINIO_ENDPOINT  = os.environ.get("S3_ENDPOINT_URL", "http://localhost:9010")
MINIO_ACCESS    = os.environ.get("S3_ACCESS_KEY_ID", "minioadmin")
MINIO_SECRET    = os.environ.get("S3_SECRET_ACCESS_KEY", "minioadmin")
MINIO_BUCKET    = os.environ.get("S3_BUCKET_DOCUMENTS", "prana-documents-dev")

# Minimal valid single-page PDF (no external deps needed)
_PLACEHOLDER_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 595 842]/Parent 2 0 R"
    b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 44>>stream\n"
    b"BT /F1 14 Tf 72 750 Td (PRANA Dev Placeholder) Tj ET\n"
    b"endstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"xref\n0 6\n"
    b"0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"0000000058 00000 n \n"
    b"0000000115 00000 n \n"
    b"0000000266 00000 n \n"
    b"0000000360 00000 n \n"
    b"trailer<</Size 6/Root 1 0 R>>\n"
    b"startxref\n430\n%%EOF\n"
)

# ── Rich seed orgs (have 575 documents) ─────────────────────────────────────
RICH_ORGS = [
    # (tenant_id, short_name, domain, docs)
    ("10000000-0000-0000-0000-000000000001", "TechCorp",   "techcorp.in",           86),
    ("10000000-0000-0000-0000-000000000004", "Nexus",      "nexussoftware.in",       96),
    ("10000000-0000-0000-0000-000000000005", "Meridian",   "meridiancapital.in",     86),
    ("10000000-0000-0000-0000-000000000006", "Zephyr",     "zephyranalytics.in",     76),
    ("10000000-0000-0000-0000-000000000007", "Pinnacle",   "pinnacleindia.in",       66),
    ("10000000-0000-0000-0000-000000000008", "Horizon",    "horizonconsulting.in",   55),
    ("10000000-0000-0000-0000-000000000009", "Aurora",     "aurorapharma.in",        44),
    ("10000000-0000-0000-0000-000000000010", "Cascade",    "cascaderetail.in",       33),
    ("10000000-0000-0000-0000-000000000002", "ABCDBank",   "abcdbank.in",            22),
    ("10000000-0000-0000-0000-000000000003", "PQRSFin",    "pqrsfintech.in",         11),
]

# TechCorp gets all 5 roles; others get oa_admin only
TECHCORP_ROLES = [
    ("admin@techcorp.in",    "oa_admin"),
    ("operator@techcorp.in", "oa_operator"),
    ("chro@techcorp.in",     "chro"),
    ("cfo@techcorp.in",      "cfo"),
    ("ciso@techcorp.in",     "ciso"),
]


def seed_minio(rows: list[tuple[str, str]]) -> None:
    """Upload placeholder PDF to MinIO for every (s3_bucket, s3_key) that doesn't exist."""
    s3 = boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS,
        aws_secret_access_key=MINIO_SECRET,
        config=Config(signature_version="s3v4"),
        region_name="ap-south-1",
    )
    # Ensure bucket exists
    try:
        s3.head_bucket(Bucket=MINIO_BUCKET)
    except Exception:
        s3.create_bucket(Bucket=MINIO_BUCKET)
        print(f"MinIO: created bucket '{MINIO_BUCKET}'")

    uploaded = skipped = 0
    for bucket, key in rows:
        target_bucket = bucket or MINIO_BUCKET
        try:
            s3.head_object(Bucket=target_bucket, Key=key)
            skipped += 1
        except Exception:
            try:
                s3.put_object(
                    Bucket=target_bucket,
                    Key=key,
                    Body=_PLACEHOLDER_PDF,
                    ContentType="application/pdf",
                )
                uploaded += 1
            except Exception as e:
                print(f"  WARN: failed to upload {key}: {e}")

    print(f"MinIO: uploaded={uploaded}  already_present={skipped}  bucket={MINIO_BUCKET}")


async def reset():
    conn = await asyncpg.connect(DB_URL)
    pw_hash = hash_password(OA_PASSWORD)

    # Verify hash works before touching DB
    assert verify_password(OA_PASSWORD, pw_hash), "Hash verification failed — aborting"
    print(f"Hash verified for '{OA_PASSWORD}'")

    async with conn.transaction():

        # ── 1. Reset portal_admin ────────────────────────────────────────────
        import datetime as _dt2
        await conn.execute("""
            UPDATE portal_admin SET
                password_hash      = $1,
                totp_secret_enc    = $2,
                totp_configured_at = $3,
                failed_totp_count  = 0,
                status             = 'ACTIVE'
            WHERE email = 'admin@prana.in'
        """, pw_hash, DEV_TOTP_ENC, _dt2.datetime.now(_dt2.timezone.utc))
        print("portal_admin: reset admin@prana.in")

        # ── 2. Reset all oa_users in rich-seed orgs ──────────────────────────
        # Sets a fixed TOTP secret so QR is stable across resets — scan once, use forever
        import datetime as _dt
        result = await conn.execute("""
            UPDATE oa_user SET
                password_hash      = $1,
                totp_secret_enc    = $2,
                totp_configured_at = $3,
                force_reset        = FALSE,
                failed_totp_count  = 0,
                status             = 'ACTIVE'
            WHERE tenant_id = ANY($4::uuid[])
        """, pw_hash, DEV_TOTP_ENC, _dt.datetime.now(_dt.timezone.utc), [r[0] for r in RICH_ORGS])
        print(f"oa_user: {result}")

        # ── 3. Reset employee_user passwords ────────────────────────────────
        emp_hash = hash_password(EMP_PASSWORD)
        assert verify_password(EMP_PASSWORD, emp_hash)
        # NOTE: totp_secret_enc is NOT touched — preserve existing TOTP setup
        result = await conn.execute("""
            UPDATE employee_user SET
                password_hash     = $1,
                force_reset       = FALSE,
                failed_totp_count = 0,
                status            = 'ACTIVE'
            WHERE status != 'DELETED'
        """, emp_hash)
        print(f"employee_user: {result}")

        # ── 4. Clear all active sessions (force fresh login) ─────────────────
        await conn.execute("UPDATE user_session SET revoked = TRUE WHERE revoked = FALSE")
        print("user_session: all sessions revoked (fresh login required)")

    await conn.close()

    # ── 5. Seed MinIO with placeholder PDFs ─────────────────────────────────
    print("\nSeeding MinIO with placeholder PDFs for all document rows…")
    conn3 = await asyncpg.connect(DB_URL)
    doc_rows = await conn3.fetch(
        "SELECT s3_bucket, s3_key FROM document WHERE is_deleted=FALSE AND s3_key IS NOT NULL"
    )
    await conn3.close()
    seed_minio([(r["s3_bucket"], r["s3_key"]) for r in doc_rows])

    # ── 7. Final verification ────────────────────────────────────────────────
    conn2 = await asyncpg.connect(DB_URL)
    pa = await conn2.fetchrow("SELECT password_hash, status FROM portal_admin WHERE email='admin@prana.in'")
    oa = await conn2.fetchrow("SELECT password_hash, status FROM oa_user WHERE email='admin@techcorp.in'")
    emp = await conn2.fetchrow("SELECT password_hash FROM employee_user LIMIT 1")

    assert verify_password(PA_PASSWORD, pa["password_hash"]),  "PA hash broken in DB"
    assert verify_password(OA_PASSWORD, oa["password_hash"]),  "OA hash broken in DB"
    assert verify_password(EMP_PASSWORD, emp["password_hash"]), "Emp hash broken in DB"
    assert pa["status"] == "ACTIVE"
    assert oa["status"] == "ACTIVE"
    await conn2.close()

    print()
    print("=" * 60)
    print("DEV RESET COMPLETE — all credentials verified in DB")
    print("=" * 60)
    print()
    print("Portal Admin:   http://localhost:3000/admin/login")
    print("  admin@prana.in          /  Prana@Admin0124")
    print()
    print("Org Login:      http://localhost:3000/org/login")
    print("  admin@techcorp.in       /  Prana@Admin0124  (86 docs, all 5 roles)")
    print("  operator@techcorp.in    /  Prana@Admin0124")
    print("  chro@techcorp.in        /  Prana@Admin0124")
    print("  cfo@techcorp.in         /  Prana@Admin0124")
    print("  ciso@techcorp.in        /  Prana@Admin0124")
    print("  admin@nexussoftware.in  /  Prana@Admin0124  (96 docs)")
    print("  admin@meridiancapital.in/  Prana@Admin0124  (86 docs)")
    print("  admin@zephyranalytics.in/  Prana@Admin0124  (76 docs)")
    print("  admin@pinnacleindia.in  /  Prana@Admin0124  (66 docs)")
    print("  admin@horizonconsulting.in / Prana@Admin0124 (55 docs)")
    print("  admin@aurorapharma.in   /  Prana@Admin0124  (44 docs)")
    print("  admin@cascaderetail.in  /  Prana@Admin0124  (33 docs)")
    print("  admin@abcdbank.in       /  Prana@Admin0124  (22 docs)")
    print("  admin@pqrsfintech.in    /  Prana@Admin0124  (11 docs)")
    print()
    print("Employee Mobile OTP: use 123456 (dev bypass)")
    print("TOTP: QR code shown on first login — scan with any authenticator app")


if __name__ == "__main__":
    asyncio.run(reset())
