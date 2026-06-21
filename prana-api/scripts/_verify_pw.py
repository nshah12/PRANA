import sys, asyncio
sys.path.insert(0, '.')
from services.encryption_service import verify_password, hash_password
import asyncpg

async def main():
    conn = await asyncpg.connect('postgresql://yugabyte:yugabyte@localhost:5433/prana')
    row = await conn.fetchrow("SELECT password_hash FROM portal_admin WHERE email='admin@prana.in'")
    h = row['password_hash']
    print('Hash in DB:', h)
    print('verify Prana@Admin0124:', verify_password('Prana@Admin0124', h))

    # Also check an oa_user
    row2 = await conn.fetchrow("SELECT password_hash FROM oa_user WHERE email='admin@techcorp.in'")
    h2 = row2['password_hash']
    print('OA hash in DB:', h2)
    print('verify OA Prana@Admin0124:', verify_password('Prana@Admin0124', h2))
    await conn.close()

asyncio.run(main())
