"""
PRANA API Version Registry — single source of truth for all versioning decisions.

HOW VERSIONING WORKS
--------------------
1. All public/HRMS-facing endpoints are prefixed: /v1/ingest/*, /v2/ingest/*
2. This file defines which versions are active, deprecated, or sunset
3. DeprecationMiddleware reads this file and adds Deprecation/Sunset headers automatically
4. The pre-production check script reads this file to flag deprecated callers in code

HOW TO ADD A NEW VERSION
-------------------------
1. Create prana-api/routers/v2/ directory with new router files
2. Import and mount under /v2 prefix in main.py
3. Add version entry below
4. Never modify existing v1 router behaviour — only add in v2

HOW TO DEPRECATE AN ENDPOINT
------------------------------
1. Add entry to DEPRECATED_ENDPOINTS with deprecated_on + sunset_on + successor
2. Notify HRMS partners via email (90-day minimum notice before sunset_on)
3. DeprecationMiddleware auto-adds headers — no code change needed in router
4. On sunset_on date: remove from router, update version status to "sunset"
"""

from datetime import date

# ── Active versions ────────────────────────────────────────────────────────────

VERSION_REGISTRY: dict[str, dict] = {
    "v1": {
        "status": "active",          # active | deprecated | sunset
        "released_on": "2025-01-01",
        "deprecated_on": None,       # set when deprecation notice sent to partners
        "sunset_on": None,           # set 90 days after deprecated_on
        "successor": None,
        "changelog": "prana-docs/API_CHANGELOG.md#v1",
    },
    # "v2": {
    #     "status": "active",
    #     "released_on": "2025-07-01",
    #     "deprecated_on": None,
    #     "sunset_on": None,
    #     "successor": None,
    #     "changelog": "prana-docs/API_CHANGELOG.md#v2",
    # },
}

# ── Deprecated individual endpoints ───────────────────────────────────────────
# Add here when a specific endpoint within an active version is being replaced
# but the whole version isn't deprecated yet.
#
# Example:
# DEPRECATED_ENDPOINTS: dict[str, dict] = {
#     "/v1/ingest/upload": {
#         "deprecated_on": date(2025, 6, 1),
#         "sunset_on": date(2025, 9, 1),          # 90 days minimum
#         "successor": "/v2/ingest/upload",
#         "reason": "New endpoint supports batch metadata and async status webhook",
#         "migration_guide": "https://docs.prana.in/migration/upload-v2",
#         "notify_sent": True,                    # flip to True after partner email sent
#     },
# }

DEPRECATED_ENDPOINTS: dict[str, dict] = {}


# ── Breaking change registry ───────────────────────────────────────────────────
# Document every breaking change here with the version it was introduced in.
# This is the source of truth for the API changelog.

BREAKING_CHANGES: list[dict] = [
    # {
    #     "version": "v2",
    #     "endpoint": "/v2/ingest/upload",
    #     "change": "Response now wraps in {document: {...}} instead of returning flat object",
    #     "migration": "Update response parsing: data.document.document_id not data.document_id",
    #     "date": date(2025, 7, 1),
    # },
]


# ── Helpers used by middleware and check script ────────────────────────────────

def is_deprecated_version(version: str) -> bool:
    v = VERSION_REGISTRY.get(version, {})
    return v.get("status") in ("deprecated", "sunset")


def is_sunset_version(version: str) -> bool:
    v = VERSION_REGISTRY.get(version, {})
    return v.get("status") == "sunset"


def get_deprecation_headers(path: str, version: str) -> dict[str, str]:
    """Returns HTTP headers to add to deprecated endpoint/version responses."""
    headers = {}

    # Check version-level deprecation
    v = VERSION_REGISTRY.get(version, {})
    if v.get("status") == "deprecated":
        headers["Deprecation"] = "true"
        if v.get("sunset_on"):
            headers["Sunset"] = v["sunset_on"].strftime("%a, %d %b %Y 23:59:59 GMT")
        if v.get("successor"):
            headers["Link"] = f'</{v["successor"]}/>; rel="successor-version"'

    # Check endpoint-level deprecation
    ep = DEPRECATED_ENDPOINTS.get(path, {})
    if ep:
        headers["Deprecation"] = f'date="{ep["deprecated_on"].isoformat()}"'
        if ep.get("sunset_on"):
            headers["Sunset"] = ep["sunset_on"].strftime("%a, %d %b %Y 23:59:59 GMT")
        if ep.get("successor"):
            headers["Link"] = f'<{ep["successor"]}>; rel="successor-version"'
        if ep.get("migration_guide"):
            headers["X-Migration-Guide"] = ep["migration_guide"]

    return headers
