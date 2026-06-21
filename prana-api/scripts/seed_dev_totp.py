"""
Seed a known TOTP secret for dev OA users so you can log in without going through
the TOTP setup flow every time.

Uses the same dev_dek = b"\x00" * 32 as auth_oa.py and auth_employee.py.

Usage:
    cd prana-api
    python scripts/seed_dev_totp.py

Then add this TOTP secret to your authenticator app manually (Settings > Enter key):
    Secret:  JBSWY3DPEHPK3PXP
    Account: prana-dev

Or use any 30-second TOTP app: Google Authenticator, Authy, 1Password.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add prana-api to path so we can import services
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.encryption_service import aes_encrypt
import asyncpg

# The known dev TOTP secret — add this to your authenticator app
DEV_TOTP_SECRET = "JBSWY3DPEHPK3PXP"
DEV_DEK = b"\x00" * 32   # dev placeholder, matches auth_oa.py


async def main():
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://prana:prana@localhost:5432/prana_dev",
    )
    conn = await asyncpg.connect(db_url)
    try:
        enc_secret = aes_encrypt(DEV_TOTP_SECRET, DEV_DEK)

        result = await conn.execute(
            """
            UPDATE oa_user
            SET totp_secret_enc = $1,
                totp_configured_at = NOW(),
                force_reset = FALSE
            WHERE totp_secret_enc IS NULL
            """,
            enc_secret,
        )
        count = int(result.split()[-1])
        print(f"Updated {count} OA user(s) with dev TOTP secret.")
        print()
        print("Add this to your authenticator app (Settings > Enter key manually):")
        print(f"  Secret : {DEV_TOTP_SECRET}")
        print(f"  Account: prana-dev  (or any label you like)")
        print()
        print("Dev login credentials:")
        print("  admin@techcorp.in    / DevEmp@123")
        print("  admin@nexussoftware.in / DevEmp@123")
        print("  (all OA admins in the seed — same TOTP secret)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
