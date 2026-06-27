# PRANA Internal Service Call Rules
# Auto-loaded when editing prana-ai/**
# ENFORCEMENT: scripts/enforce_rules.py — INTERNAL-01
# Run /enforce before any PR merge. Violations block deployment.

## The rule

| Caller | Callee | Path | Allowed? |
|--------|--------|------|----------|
| Browser / mobile app | prana-api | Internet → ALB → Kong → prana-api | YES — only path for external callers |
| HRMS system | prana-api | Internet → ALB → Kong → prana-api | YES — HMAC verified at Kong |
| prana-ai | prana-api | VPC-internal direct (port 8000) | YES — the ONE authorised bypass |
| prana-ask | prana-api | Proxied via prana-api (`/ask/*`) | YES — prana-api proxies to prana-ask |
| prana-ai | prana-api via Kong/ALB | Internet round-trip | **NO — INTERNAL-01 violation** |
| prana-ask | prana-api via Kong/ALB | Internet round-trip | **NO — INTERNAL-01 violation** |

## Why prana-ai gets a direct path

prana-ai is the AI pipeline worker. At Stage 06 it calls prana-api to:
- Update `document.pipeline_status` to ROUTED
- Trigger `DOC_ROUTED` Kafka event (via prana-api's Kafka producer)

Routing this through Kong would mean:
- Generating a service JWT for prana-ai to authenticate with Kong
- Paying ALB latency on every pipeline completion
- Exposing the callback on the public internet (even if Kong validates it)

The VPC-internal path is faster, simpler, and never touches the public network.

## How prana-ai must call prana-api

```python
# CORRECT — reads from env var, resolves to VPC-internal DNS
import os, httpx

PRANA_API_INTERNAL = os.environ["PRANA_API_INTERNAL_URL"]
# Value in ECS task definition: http://prana-api.prod.internal:8000

async def notify_routed(document_id: str, tenant_id: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{PRANA_API_INTERNAL}/internal/pipeline/routed",
            json={"document_id": document_id, "tenant_id": tenant_id},
            headers={"X-Internal-Service": "prana-ai"},
            timeout=10,
        )
```

```python
# WRONG — INTERNAL-01 will fire on this
await client.post("https://api.prana.in/internal/pipeline/routed", ...)
```

## The SG rule that enforces this at the network level

In `terraform/modules/networking/main.tf`:

```hcl
resource "aws_security_group_rule" "api_from_ai_internal" {
  # prana-ai SG → prana-api SG on port 8000
  # This is the ONLY authorised bypass of Kong.
}
```

prana-ask has NO equivalent rule — it has no reason to call prana-api directly.

## What INTERNAL-01 catches

Any URL in prana-ai source code matching a public domain pattern:
- `https://api.prana.in/...`
- `https://api-staging.prana.in/...`
- Any `https://*prana*.in` or similar public hostname

INTERNAL-01 does NOT fire on:
- `http://prana-api.prod.internal:8000` — correct internal DNS
- `http://localhost:8000` — dev environment
- `os.environ["PRANA_API_INTERNAL_URL"]` — env var reference (not a URL literal)
- Test files and scripts

## Adding new internal endpoints on prana-api

Internal-only endpoints (called only by prana-ai) must:
1. Live under `/internal/` prefix — never under `/v1/` (that's the public versioned API)
2. Validate the `X-Internal-Service: prana-ai` header — reject if missing
3. Never be mounted on Kong routes in `kong.yml`
4. Be documented here with the call site in prana-ai
