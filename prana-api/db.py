import asyncpg
from typing import AsyncGenerator
from fastapi import Request


async def create_pool(dsn: str, min_size: int, max_size: int) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=dsn,
        min_size=min_size,
        max_size=max_size,
        command_timeout=30,
        # YugabyteDB: serializable isolation for financial data
        init=_set_session_defaults,
    )


async def _set_session_defaults(conn: asyncpg.Connection) -> None:
    await conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    await conn.execute("SET application_name = 'prana-api'")


async def get_db(request: Request) -> AsyncGenerator[asyncpg.Connection, None]:
    """FastAPI dependency — yields a single connection from the pool."""
    async with request.app.state.db_pool.acquire() as conn:
        yield conn
