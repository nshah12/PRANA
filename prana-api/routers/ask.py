"""
Ask PRANA proxy endpoint.

Validates employee JWT, enforces rate limit, then proxies the query to prana-ask.
employee_user_id is taken from JWT claims — never from the request body.

Rate limit: ask_rate_limit_per_hour from platform_config (default 20/hr/employee).
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from dependencies import DbConn, require_employee, AuthUser
from config import get_settings

router = APIRouter()
RATE_LIMIT_KEY = "ask_rate:{employee_id}:{hour}"


class AskRequest(BaseModel):
    query: str


class AskResponse(BaseModel):
    answer: str


@router.post("", response_model=AskResponse)
async def ask(
    body: AskRequest,
    request: Request,
    db: DbConn,
    current=Depends(require_employee),
):
    # Rate limit check via Redis
    redis = request.app.state.redis
    from datetime import datetime, timezone
    hour_bucket = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H")
    rate_key = f"ask_rate:{current.user_id}:{hour_bucket}"

    count = await redis.incr(rate_key)
    if count == 1:
        await redis.expire(rate_key, 3600)   # expire after 1 hour

    # Rate limit from config (default 20)
    limit_row = await db.fetchval(
        """SELECT COALESCE(
            (SELECT config_value FROM tenant_config WHERE tenant_id=$1 AND config_key='ask_rate_limit_per_hour'),
            (SELECT config_value FROM platform_config WHERE config_key='ask_rate_limit_per_hour'),
            '20'
        )""",
        current.tenant_id,
    )
    rate_limit = int(limit_row or 20)

    if count > rate_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"RATE_LIMITED — {rate_limit} queries per hour allowed",
        )

    # Proxy to prana-ask
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)) as client:
            resp = await client.post(
                f"{settings.ask_service_url}/ask",
                headers={
                    "X-Prana-Ask-Secret": settings.ask_service_secret,
                    "X-Employee-ID": str(current.user_id),
                    "Content-Type": "application/json",
                },
                json={"query": body.query},
            )
            resp.raise_for_status()
            data = resp.json()
            return AskResponse(answer=data["answer"])

    except httpx.TimeoutException:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="ASK_SERVICE_TIMEOUT")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="ASK_SERVICE_ERROR")
