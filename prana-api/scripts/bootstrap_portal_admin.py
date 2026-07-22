"""
bootstrap_portal_admin.py — Create the first Portal Admin account in a fresh environment.

schema.sql seeds zero portal_admin rows by design (no backdoor superuser in
production). Run this exactly once per environment (pre-prod, prod) before
anyone can log in via /admin/login at all.

Run from prana-api/:
    python scripts/bootstrap_portal_admin.py --email admin@prana.in

Prompts for a password interactively (never pass it as a CLI arg — it would
land in shell history). Enforces the same minimum-16-char policy the
password-reset endpoint enforces. TOTP is NOT configured here — the account
shows the QR setup screen on first login, same as every other account.
"""
import argparse
import asyncio
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg
from services.encryption_service import hash_password

DB_URL = os.environ.get("DATABASE_URL", "postgresql://yugabyte:yugabyte@localhost:5433/prana")
MIN_PASSWORD_LEN = 16


async def bootstrap(email: str, password: str) -> None:
    if not email.endswith("@prana.in"):
        raise SystemExit("Portal Admin email must end in @prana.in (schema constraint chk_pa_domain).")
    if len(password) < MIN_PASSWORD_LEN:
        raise SystemExit(f"Password must be at least {MIN_PASSWORD_LEN} characters.")

    conn = await asyncpg.connect(DB_URL)
    try:
        existing = await conn.fetchval("SELECT COUNT(*) FROM portal_admin")
        if existing:
            raise SystemExit(
                f"portal_admin already has {existing} row(s) — refusing to bootstrap again. "
                "Use the existing PA login flow (or its password-reset endpoint) instead."
            )

        pw_hash = hash_password(password)
        pa_id = await conn.fetchval(
            """
            INSERT INTO portal_admin (email, password_hash, status)
            VALUES ($1, $2, 'ACTIVE')
            RETURNING pa_id
            """,
            email, pw_hash,
        )
        print(f"Portal Admin created: {email} (pa_id={pa_id})")
        print("TOTP not configured — QR setup screen will show on first login at /admin/login.")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Must end in @prana.in")
    args = parser.parse_args()

    password = getpass.getpass("New Portal Admin password (min 16 chars): ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords did not match.")

    asyncio.run(bootstrap(args.email, password))


if __name__ == "__main__":
    main()
