"""
AnalyticsService — business logic behind workflows/intelligence.py's
activities (CareerInsightWorkflow, AnomalyAcknowledgementWorkflow,
DigestWorkflow, PeerBenchmarkWorkflow, SkillGapWorkflow, MarketCompWorkflow).
Zero Temporal imports.

VaultCompletenessWorkflow removed 2026-08-06 — it was never triggered by
anything (dead code); its richer 3-category scoring formula was merged into
EmployeeLifecycleService.recompute_vault_completeness, the one actually wired
to VaultHealthWorkflow. See that service's module docstring.

build_career_insight calls prana-ai's POST /pipeline/career-insight (added
2026-08-07, see prana-ai/insights/career_narrative_service.py) via
AiPipelineClient.career_insight — same proxy pattern as build_market_comp's
BenchmarkingService call, just over HTTP since this one needs the LLM.

build_skill_gap_analysis calls prana-ai's POST /pipeline/skill-gap (added
2026-08-07, see prana-ai/insights/skill_gap_service.py) via
AiPipelineClient.skill_gap — same proxy pattern as build_career_insight.
Deliberately modest MVP scope (see skill_gap_service.py's docstring): no
skills taxonomy exists in the schema, so this is general LLM synthesis from
designation/grade progression, not a taxonomy/market comparison. UI copy
must call it "career growth suggestions," never "skill gap analysis."
"""
import datetime
import uuid
from typing import Optional


class AnalyticsService:

    def __init__(self, db, kafka=None) -> None:
        self._db = db
        self._kafka = kafka

    # ── CareerInsightWorkflow ─────────────────────────────────────────────────

    async def build_career_insight(self, *, employee_uuid: str, tenant_id: Optional[str] = None) -> dict:
        from services.ai_client import AiPipelineClient

        return await AiPipelineClient().career_insight(employee_uuid=employee_uuid, tenant_id=tenant_id)

    async def write_career_insight(self, *, employee_uuid: str, tenant_id: Optional[str], insights: dict) -> None:
        await self._upsert_insight(employee_uuid, tenant_id, "CAREER", insights)

    # score_vault_completeness / write_vault_completeness removed 2026-08-06 —
    # consolidated into EmployeeLifecycleService.recompute_vault_completeness,
    # the one actually triggered (by VaultHealthWorkflow). See that service's
    # module docstring for the 3-writer-race history this closes.

    # ── AnomalyAcknowledgementWorkflow ────────────────────────────────────────

    async def record_anomaly_ack(self, *, anomaly_id: str, acked: bool,
                                  note: str, acknowledged_by: Optional[str]) -> None:
        await self._db.execute(
            """
            UPDATE anomaly_event
            SET status = $1, acknowledged_by = $2, acknowledged_at = NOW()
            WHERE anomaly_id = $3
            """,
            "RESOLVED" if acked else "OPEN", acknowledged_by, anomaly_id,
        )

    # ── DigestWorkflow ────────────────────────────────────────────────────────

    async def build_digest(self, *, tenant_id: str, digest_type: str) -> dict:
        from services.digest_service import DigestService, period_window

        svc = DigestService()
        from_dt, to_dt = period_window("weekly" if digest_type != "monthly" else "monthly")
        data: dict = {}
        for role in ("chro", "cfo", "ciso"):
            config = await svc.get_config(self._db, tenant_id, role)
            schedule = config.get("schedules", {}).get(digest_type, {})
            if not config.get("active") or not schedule.get("enabled"):
                continue
            builder = getattr(svc, f"build_{role}_digest")
            data[role] = {"recipients": config.get("recipients", []),
                          "content": await builder(self._db, tenant_id, from_dt, to_dt)}
        return {"digest_type": digest_type, "tenant_id": tenant_id, "data": data}

    async def send_digest_email(self, *, tenant_id: str, digest_type: str, data: dict) -> None:
        if not self._kafka:
            return
        for role, payload in data.items():
            for recipient_id in payload.get("recipients", []):
                # EmailConsumer requires recipient_email or it silently skips —
                # recipient_id here is an oa_user_id, not an email address.
                email = await self._db.fetchval(
                    "SELECT email FROM oa_user WHERE oa_user_id=$1", recipient_id,
                )
                notif = {
                    "event_type": f"DIGEST_{digest_type.upper()}",
                    "recipient_id": recipient_id,
                    "recipient_type": "OA_USER",
                    "template_id": f"DIGEST_{digest_type.upper()}",
                    "tenant_id": tenant_id,
                    "template_data": payload.get("content", {}),
                }
                if email:
                    notif["recipient_email"] = email
                await self._kafka.communication_requested(notif)

    # ── PeerBenchmarkWorkflow ─────────────────────────────────────────────────

    async def build_peer_benchmark(self, *, tenant_id: str, grade: str, department: str) -> dict:
        from services.benchmarking_service import BenchmarkingService

        svc = BenchmarkingService(self._db)
        median = await svc.get_market_median(grade=grade, department=department)
        return {"band_label": f"{grade}:{department}", "cache_value": median}

    async def write_peer_benchmark(self, *, tenant_id: str, band_label: str, cache_value: dict) -> None:
        # insight_cache's unique index includes a nullable period_month, which
        # Postgres/YugabyteDB treats as distinct-per-NULL by default — an
        # ON CONFLICT on that index would never match an existing NULL-period
        # row, so this does an explicit update-then-insert instead.
        cache_key = f"peer_benchmark:{band_label}"
        updated = await self._db.execute(
            """
            UPDATE insight_cache SET cache_value=$3, computed_at=NOW()
            WHERE tenant_id=$1 AND cache_key=$2 AND period_month IS NULL
            """,
            tenant_id, cache_key, cache_value,
        )
        if updated == "UPDATE 0":
            await self._db.execute(
                """
                INSERT INTO insight_cache (tenant_id, cache_key, band_label, cache_value, computed_at)
                VALUES ($1, $2, $3, $4, NOW())
                """,
                tenant_id, cache_key, band_label, cache_value,
            )

    # ── SkillGapWorkflow ──────────────────────────────────────────────────────

    async def build_skill_gap_analysis(self, *, employee_uuid: str, tenant_id: Optional[str] = None) -> dict:
        from services.ai_client import AiPipelineClient

        return await AiPipelineClient().skill_gap(employee_uuid=employee_uuid, tenant_id=tenant_id)

    async def write_skill_gap(self, *, employee_uuid: str, tenant_id: Optional[str], insights: dict) -> None:
        await self._upsert_insight(employee_uuid, tenant_id, "SKILL_GAP", insights)

    # ── MarketCompWorkflow ────────────────────────────────────────────────────

    async def build_market_comp(self, *, employee_uuid: str) -> dict:
        """Unlike build_career_insight/build_skill_gap_analysis, this workflow's
        own docstring rules out an external/LLM call ("embedded market comp
        dataset") — so this reuses the same cross-tenant salary_band lookup as
        build_peer_benchmark, just framed as "vs market" for one employee."""
        from services.benchmarking_service import BenchmarkingService

        row = await self._db.fetchrow(
            "SELECT grade, department FROM employee_master WHERE employee_uuid=$1",
            employee_uuid,
        )
        if not row:
            return {"insights": {}}
        svc = BenchmarkingService(self._db)
        median = await svc.get_market_median(grade=row["grade"], department=row["department"])
        return {"insights": {"market_comp": median}}

    async def write_market_comp(self, *, employee_uuid: str, tenant_id: Optional[str], insights: dict) -> None:
        await self._upsert_insight(employee_uuid, tenant_id, "MARKET_COMP", insights)

    # ── shared ────────────────────────────────────────────────────────────────

    async def _upsert_insight(self, employee_uuid: str, tenant_id: Optional[str],
                               insight_type: str, insights: dict) -> None:
        import json

        await self._db.execute(
            """
            INSERT INTO employee_insight (insight_id, employee_uuid, tenant_id, insight_type, insights, computed_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (employee_uuid, insight_type) DO UPDATE SET
              insights = EXCLUDED.insights, computed_at = NOW()
            """,
            uuid.uuid4(), employee_uuid, tenant_id, insight_type, json.dumps(insights),
        )
