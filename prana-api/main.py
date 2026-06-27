import asyncio
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from middleware.deprecation import DeprecationMiddleware
from db import create_pool
from services.jwt_service import JWTService
from services.encryption_service import KMSService
from services.s3_service import S3Service
from kafka.producer import KafkaPub, set_kafka_producer
from kafka.consumers.audit_consumer import AuditConsumer
from kafka.consumers.workflow_consumer import WorkflowConsumer
from kafka.consumers.sse_fanout_consumer import SSEFanoutConsumer
from kafka.consumers.notif_consumer import NotifConsumer
from kafka.consumers.analytics_consumer import AnalyticsConsumer
from kafka.consumers.cache_invalidation_consumer import CacheInvalidationConsumer
from kafka.consumers.compliance_consumer import ComplianceConsumer
from kafka.consumers.oa_user_consumer import OAUserConsumer
from kafka.consumers.employee_consumer import EmployeeConsumer
from kafka.consumers.tenant_consumer import TenantConsumer
from kafka.consumers.auth_consumer import AuthConsumer
from kafka.consumers.statutory_consumer import StatutoryConsumer
from kafka.consumers.security_consumer import SecurityConsumer
from kafka.consumers.email_consumer import EmailConsumer
from kafka.consumers.sms_consumer import SMSConsumer
from kafka.consumers.push_consumer import PushConsumer
from kafka.consumers.whatsapp_consumer import WhatsAppConsumer
from kafka.consumers.bell_consumer import BellConsumer
from kafka.consumers.integration_consumer import IntegrationConsumer
from kafka.consumers.platform_consumer import PlatformConsumer
from services.cache_service import CacheService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # DB pool
    app.state.db_pool = await create_pool(
        dsn=settings.db_dsn,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
    )

    # Redis
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=False)

    # Cache service (Redis wrapper — available to all routers via request.app.state)
    app.state.cache = CacheService(app.state.redis)

    # Services
    app.state.jwt_service = JWTService(settings, app.state.redis)
    app.state.kms_service = KMSService(
        region=settings.aws_region,
        access_key_id=settings.aws_access_key_id,
        secret_access_key=settings.aws_secret_access_key,
    )
    app.state.settings = settings

    # S3 / MinIO
    s3_svc = S3Service(settings)
    try:
        s3_svc.ensure_bucket(settings.s3_bucket_documents)
        s3_svc.ensure_bucket(settings.s3_bucket_staging)
    except Exception:
        pass   # No S3 in dev without MinIO — non-fatal
    app.state.s3 = s3_svc

    # Temporal client
    try:
        from temporalio.client import Client as TemporalClient
        app.state.temporal_client = await TemporalClient.connect(settings.temporal_host)
    except Exception:
        app.state.temporal_client = None   # dev: Temporal not running

    # Kafka producer
    kafka = KafkaPub(settings)
    try:
        await kafka.start()
        app.state.kafka_producer = kafka
        set_kafka_producer(kafka)
    except Exception:
        app.state.kafka_producer = None   # dev: Kafka not running

    # Signal WORKER_STARTED — PlatformConsumer routes to ops alerting
    if app.state.kafka_producer:
        try:
            await app.state.kafka_producer.platform_event({
                "event_type": "WORKER_STARTED",
                "service":    "prana-api",
                "version":    settings.app_version if hasattr(settings, "app_version") else "unknown",
            })
        except Exception:
            pass  # Non-fatal — don't block startup

    # Kafka consumers — each runs as a background asyncio task
    _consumer_tasks: list[asyncio.Task] = []
    if app.state.kafka_producer:
        import os
        pod_id = os.environ.get("POD_NAME", "local")
        consumers = [
            # Original consumers
            AuditConsumer(settings, app.state.db_pool),
            WorkflowConsumer(settings, app.state.temporal_client, app.state.db_pool),
            SSEFanoutConsumer(settings, app.state.redis),
            NotifConsumer(settings, app.state.db_pool),
            AnalyticsConsumer(settings, app.state.temporal_client, app.state.redis),
            CacheInvalidationConsumer(settings, app.state.redis, pod_id=pod_id),
            # Domain event consumers
            ComplianceConsumer(settings, temporal_client=app.state.temporal_client),
            OAUserConsumer(settings, db_pool=app.state.db_pool, temporal_client=app.state.temporal_client),
            EmployeeConsumer(settings, db_pool=app.state.db_pool, temporal_client=app.state.temporal_client, kafka_producer=kafka),
            TenantConsumer(settings, db_pool=app.state.db_pool, temporal_client=app.state.temporal_client),
            AuthConsumer(settings, db_pool=app.state.db_pool, temporal_client=app.state.temporal_client),
            StatutoryConsumer(settings, db_pool=app.state.db_pool, temporal_client=app.state.temporal_client),
            SecurityConsumer(settings, db_pool=app.state.db_pool, temporal_client=app.state.temporal_client, redis=app.state.redis),
            # Notification channel consumers
            EmailConsumer(settings, app.state.db_pool),
            SMSConsumer(settings, app.state.db_pool),
            PushConsumer(settings, app.state.db_pool),
            WhatsAppConsumer(settings, app.state.db_pool),
            BellConsumer(settings, app.state.db_pool, app.state.redis),
            # Integration & platform consumers
            IntegrationConsumer(settings, app.state.db_pool, kafka),
            PlatformConsumer(settings),
        ]
        for c in consumers:
            _consumer_tasks.append(asyncio.create_task(c.run()))

    yield

    for t in _consumer_tasks:
        t.cancel()
    if app.state.kafka_producer:
        try:
            await app.state.kafka_producer.platform_event({
                "event_type": "WORKER_STOPPED",
                "service":    "prana-api",
            })
        except Exception:
            pass
        await app.state.kafka_producer.stop()
    await app.state.db_pool.close()
    await app.state.redis.aclose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="PRANA API",
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    # Adds Deprecation/Sunset headers to deprecated versions/endpoints automatically
    # Blocks sunset versions with 410 Gone — no router changes needed
    app.add_middleware(DeprecationMiddleware)

    # ── Global exception handlers ──────────────────────────────────────────────

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Never leak stack traces to clients
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "INTERNAL_ERROR"},
        )

    # ── Health ─────────────────────────────────────────────────────────────────

    @app.get("/health", include_in_schema=False)
    async def health():
        return {"status": "ok"}

    # ── Routers ────────────────────────────────────────────────────────────────
    from routers import (
        auth_employee, auth_oa, auth_pa, totp_setup,
        tenants, employees, oa_users, ingest, elevations, exceptions,
        vault, share_access, compliance, dpdp, labour_law,
        chro, cfo, ciso, pa_admin, org_settings, sessions,
        ask, public, doc_manifest, internal_pipeline, alumni, benchmarking,
        gamification,
        hrms_definitions,
        hrms_config,
    )
    # ── Unversioned — internal/auth (no external HRMS callers) ───────────────────
    app.include_router(auth_employee.router, prefix="/auth/employee",        tags=["auth"])
    app.include_router(auth_oa.router,       prefix="/auth/org",             tags=["auth"])
    app.include_router(auth_pa.router,       prefix="/auth/admin",           tags=["auth"])
    app.include_router(sessions.router,      prefix="/auth/sessions",        tags=["auth"])
    app.include_router(totp_setup.router,    prefix="/totp/setup",           tags=["totp"])
    app.include_router(tenants.router,       prefix="/admin/tenants",        tags=["admin"])
    app.include_router(pa_admin.router,      prefix="/admin",                tags=["admin"])
    app.include_router(public.router,        tags=["public"])

    # ── v1 — HRMS-facing and mobile-facing (versioned, stable contract) ────────
    # Rule: NEVER modify existing v1 behaviour — breaking changes go to v2 router
    # Rule: Adding optional fields to v1 responses is safe (non-breaking)
    # Rule: Removing/renaming fields requires v2 + 90-day deprecation notice
    app.include_router(ingest.router,        prefix="/v1/ingest",            tags=["v1:ingest"])
    app.include_router(vault.router,         prefix="/v1/vault",             tags=["v1:vault"])
    app.include_router(share_access.router,  prefix="/v1/s",                 tags=["v1:share"])
    app.include_router(employees.router,     prefix="/v1/org/employees",     tags=["v1:employees"])
    app.include_router(oa_users.router,      prefix="/v1/org",               tags=["v1:org"])
    app.include_router(org_settings.router,  prefix="/v1/org",               tags=["v1:org"])
    app.include_router(elevations.router,    prefix="/v1/org",               tags=["v1:elevations"])
    app.include_router(exceptions.router,   prefix="/v1/org",               tags=["v1:exceptions"])
    app.include_router(compliance.router,    prefix="/v1/vault/compliance",  tags=["v1:compliance"])
    app.include_router(dpdp.router,          prefix="/v1/dpdp",              tags=["v1:dpdp"])
    app.include_router(labour_law.router,    prefix="/v1/compliance/statutory", tags=["v1:labour-law"])
    app.include_router(chro.router,          prefix="/v1/chro",              tags=["v1:chro"])
    app.include_router(cfo.router,           prefix="/v1/cfo",               tags=["v1:cfo"])
    app.include_router(ciso.router,          prefix="/v1/ciso",              tags=["v1:ciso"])
    app.include_router(ask.router,           prefix="/v1/ask",               tags=["v1:ask"])
    app.include_router(alumni.router,        prefix="/v1/alumni",            tags=["v1:alumni"])
    app.include_router(benchmarking.router,  prefix="/v1/benchmarking",      tags=["v1:benchmarking"])
    app.include_router(gamification.router,      prefix="/v1/gamification",           tags=["v1:gamification"])
    app.include_router(hrms_definitions.router,  prefix="/v1/admin/hrms/definitions", tags=["v1:hrms-admin"])
    app.include_router(hrms_config.router,       prefix="/v1/hrms/config",            tags=["v1:hrms-config"])
    app.include_router(doc_manifest.router,                                  tags=["v1:manifests"])

    # ── Internal — prana-ai VPC callbacks only (NOT in Kong routes) ──────────────
    app.include_router(internal_pipeline.router, prefix="/internal/pipeline", tags=["internal"])

    # ── v2 — mount here when ready (import v2 routers from routers/v2/) ────────
    # from routers.v2 import ingest as ingest_v2
    # app.include_router(ingest_v2.router, prefix="/v2/ingest", tags=["v2:ingest"])

    return app


app = create_app()
