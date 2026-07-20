"""
RequestIDMiddleware — assigns a stable request_id to every request, stored on
request.state.request_id and echoed back as the X-Request-ID response header.

Prerequisite for the error-observability track (prana-docs/ERROR_OBSERVABILITY_DESIGN.md
§3.1): correlates an HTTP request to its log lines, error_event rows, and the
"request_id" field the API error contract has always documented but never actually
populated.
"""
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
