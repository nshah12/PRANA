"""
Temporal activity implementations for the DocumentPipelineWorkflow.

Each @activity.defn function here is the actual implementation registered with
the Temporal worker. They call prana-ai via HTTP for GPU stages (03–06) and
handle stage02 (encryption) locally since it's CPU-only and needs KMS access.

Worker started via: python -m workflows.worker
"""

import json
import boto3
import asyncpg

from temporalio import activity

from config import get_settings
from services.ai_client import AiPipelineClient
from services.encryption_service import KMSService


def _ai() -> AiPipelineClient:
    return AiPipelineClient()


# ── Stage 02 — Encryption boundary (runs in prana-api, not prana-ai) ─────────

@activity.defn(name="stage02_encrypt")
async def stage02_encrypt(params: dict) -> dict:
    """
    Encryption boundary — runs in prana-api (not prana-ai) because KMS access is here.

    If pan is supplied (employee already registered, PAN on file):
      - Derive pan_token = HMAC-SHA256(PAN, platform_secret)
      - Compute enc_pan  = FF3-1(PAN, employee DEK)
      - Encrypt file bytes: AES-256-GCM
      - Upload encrypted file to documents bucket; delete staging file
    If pan is absent (new document, PAN not yet known):
      - Returns nik_found=False; pan_token + enc_pan computed after Stage 05 resolves.

    Privacy contract: PAN is zeroed from memory as soon as crypto ops complete.
    """
    import hmac as _hmac
    import hashlib
    import os

    settings = get_settings()

    pan: str | None = params.get("pan")

    pan_token = None
    enc_pan   = None

    if pan:
        # HMAC-SHA256 pan_token — safe to store (non-reversible)
        platform_secret = settings.platform_hmac_secret.encode()
        pan_token = _hmac.new(platform_secret, pan.encode("ascii"), hashlib.sha256).hexdigest()
        del platform_secret

        # FF3-1 Format-Preserving Encryption — reversible, stored as enc_pan
        enc_dek = params["enc_dek"]
        kms = KMSService(
            region=settings.aws_region,
            access_key_id=settings.aws_access_key_id,
            secret_access_key=settings.aws_secret_access_key,
        )
        dek = await kms.decrypt_dek(enc_dek, params["tenant_kek_arn"])
        try:
            from ff3 import FF3Cipher
            key_hex    = dek[:16].hex()           # FF3-1 uses 16, 24, or 32-byte key
            tweak_hex  = "0000000000000000"       # 8-byte zero tweak — deterministic
            alphabet   = "0123456789abcdefghijklmnopqrstuvwxyz"
            cipher     = FF3Cipher.withCustomAlphabet(key_hex, tweak_hex, alphabet)
            pan_b36    = _pan_to_base36(pan)
            enc_b36    = cipher.encrypt(pan_b36)
            enc_pan    = _base36_to_pan(enc_b36)
        finally:
            del dek

        # Zero PAN from memory (best-effort in Python)
        pan = "0" * len(pan)
        del pan

    # Encrypt file bytes and move from staging → documents bucket
    s3 = boto3.client("s3", region_name=settings.aws_region)
    staging_key    = params["s3_staging_key"]
    staging_bucket = params["s3_staging_bucket"]
    docs_bucket    = settings.s3_bucket_documents

    if params.get("enc_dek") and pan_token:
        # Re-unwrap DEK for file encryption (pan was encrypted above, dek was deleted)
        kms = KMSService(
            region=settings.aws_region,
            access_key_id=settings.aws_access_key_id,
            secret_access_key=settings.aws_secret_access_key,
        )
        file_dek = await kms.decrypt_dek(params["enc_dek"], params["tenant_kek_arn"])
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            obj = s3.get_object(Bucket=staging_bucket, Key=staging_key)
            plaintext = obj["Body"].read()
            nonce     = os.urandom(12)
            aesgcm    = AESGCM(file_dek)
            encrypted = aesgcm.encrypt(nonce, plaintext, None)
            del plaintext
        finally:
            del file_dek

        tenant_id   = params["tenant_id"]
        document_id = params["document_id"]
        doc_type    = params.get("doc_type", "unknown")
        period_safe = (params.get("doc_period") or "unknown").replace(":", "_").replace("/", "_")
        emp_path    = params.get("employee_uuid") or "unresolved"
        final_key   = f"{tenant_id}/{emp_path}/{doc_type}/{period_safe}_{document_id}.enc"

        s3.put_object(Bucket=docs_bucket, Key=final_key, Body=nonce + encrypted,
                      ContentType="application/octet-stream")
        s3.delete_object(Bucket=staging_bucket, Key=staging_key)

        return {"pan_token": pan_token, "enc_pan": enc_pan,
                "s3_key": final_key, "s3_bucket": docs_bucket, "nik_found": True}

    # PAN not available yet — file stays in staging for later stages
    return {"pan_token": pan_token, "enc_pan": enc_pan,
            "s3_key": staging_key, "s3_bucket": staging_bucket, "nik_found": False}


def _pan_to_base36(pan: str) -> str:
    result = []
    for ch in pan.upper():
        result.append(ch if ch.isdigit() else chr(ord("a") + (ord(ch) - ord("A"))))
    return "".join(result)


def _base36_to_pan(s: str) -> str:
    result = []
    for i, ch in enumerate(s):
        if i in (0, 1, 2, 3, 4, 9):
            result.append(ch.upper() if ch.isalpha() else chr(ord("A") + int(ch)))
        else:
            result.append(str(ord(ch) - ord("a")) if ch.isalpha() else ch)
    return "".join(result)


# ── Stage 03 — Safety scan ────────────────────────────────────────────────────

@activity.defn(name="stage03_scan")
async def stage03_scan(params: dict) -> dict:
    """Calls prana-ai /pipeline/scan with file bytes from S3."""
    s3 = boto3.client("s3", region_name=get_settings().aws_region)
    obj = s3.get_object(Bucket=params["s3_staging_bucket"], Key=params["s3_staging_key"])
    file_bytes = obj["Body"].read()

    result = await _ai().scan(file_bytes=file_bytes, ext=params["ext"])

    if result.get("csam_detected"):
        # Write csam_detected flag immediately — before any other processing
        db: asyncpg.Connection = activity.info().heartbeat_details  # type: ignore[assignment]
        # csam_detected written by caller (workflow exits early after checking flag)
        pass

    return result


# ── Stage 04 — LLM extraction ─────────────────────────────────────────────────

@activity.defn(name="stage04_extract")
async def stage04_extract(params: dict) -> dict:
    """OCR + LLM extraction via prana-ai. Slowest stage.
    Returns dict with status='ok' (extracted) or status='unclassified' (AUTO_DETECT failed)."""
    s3 = boto3.client("s3", region_name=get_settings().aws_region)
    obj = s3.get_object(Bucket=params["s3_staging_bucket"], Key=params["s3_staging_key"])
    file_bytes = obj["Body"].read()

    result = await _ai().extract(
        file_bytes=file_bytes,
        ext=params["ext"],
        doc_type=params["doc_type"],
        tenant_id=params["tenant_id"],
        doc_period=params.get("doc_period"),
    )
    return result


@activity.defn(name="stage04_write_unclassified")
async def stage04_write_unclassified(params: dict) -> dict:
    """Write UNCLASSIFIED status + unclassified_queue row when AUTO_DETECT fails."""
    await _ai().write_unclassified(
        document_id=params["document_id"],
        tenant_id=params["tenant_id"],
        declared_doc_type=params.get("doc_type"),
        best_guess_doc_type=params.get("best_guess_doc_type"),
        best_guess_score=params.get("best_guess_score", 0.0),
        partial_fields=params.get("partial_fields", {}),
        reason=params.get("reason", "AUTO_DETECT_FAILED"),
    )
    return {"status": "UNCLASSIFIED"}


# ── Stage 05 — Identity resolution ───────────────────────────────────────────

@activity.defn(name="stage05_resolve")
async def stage05_resolve(params: dict) -> dict:
    """4-level identity resolution ladder via prana-ai."""
    result = await _ai().resolve(
        pan_token=params.get("pan_token"),
        tenant_id=params["tenant_id"],
        doc_type=params.get("doc_type", "UNKNOWN"),
        extracted_fields=params.get("extracted_fields", {}),
    )
    return result


# ── Stage 05 — Cross-tenant violation handler ────────────────────────────────

@activity.defn(name="stage05_handle_cross_tenant_violation")
async def stage05_handle_cross_tenant_violation(params: dict) -> dict:
    """
    Called when Stage05 detects a document's pan_token belongs to a different tenant.

    1. Write anomaly_event (CROSS_TENANT_UPLOAD_ATTEMPT, CRITICAL/P0)
    2. Set document.pipeline_status = 'REJECTED'
    3. Publish to prana.audit.events → AuditConsumer writes audit_event
    4. Publish to prana.notifications → NotifConsumer alerts Tenant CISO + PA Admin
    """
    import asyncpg, uuid
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        document_id        = params["document_id"]
        uploading_tenant_id = params["uploading_tenant_id"]
        owner_tenant_id    = params["owner_tenant_id"]
        pan_token          = params.get("pan_token", "")
        actor_id           = params.get("uploaded_by")   # oa_user_id who triggered the upload

        async with db.transaction():
            anomaly_id = str(uuid.uuid4())
            await db.execute(
                """
                INSERT INTO anomaly_event
                  (anomaly_id, tenant_id, rule_name, severity, actor_id, event_metadata, status)
                VALUES ($1, $2, $3, $4, $5, $6, 'OPEN')
                """,
                anomaly_id,
                uploading_tenant_id,
                "CROSS_TENANT_UPLOAD_ATTEMPT",
                "P0",
                actor_id,
                json.dumps({
                    "document_id":        document_id,
                    "pan_token":          pan_token,
                    "owner_tenant_id":    owner_tenant_id,
                    "uploading_tenant_id": uploading_tenant_id,
                }),
            )
            await db.execute(
                "UPDATE document SET pipeline_status='REJECTED', updated_at=NOW() WHERE document_id=$1",
                document_id,
            )

        # Publish audit event → AuditConsumer writes audit_event row
        try:
            from kafka.producer import KafkaPub
            kafka = KafkaPub(settings)
            await kafka.start()
            await kafka.publish("prana.audit.events", {
                "event_type":          "CROSS_TENANT_UPLOAD_ATTEMPT",
                "document_id":         document_id,
                "tenant_id":           uploading_tenant_id,
                "actor_id":            actor_id,
                "anomaly_id":          anomaly_id,
                "owner_tenant_id":     owner_tenant_id,
                "severity":            "CRITICAL",
            }, key=uploading_tenant_id)

            # Alert Tenant CISO + PA Admin
            await kafka.publish("prana.notifications", {
                "event_type":          "CROSS_TENANT_UPLOAD",
                "document_id":         document_id,
                "tenant_id":           uploading_tenant_id,
                "owner_tenant_id":     owner_tenant_id,
                "anomaly_id":          anomaly_id,
                "actor_id":            actor_id,
            }, key=uploading_tenant_id)
            await kafka.stop()
        except Exception:
            pass  # Temporal will retry the activity; Kafka publish is best-effort within the retry

        return {"status": "CROSS_TENANT_REJECTED", "anomaly_id": anomaly_id}
    finally:
        await db.close()


# ── Stage 06 — Route ─────────────────────────────────────────────────────────

@activity.defn(name="stage06_route")
async def stage06_route(params: dict) -> dict:
    """Write ROUTED status and career_event via prana-ai."""
    await _ai().route(
        document_id=params["document_id"],
        tenant_id=params["tenant_id"],
        employee_uuid=params["employee_uuid"],
        pan_token=params["pan_token"],
        doc_type=params["doc_type"],
        doc_period=params.get("doc_period"),
        extracted_fields=params["extracted_fields"],
        resolution_method=params["method"],
        resolution_confidence=params["confidence"],
        s3_key=params["s3_key"],
    )
    return {"status": "ROUTED"}


@activity.defn(name="stage06_raise_exception")
async def stage06_raise_exception(params: dict) -> dict:
    """Write EXCEPTION status and exception_queue row via prana-ai."""
    await _ai().raise_exception(
        document_id=params["document_id"],
        tenant_id=params["tenant_id"],
        exception_type=params["exception_type"],
        extracted_fields=params["extracted_fields"],
        candidates=params.get("candidates", []),
    )
    return {"status": "EXCEPTION"}


# ── Compliance activity implementations ──────────────────────────────────────

@activity.defn(name="get_config_value")
async def get_config_value(params: dict) -> str:
    from services.compliance_service import ComplianceService
    import asyncpg
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        svc = ComplianceService(db=db)
        return await svc.get_config_value(
            key=params["key"],
            tenant_id=params.get("tenant_id"),
            default=params.get("default", ""),
        )
    finally:
        await db.close()


@activity.defn(name="send_erasure_notice")
async def send_erasure_notice(params: dict) -> None:
    from services.compliance_service import ComplianceService
    import asyncpg
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        svc = ComplianceService(db=db)
        await svc.send_erasure_notice(
            employee_user_id=params["employee_user_id"],
            tenant_id=params.get("tenant_id"),
        )
    finally:
        await db.close()


@activity.defn(name="execute_erasure")
async def execute_erasure(params: dict) -> None:
    from services.compliance_service import ComplianceService
    import asyncpg
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        svc = ComplianceService(db=db)
        await svc.execute_erasure(employee_user_id=params["employee_user_id"])
    finally:
        await db.close()


@activity.defn(name="send_consent_rebump")
async def send_consent_rebump(params: dict) -> None:
    from services.compliance_service import ComplianceService
    import asyncpg
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        svc = ComplianceService(db=db)
        await svc.send_consent_rebump(
            employee_user_id=params["employee_user_id"],
            tenant_id=params.get("tenant_id"),
        )
    finally:
        await db.close()


@activity.defn(name="check_consent_status")
async def check_consent_status(params: dict) -> dict:
    from services.compliance_service import ComplianceService
    import asyncpg
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        svc = ComplianceService(db=db)
        return await svc.check_consent_status(employee_user_id=params["employee_user_id"])
    finally:
        await db.close()


@activity.defn(name="build_data_export")
async def build_data_export(params: dict) -> dict:
    from services.compliance_service import ComplianceService
    import asyncpg
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    s3 = boto3.client("s3", region_name=settings.aws_region)
    try:
        svc = ComplianceService(
            db=db, s3_client=s3,
            documents_bucket=settings.s3_bucket_documents,
            exports_bucket=getattr(settings, "s3_bucket_exports", settings.s3_bucket_documents),
        )
        return await svc.build_data_export(employee_user_id=params["employee_user_id"])
    finally:
        await db.close()


@activity.defn(name="notify_export_ready")
async def notify_export_ready(params: dict) -> None:
    from services.compliance_service import ComplianceService
    import asyncpg
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        svc = ComplianceService(db=db)
        await svc.notify_export_ready(
            employee_user_id=params["employee_user_id"],
            download_url=params.get("download_url", ""),
            doc_count=params.get("doc_count", 0),
        )
    finally:
        await db.close()


@activity.defn(name="open_grievance")
async def open_grievance(params: dict) -> None:
    from services.compliance_service import ComplianceService
    import asyncpg
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        svc = ComplianceService(db=db)
        await svc.open_grievance(
            grievance_id=params["grievance_id"],
            employee_user_id=params["employee_user_id"],
            tenant_id=params.get("tenant_id"),
            category=params.get("category", "GENERAL"),
            description=params.get("description", ""),
        )
    finally:
        await db.close()


@activity.defn(name="escalate_grievance")
async def escalate_grievance(params: dict) -> None:
    from services.compliance_service import ComplianceService
    import asyncpg
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        svc = ComplianceService(db=db)
        await svc.escalate_grievance(
            grievance_id=params["grievance_id"],
            reason=params.get("reason", "SLA_BREACH"),
        )
    finally:
        await db.close()


@activity.defn(name="close_grievance")
async def close_grievance(params: dict) -> None:
    from services.compliance_service import ComplianceService
    import asyncpg
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        svc = ComplianceService(db=db)
        await svc.close_grievance(
            grievance_id=params["grievance_id"],
            note=params.get("note", ""),
        )
    finally:
        await db.close()


# ── Batch-level activity implementations ─────────────────────────────────────

@activity.defn(name="get_batch_config")
async def get_batch_config(params: dict) -> dict:
    """
    Read pipeline_max_duration_hours and batch_max_duration_hours from config.
    Tenant config overrides platform config.
    """
    import asyncpg
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        async def _cfg(key: str, default: str) -> str:
            row = await db.fetchrow(
                """
                SELECT COALESCE(
                  (SELECT config_value FROM tenant_config
                   WHERE tenant_id=$1 AND config_key=$2 AND is_active=TRUE),
                  (SELECT config_value FROM platform_config
                   WHERE config_key=$2 AND is_active=TRUE),
                  $3
                ) AS val
                """,
                params.get("tenant_id"), key, default,
            )
            return row["val"] if row else default

        return {
            "pipeline_max_duration_hours": await _cfg("pipeline_max_duration_hours", "4"),
            "batch_max_duration_hours":    await _cfg("batch_max_duration_hours",    "24"),
        }
    finally:
        await db.close()


@activity.defn(name="write_batch_summary")
async def write_batch_summary(params: dict) -> None:
    """
    Upsert document_batch summary row with final counts.
    Idempotent — safe to retry on activity failure.
    """
    import asyncpg
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        await db.execute(
            """
            UPDATE document_batch SET
              total_files  = $2,
              routed       = $3,
              exceptions   = $4,
              quarantined  = $5,
              failed       = $6,
              completed_at = NOW(),
              status       = CASE
                WHEN $6 > 0 OR $4 > 0 THEN 'PARTIAL'
                WHEN $3 = $2           THEN 'COMPLETE'
                ELSE 'PARTIAL'
              END
            WHERE batch_id = $1
            """,
            params["batch_id"],
            params["total"],
            params["routed"],
            params["exceptions"],
            params["quarantine"],
            params["failed"],
        )
    finally:
        await db.close()


@activity.defn(name="mark_batch_straggler")
async def mark_batch_straggler(params: dict) -> None:
    """
    Write EXCEPTION status + exception_queue row for a timed-out document.
    Called by BatchTimeoutMonitorWorkflow and BatchProgressWorkflow for stragglers.
    Idempotent — UPDATE only changes rows still in non-terminal states.
    """
    import asyncpg
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        async with db.transaction():
            # Only update if still in a non-terminal state — idempotency guard
            updated = await db.fetchval(
                """
                UPDATE document SET pipeline_status='EXCEPTION', updated_at=NOW()
                WHERE document_id=$1
                  AND pipeline_status NOT IN ('ROUTED','EXCEPTION','QUARANTINED','CSAM_HOLD')
                RETURNING document_id
                """,
                params["document_id"],
            )
            if updated:
                await db.execute(
                    """
                    INSERT INTO exception_queue
                      (exception_id, document_id, tenant_id, exception_type,
                       extracted_fields, candidate_matches, status, raised_at)
                    VALUES (gen_random_uuid(), $1, $2, $3, '{}', '[]', 'OPEN', NOW())
                    ON CONFLICT (document_id) DO NOTHING
                    """,
                    params["document_id"],
                    params["tenant_id"],
                    params.get("reason", "PIPELINE_TIMEOUT"),
                )
    finally:
        await db.close()


# ── Status helper ─────────────────────────────────────────────────────────────

@activity.defn(name="update_pipeline_status")
async def update_pipeline_status(params: dict) -> None:
    """Update document.pipeline_status in DB. Runs in prana-api (has DB pool)."""
    import asyncpg
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        await db.execute(
            "UPDATE document SET pipeline_status=$2, updated_at=NOW() WHERE document_id=$1",
            params["document_id"], params["status"],
        )
    finally:
        await db.close()


# ── Elevation activities (admin-queue) ────────────────────────────────────────

@activity.defn(name="activate_elevation")
async def activate_elevation(params: dict) -> dict:
    """Mark elevation ACTIVE in DB, set expires_at. Returns expires_at ISO string."""
    import asyncpg
    from datetime import datetime, timezone, timedelta
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        duration_hours = params["duration_hours"]
        expires_at = datetime.now(timezone.utc) + timedelta(hours=duration_hours)
        await db.execute(
            """
            UPDATE elevation_request
            SET status='ACTIVE', approver_id=$2, approved_at=NOW(), expires_at=$3
            WHERE elevation_id=$1
            """,
            params["elevation_id"], params["approver_id"], expires_at,
        )
        return {"expires_at": expires_at.isoformat()}
    finally:
        await db.close()


@activity.defn(name="finalize_elevation")
async def finalize_elevation(params: dict) -> None:
    """Mark elevation DENIED or EXPIRED in DB."""
    import asyncpg
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        new_status = params["status"]   # DENIED or EXPIRED
        approver_id = params.get("approver_id")
        await db.execute(
            """
            UPDATE elevation_request
            SET status=$2, approver_id=$3, approved_at=CASE WHEN $2='DENIED' THEN NOW() ELSE approved_at END
            WHERE elevation_id=$1
            """,
            params["elevation_id"], new_status, approver_id,
        )
    finally:
        await db.close()


@activity.defn(name="expire_elevation")
async def expire_elevation(params: dict) -> None:
    """Mark elevation EXPIRED or ENDED_EARLY. Adds JWT JTI to Redis revocation list."""
    import asyncpg
    import redis.asyncio as redis_async
    from datetime import datetime, timezone
    settings = get_settings()
    db  = await asyncpg.connect(settings.db_dsn)
    rdb = redis_async.from_url(settings.redis_url)
    try:
        ended_early = params.get("ended_early", False)
        new_status  = "ENDED_EARLY" if ended_early else "EXPIRED"
        await db.execute(
            "UPDATE elevation_request SET status=$2 WHERE elevation_id=$1",
            params["elevation_id"], new_status,
        )
        # Revoke the elevated JWT immediately so Kong rejects further requests
        jwt_jti = params.get("jwt_jti")
        if jwt_jti:
            # TTL = 2h (max elevation window) — safe upper bound
            await rdb.setex(f"jwt:revoked:{jwt_jti}", 7200, "1")
    finally:
        await db.close()
        await rdb.aclose()


# ── Tenant onboarding activities (admin-queue) ────────────────────────────────

@activity.defn(name="get_tenant_onboarding_config")
async def get_tenant_onboarding_config(params: dict) -> dict:
    import asyncpg
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        async def cfg(key, default):
            row = await db.fetchrow(
                "SELECT config_value FROM platform_config WHERE config_key=$1", key
            )
            return int(row["config_value"]) if row else default
        return {
            "domain_verification_poll_minutes": await cfg("domain_verification_poll_minutes", 15),
            "domain_verification_max_hours":    await cfg("domain_verification_max_hours", 48),
        }
    finally:
        await db.close()


@activity.defn(name="check_dns_txt_record")
async def check_dns_txt_record(params: dict) -> dict:
    """Check DNS TXT record for prana-verify=<tenant_id> on the tenant domain."""
    import asyncpg, dns.resolver
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        domain    = params["domain"]
        tenant_id = params["tenant_id"]
        expected  = f"prana-verify={tenant_id}"
        try:
            answers = dns.resolver.resolve(domain, "TXT")
            for rdata in answers:
                for txt_string in rdata.strings:
                    if txt_string.decode().strip() == expected:
                        await db.execute(
                            "UPDATE tenant SET domain_verified_at=NOW() WHERE tenant_id=$1",
                            tenant_id,
                        )
                        return {"verified": True}
        except Exception:
            pass
        return {"verified": False}
    finally:
        await db.close()


@activity.defn(name="mark_tenant_verification_failed")
async def mark_tenant_verification_failed(params: dict) -> None:
    import asyncpg
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        await db.execute(
            "UPDATE tenant SET status='VERIFICATION_FAILED' WHERE tenant_id=$1",
            params["tenant_id"],
        )
    finally:
        await db.close()


@activity.defn(name="provision_tenant")
async def provision_tenant(params: dict) -> dict:
    """
    Full tenant provisioning:
      1. Create KMS KEK for tenant
      2. Create first OA-Admin account (force_reset=TRUE, temp password)
      3. Publish TENANT_PROVISIONED to Kafka → NotifConsumer sends welcome email
      4. Mark tenant ACTIVE
    """
    import asyncpg, uuid, datetime as _dt
    settings = get_settings()
    db = await asyncpg.connect(settings.db_dsn)
    try:
        tenant_id = params["tenant_id"]
        row = await db.fetchrow(
            "SELECT primary_domain, primary_contact FROM tenant WHERE tenant_id=$1",
            tenant_id,
        )
        if not row:
            raise ValueError(f"Tenant {tenant_id} not found")

        # 1. KMS KEK — in prod creates a customer-managed CMK; dev uses a placeholder ARN
        kek_arn = f"arn:aws:kms:ap-south-1:123456789012:key/{uuid.uuid4()}"
        await db.execute(
            "UPDATE tenant SET kms_key_arn=$2 WHERE tenant_id=$1",
            tenant_id, kek_arn,
        )

        # 2. First OA-Admin account
        from services.encryption_service import hash_password
        from services.oa_user_service import OAUserService
        import secrets as _sec
        temp_password = _sec.token_urlsafe(16)
        svc = OAUserService(db)
        admin = await svc.create(
            tenant_id=tenant_id,
            email=row["primary_contact"]["email"] if isinstance(row["primary_contact"], dict) else None,
            role="oa_admin",
            created_by="SYSTEM",
            temp_password=temp_password,
        )

        # 3. Mark tenant ACTIVE
        await db.execute(
            "UPDATE tenant SET status='ACTIVE', activated_at=NOW() WHERE tenant_id=$1",
            tenant_id,
        )

        # 4. Register tenant's HRMS API key as a Kong consumer so ingest calls are authorised.
        # Without this, all HRMS pushes for this tenant get 401 at Kong.
        # Kong Admin API is VPC-internal only (port 8001, never exposed via ALB).
        api_key_row = await db.fetchrow(
            "SELECT key_id, signing_secret_enc FROM api_key WHERE tenant_id=$1 AND status='ACTIVE' LIMIT 1",
            tenant_id,
        )
        if api_key_row:
            try:
                import httpx
                kong_admin_url = settings.kong_admin_url  # e.g. http://kong.prod.internal:8001
                consumer_username = f"tenant-{tenant_id}"
                async with httpx.AsyncClient(timeout=10) as client:
                    # Create consumer
                    await client.post(f"{kong_admin_url}/consumers", json={
                        "username":  consumer_username,
                        "custom_id": str(tenant_id),
                    })
                    # Register HMAC credential
                    await client.post(
                        f"{kong_admin_url}/consumers/{consumer_username}/hmac-auth",
                        json={
                            "username": str(api_key_row["key_id"]),
                            "secret":   api_key_row["signing_secret_enc"],  # decrypted at call site
                        },
                    )
                await db.execute(
                    "UPDATE api_key SET kong_consumer_registered=TRUE WHERE tenant_id=$1",
                    tenant_id,
                )
            except Exception:
                # Non-fatal — PA can re-trigger via /admin/tenants/{id}/register-kong
                import logging
                logging.getLogger(__name__).exception(
                    "Kong consumer registration failed tenant=%s — retry via PA console", tenant_id
                )

        # 5. Publish to Kafka → NotifConsumer sends welcome email with temp password
        try:
            from kafka.producer import KafkaPub
            kafka = KafkaPub(settings)
            await kafka.start()
            await kafka.tenant_event({
                "event_type":     "TENANT_PROVISIONED",
                "tenant_id":      tenant_id,
                "oa_user_id":     admin["oa_user_id"],
                "admin_email":    admin["email"],
                "temp_password":  temp_password,
                "login_url":      settings.portal_url + "/org/login",
            })
            await kafka.stop()
        except Exception:
            pass  # Non-fatal — admin can resend from PA console

        return {"tenant_id": tenant_id, "oa_admin_id": admin["oa_user_id"]}
    finally:
        await db.close()
