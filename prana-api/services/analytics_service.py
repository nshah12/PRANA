"""
AnalyticsService — business logic behind workflows/intelligence.py's 14
activities (CareerInsightWorkflow, VaultCompletenessWorkflow,
AnomalyAcknowledgementWorkflow, DigestWorkflow, PeerBenchmarkWorkflow,
SkillGapWorkflow, MarketCompWorkflow). Zero Temporal imports.

KNOWN GAP: build_career_insight, build_skill_gap_analysis, and build_market_comp
need an LLM-derived narrative from prana-ai, but prana-ai's only exposed HTTP
surface (prana-ai/routers/pipeline.py, mounted under /pipeline) has no endpoint
for any of the three — only scan/extract/write_unclassified/resolve/route/
raise_exception/refresh_insight. Building one is a prana-ai change (a separate
deployable service), not something this file can do on its own. Each of the
three raises NotImplementedError with that context rather than silently
returning empty data or guessing at an endpoint that doesn't exist.
"""
import datetime
import uuid
from typing import Optional

_REQUIRED_DOC_CATEGORIES: dict[str, tuple[str, ...]] = {
    "employment_proof": ("OFFER_LETTER", "APPOINTMENT_LETTER", "JOINING_LETTER"),
    "salary_slip":       ("SALARY_SLIP",),
    "form16":            ("FORM_16",),
}


class AnalyticsService:

    def __init__(self, db, kafka=None) -> None:
        self._db = db
        self._kafka = kafka

    # ── CareerInsightWorkflow ─────────────────────────────────────────────────

    async def build_career_insight(self, *, employee_uuid: str) -> dict:
        raise NotImplementedError(
            "build_career_insight needs prana-ai to expose a career-narrative "
            "endpoint (e.g. POST /pipeline/career-insight) — no such endpoint "
            "exists yet in prana-ai/routers/pipeline.py."
        )

    async def write_career_insight(self, *, employee_uuid: str, tenant_id: Optional[str], insights: dict) -> None:
        await self._upsert_insight(employee_uuid, tenant_id, "CAREER", insights)

    # ── VaultCompletenessWorkflow ─────────────────────────────────────────────

    async def score_vault_completeness(self, *, employee_uuid: str) -> dict:
        """Percentage of 3 core document categories present for this employee:
        employment proof, a salary slip, and a Form 16 — matching the same 3
        component names vault_health_score already tracks."""
        rows = await self._db.fetch(
            "SELECT DISTINCT doc_type FROM document WHERE employee_uuid=$1 AND is_deleted=FALSE",
            employee_uuid,
        )
        present_types = {r["doc_type"] for r in rows}
        categories_met = sum(
            1 for doc_types in _REQUIRED_DOC_CATEGORIES.values()
            if present_types & set(doc_types)
        )
        pct = round(categories_met / len(_REQUIRED_DOC_CATEGORIES) * 100)
        return {"vault_completeness": pct}

    async def write_vault_completeness(self, *, employee_uuid: str, vault_completeness: int) -> None:
        await self._db.execute(
            "UPDATE employee_master SET vault_completeness=$1, updated_at=NOW() WHERE employee_uuid=$2",
            vault_completeness, employee_uuid,
        )

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
                await self._kafka.notify_email({
                    "event_type": f"DIGEST_{digest_type.upper()}",
                    "recipient_id": recipient_id,
                    "template_id": f"DIGEST_{digest_type.upper()}",
                    "tenant_id": tenant_id,
                    "payload": payload.get("content", {}),
                })

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

    async def build_skill_gap_analysis(self, *, employee_uuid: str) -> dict:
        raise NotImplementedError(
            "build_skill_gap_analysis needs prana-ai to expose a skill-gap "
            "endpoint — no such endpoint exists yet in prana-ai/routers/pipeline.py."
        )

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
        await self._db.execute(
            """
            INSERT INTO employee_insight (insight_id, employee_uuid, tenant_id, insight_type, insights, computed_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (employee_uuid, insight_type) DO UPDATE SET
              insights = EXCLUDED.insights, computed_at = NOW()
            """,
            uuid.uuid4(), employee_uuid, tenant_id, insight_type, insights,
        )
