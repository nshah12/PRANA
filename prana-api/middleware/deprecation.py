"""
DeprecationMiddleware — automatically adds Deprecation/Sunset/Link headers
to any response from a deprecated API version or endpoint.

No router changes needed. Add to main.py once and it covers all routes.
"""
import re
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from versioning import get_deprecation_headers, is_sunset_version

# Matches /v1/... or /v2/... etc
_VERSION_RE = re.compile(r"^/v(\d+)/")


class DeprecationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Extract version from URL
        match = _VERSION_RE.match(path)
        version = f"v{match.group(1)}" if match else None

        # Block sunset versions entirely — return 410 Gone
        if version and is_sunset_version(version):
            return Response(
                content=f'{{"error":"API_VERSION_SUNSET","message":"/{version} was sunset. '
                        f'See API changelog at /docs or prana-docs/API_CHANGELOG.md"}}',
                status_code=410,
                media_type="application/json",
            )

        response = await call_next(request)

        # Add deprecation headers if applicable
        if version:
            headers = get_deprecation_headers(path, version)
            for key, value in headers.items():
                response.headers[key] = value

        return response
