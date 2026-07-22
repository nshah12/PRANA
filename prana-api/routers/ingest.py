"""
Document ingest — OA-Operator / OA-Admin.

POST /ingest/upload              — single / multi-file upload → publishes DOC_INGESTED per file
POST /ingest/batch               — ZIP batch upload → publishes DOC_INGESTED per file + BATCH_UPLOADED
GET  /ingest/status/{doc_id}     — SSE stream via Redis Pub/Sub (NOT DB polling)
GET  /ingest/documents           — list documents for this tenant
GET  /ingest/exceptions          — list open exception queue items
POST /ingest/exceptions/{id}/resolve  — OA-Admin: assign employee_uuid, signal Temporal workflow
POST /ingest/exceptions/{id}/dismiss  — OA-Admin: dismiss unresolvable

HTTP handler contract (KAFKA_REDIS_ARCHITECTURE.md §4):
  validate → S3 put → 1 DB write → 1 Kafka publish → 202
  All audit writes, workflow starts, and notifications handled by consumers.

Exception signal (resolve/dismiss) is a direct Temporal signal — not a Kafka event —
because it targets a specific running workflow instance.
"""
import asyncio
from messages import SuccessCode, success_response
import datetime
import hashlib
import json
import uuid
import zipfile
import io
from typing import Optional, AsyncGenerator, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from dependencies import ApiKeyAuth, DbConn, require_oa
from kafka.producer import TOPIC_INGEST
from errors import PranaError
from services.statutory_hold_service import compute_hold_until
from services.checklist_service import ChecklistService, ChecklistIncompleteError

router = APIRouter()

OAOperator = Depends(require_oa("oa_operator", "oa_admin"))
OAAdmin    = Depends(require_oa("oa_admin"))

_ALLOWED_EXTENSIONS = {"pdf"}
_MAX_BATCH_BYTES    = 500 * 1024 * 1024   # 500 MB compressed archive (spec §4 Upload)
# Zip-bomb defences (H4): a small archive must not inflate without bound.
_MAX_UNCOMPRESSED_TOTAL_BYTES = 2 * 1024 * 1024 * 1024   # 2 GB total decompressed
_MAX_ENTRY_UNCOMPRESSED_BYTES = 200 * 1024 * 1024        # 200 MB per file
_MAX_COMPRESSION_RATIO        = 200                       # entry uncompressed / compressed


# ── Multi-file upload (1–N PDFs) ──────────────────────────────────────────────

@router.post("/upload", status_code=status.HTTP_202_ACCEPTED, dependencies=[OAOperator])
async def upload_documents(
    request: Request,
    db: DbConn,
    files: List[UploadFile] = File(...),
    doc_type: str = Form(...),
    doc_period: Optional[str] = Form(None),
    comment: Optional[str] = Form(None),
    current=Depends(require_oa("oa_operator", "oa_admin")),
):
    """Accept 1-N PDF files. Each gets its own document_id and DOC_INGESTED Kafka event."""
    await _assert_checklist_complete(db, current.tenant_id)
    started_at  = datetime.datetime.now(datetime.timezone.utc)
    ip          = _client_ip(request)
    ua          = request.headers.get("user-agent", "")
    actor_type  = _actor_type(current.role)
    batch_id    = str(uuid.uuid4()) if len(files) > 1 else None
    results     = []
    errors: list = []
    total_bytes = 0
    kafka       = request.app.state.kafka_producer

    for f in files:
        file_bytes = await f.read()
        try:
            _validate_file(f.filename, file_bytes)
        except HTTPException as e:
            errors.append({"filename": f.filename, "error": e.detail})
            results.append({"filename": f.filename, "error": e.detail})
            if kafka:
                try:
                    await kafka.integration_event({
                        "event_type": "HRMS_WEBHOOK_FAILED",
                        "tenant_id":  current.tenant_id,
                        "reason":     e.detail,
                        "filename":   f.filename,
                        "actor_id":   current.user_id,
                    })
                except Exception as exc:
                    from services.error_observability_service import ErrorObservabilityService
                    try:
                        await ErrorObservabilityService(db).record(
                            exc=exc, source="HTTP", source_detail="upload_documents:publish_hrms_webhook_failed",
                        )
                    except Exception:
                        pass
            continue

        total_bytes += len(file_bytes)
        doc_id, event = await _ingest_one(
            request=request, db=db,
            file_bytes=file_bytes, filename=f.filename,
            doc_type=doc_type, doc_period=doc_period,
            tenant_id=current.tenant_id, actor_id=current.user_id,
            actor_type=actor_type, batch_id=batch_id, comment=comment,
            ip_address=ip, user_agent=ua,
        )
        await kafka.doc_ingested(event)
        results.append({"filename": f.filename, "document_id": doc_id, "pipeline_status": "QUEUED"})

    # BATCH_UPLOADED event — consumed by AuditConsumer + WorkflowConsumer(BatchProgressWorkflow)
    accepted = [r for r in results if "document_id" in r]
    if batch_id:
        ended_at = datetime.datetime.now(datetime.timezone.utc)
        batch_event = {
            "event_type":  "BATCH_UPLOADED",
            "event_id":    str(uuid.uuid4()),
            "occurred_at": ended_at.isoformat(),
            "tenant_id":   current.tenant_id,
            "batch_id":    batch_id,
            "doc_type":    doc_type,
            "doc_period":  doc_period,
            "source":      "PORTAL_UPLOAD",
            "total":       len(files),
            "accepted":    len(accepted),
            "rejected":    len(errors),
            "total_bytes": total_bytes,
            "started_at":  started_at.isoformat(),
            "ended_at":    ended_at.isoformat(),
            "duration_ms": int((ended_at - started_at).total_seconds() * 1000),
            "filenames":   [f.filename for f in files],
            "errors":      errors,
            "actor_id":    current.user_id,
            "actor_type":  actor_type,
            "ip_address":  ip,
            "user_agent":  ua,
        }
        await kafka.batch_uploaded(batch_event)

    if len(results) == 1 and "error" not in results[0]:
        return results[0]
    return {"batch_id": batch_id, "files": results, "total": len(results)}


# ── ZIP batch upload ──────────────────────────────────────────────────────────

@router.post("/batch", status_code=status.HTTP_202_ACCEPTED, dependencies=[OAOperator])
async def batch_upload(
    request: Request,
    db: DbConn,
    archive: UploadFile = File(...),
    doc_type: str = Form(...),
    doc_period: Optional[str] = Form(None),
    comment: Optional[str] = Form(None),
    current=Depends(require_oa("oa_operator", "oa_admin")),
):
    await _assert_checklist_complete(db, current.tenant_id)
    started_at    = datetime.datetime.now(datetime.timezone.utc)
    ip            = _client_ip(request)
    ua            = request.headers.get("user-agent", "")
    actor_type    = _actor_type(current.role)
    kafka         = request.app.state.kafka_producer
    archive_bytes = await archive.read()

    if not archive.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PranaError.ARCHIVE_MUST_BE_ZIP)

    # H4: reject an oversized compressed archive before touching it.
    if len(archive_bytes) > _MAX_BATCH_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=PranaError.ARCHIVE_TOO_LARGE)

    batch_id = str(uuid.uuid4())
    results: list  = []
    errors: list   = []
    total_bytes    = 0
    uncompressed_total = 0

    try:
        zf = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PranaError.INVALID_ZIP)

    # H4: pre-flight the central directory (declared sizes, no decompression yet).
    _assert_not_zip_bomb(zf)

    all_filenames = [e.filename for e in zf.infolist() if not e.is_dir()]

    for entry in zf.infolist():
        if entry.is_dir():
            continue
        ext = entry.filename.rsplit(".", 1)[-1].lower() if "." in entry.filename else ""
        if ext not in _ALLOWED_EXTENSIONS:
            errors.append({"filename": entry.filename, "error": "UNSUPPORTED_FILE_TYPE"})
            continue

        file_bytes = zf.read(entry.filename)
        # Content sniff (not just extension) — reject non-PDFs renamed to .pdf.
        if not file_bytes.startswith(b"%PDF-"):
            errors.append({"filename": entry.filename, "error": "UNSUPPORTED_FILE_TYPE"})
            continue
        total_bytes += len(file_bytes)

        doc_id, event = await _ingest_one(
            request=request, db=db,
            file_bytes=file_bytes, filename=entry.filename,
            doc_type=doc_type, doc_period=doc_period,
            tenant_id=current.tenant_id, actor_id=current.user_id,
            actor_type=actor_type, batch_id=batch_id, comment=comment,
            ip_address=ip, user_agent=ua,
        )
        await kafka.doc_ingested(event)
        results.append({"filename": entry.filename, "document_id": doc_id, "pipeline_status": "QUEUED"})

    accepted  = [r for r in results if "document_id" in r]
    ended_at  = datetime.datetime.now(datetime.timezone.utc)

    if accepted:
        # BatchProgressWorkflow's write_batch_summary activity UPDATEs this row once
        # every child pipeline settles — must exist before that workflow starts.
        await db.execute(
            "INSERT INTO document_batch (batch_id, tenant_id, total_files, status) "
            "VALUES ($1, $2, $3, 'PROCESSING')",
            batch_id, current.tenant_id, len(accepted),
        )

    batch_event = {
        "event_type":  "BATCH_UPLOADED",
        "event_id":    str(uuid.uuid4()),
        "occurred_at": ended_at.isoformat(),
        "tenant_id":   current.tenant_id,
        "batch_id":    batch_id,
        "doc_type":    doc_type,
        "doc_period":  doc_period,
        "source":      "PORTAL_ZIP",
        "total":       len(all_filenames),
        "accepted":    len(accepted),
        "rejected":    len(errors),
        "total_bytes": total_bytes,
        "started_at":  started_at.isoformat(),
        "ended_at":    ended_at.isoformat(),
        "duration_ms": int((ended_at - started_at).total_seconds() * 1000),
        "filenames":   all_filenames,
        "errors":      errors,
        "actor_id":    current.user_id,
        "actor_type":  actor_type,
        "ip_address":  ip,
        "user_agent":  ua,
    }
    await kafka.batch_uploaded(batch_event)

    return {"batch_id": batch_id, "files": results, "total": len(results)}


# ── SSE pipeline status stream (Redis Pub/Sub — NOT DB polling) ───────────────

@router.get("/status/{document_id}")
async def pipeline_status_stream(
    document_id: str,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_operator", "oa_admin")),
):
    """
    Server-Sent Events: subscribes to Redis channel sse:doc:{document_id}.
    SSEFanoutConsumer publishes to this channel when pipeline stage changes.
    Closes on terminal state or 6-minute hard timeout.
    """
    tenant_id    = current.tenant_id
    redis_client = request.app.state.redis

    # Verify document belongs to this tenant before opening subscription
    row = await db.fetchrow(
        "SELECT pipeline_status FROM document WHERE document_id=$1 AND tenant_id=$2",
        document_id, tenant_id,
    )
    if not row:
        from services.tenant_isolation_guard import TenantIsolationGuard
        await TenantIsolationGuard(db).check_document_access(
            document_id=document_id, requesting_tenant_id=tenant_id, actor_id=current.user_id,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.DOCUMENT_NOT_FOUND)

    initial_status = row["pipeline_status"]

    async def _generate() -> AsyncGenerator[str, None]:
        # Emit current status immediately so UI doesn't wait for next stage change
        yield _sse({"document_id": document_id, "pipeline_status": initial_status})

        if initial_status in ("ROUTED", "EXCEPTION", "QUARANTINED"):
            return

        channel = f"sse:doc:{document_id}"
        pubsub  = redis_client.pubsub()
        await pubsub.subscribe(channel)

        try:
            deadline = asyncio.get_event_loop().time() + 360   # 6 min hard ceiling
            async for message in pubsub.listen():
                if await request.is_disconnected():
                    break
                if asyncio.get_event_loop().time() > deadline:
                    break
                if message["type"] != "message":
                    continue
                data = json.loads(message["data"])
                yield _sse(data)
                if data.get("pipeline_status") in ("ROUTED", "EXCEPTION", "QUARANTINED"):
                    break
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    return StreamingResponse(_generate(), media_type="text/event-stream")


# ── Document list ─────────────────────────────────────────────────────────────

@router.get("/documents", status_code=status.HTTP_200_OK, dependencies=[OAOperator])
async def list_documents(
    db: DbConn,
    pipeline_status: Optional[str] = None,
    doc_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current=Depends(require_oa("oa_operator", "oa_admin")),
):
    conditions = ["tenant_id=$1", "is_deleted=FALSE", "employer_visible=TRUE"]
    params: list = [current.tenant_id]
    i = 2

    if pipeline_status:
        conditions.append(f"pipeline_status=${i}"); params.append(pipeline_status); i += 1
    if doc_type:
        conditions.append(f"doc_type=${i}"); params.append(doc_type); i += 1

    where = " AND ".join(conditions)
    total = await db.fetchval(
        "SELECT COUNT(*) FROM document WHERE " + where,
        *params,
    )
    lim_i = i
    off_i = i + 1
    rows = await db.fetch(
        f"""
        SELECT document_id, doc_type, doc_period, pipeline_status,
               resolution_method, resolution_confidence, pushed_at, routed_at
        FROM document WHERE {where}
        ORDER BY pushed_at DESC LIMIT ${lim_i} OFFSET ${off_i}
        """,
        *params, min(limit, 200), offset,
    )
    docs = [
        {
            "document_id": str(r["document_id"]),
            "doc_type": r["doc_type"],
            "doc_period": r["doc_period"],
            "pipeline_status": r["pipeline_status"],
            "resolution_method": r["resolution_method"],
            "resolution_confidence": r["resolution_confidence"],
            "pushed_at": r["pushed_at"].isoformat() if r["pushed_at"] else None,
            "routed_at": r["routed_at"].isoformat() if r["routed_at"] else None,
        }
        for r in rows
    ]
    return {"documents": docs, "total": int(total or 0)}


# ── Dashboard stats ───────────────────────────────────────────────────────────

@router.get("/stats", status_code=status.HTTP_200_OK)
async def dashboard_stats(
    db: DbConn,
    current=Depends(require_oa("oa_operator", "oa_admin")),
):
    total_docs = await db.fetchval(
        "SELECT COUNT(*) FROM document WHERE tenant_id=$1 AND is_deleted=FALSE AND employer_visible=TRUE",
        current.tenant_id,
    )
    pending = await db.fetchval(
        """
        SELECT COUNT(*) FROM document
        WHERE tenant_id=$1 AND is_deleted=FALSE AND employer_visible=TRUE
          AND pipeline_status NOT IN ('ROUTED','EXCEPTION')
        """,
        current.tenant_id,
    )
    employees = await db.fetchval(
        "SELECT COUNT(*) FROM employee_master WHERE tenant_id=$1 AND status='ACTIVE'",
        current.tenant_id,
    )
    open_exceptions = await db.fetchval(
        "SELECT COUNT(*) FROM exception_queue WHERE tenant_id=$1 AND status='OPEN'",
        current.tenant_id,
    )
    return {
        "documents_pushed": int(total_docs or 0),
        "pending_pipeline": int(pending or 0),
        "employees": int(employees or 0),
        "open_exceptions": int(open_exceptions or 0),
    }


# ── Exception queue ───────────────────────────────────────────────────────────

@router.get("/exceptions", status_code=status.HTTP_200_OK)
async def list_exceptions(
    db: DbConn,
    current=Depends(require_oa("oa_operator", "oa_admin")),
):
    rows = await db.fetch(
        """
        SELECT eq.exception_id, eq.document_id, eq.exception_type,
               eq.extracted_fields, eq.candidate_matches, eq.status, eq.raised_at,
               d.doc_type, d.doc_period
        FROM exception_queue eq
        JOIN document d ON d.document_id = eq.document_id
        WHERE eq.tenant_id=$1 AND eq.status='OPEN'
        ORDER BY eq.raised_at ASC
        """,
        current.tenant_id,
    )
    import json as _json
    def _parse_jsonb(v):
        if v is None: return None
        if isinstance(v, str):
            try: return _json.loads(v)
            except (ValueError, TypeError): return v
        return v
    return {"exceptions": [
        {
            "exception_id": str(r["exception_id"]),
            "document_id": str(r["document_id"]),
            "exception_type": r["exception_type"],
            "extracted_fields": _parse_jsonb(r["extracted_fields"]),
            "candidate_matches": _parse_jsonb(r["candidate_matches"]),
            "status": r["status"],
            "raised_at": r["raised_at"].isoformat() if r["raised_at"] else None,
            "doc_type": r["doc_type"],
            "doc_period": r["doc_period"],
        }
        for r in rows
    ], "total": len(rows)}


class ResolveExceptionIn(BaseModel):
    employee_uuid: str


@router.post("/exceptions/{exception_id}/resolve", status_code=status.HTTP_200_OK)
async def resolve_exception(
    exception_id: str,
    body: ResolveExceptionIn,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_admin")),
):
    row = await db.fetchrow(
        "SELECT document_id, status FROM exception_queue WHERE exception_id=$1 AND tenant_id=$2",
        exception_id, current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.EXCEPTION_NOT_FOUND)
    if row["status"] != "OPEN":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PranaError.ALREADY_RESOLVED)

    async with db.transaction():
        await db.execute(
            "UPDATE exception_queue SET status='RESOLVED', resolved_by=$2, "
            "resolved_employee_uuid=$3, resolved_at=NOW() WHERE exception_id=$1",
            exception_id, current.user_id, body.employee_uuid,
        )

    # Publish EXCEPTION_RESOLVED — AuditConsumer writes the audit row
    kafka = request.app.state.kafka_producer
    await kafka.exception_resolved({
        "event_type":    "EXCEPTION_RESOLVED",
        "event_id":      str(uuid.uuid4()),
        "occurred_at":   datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tenant_id":     current.tenant_id,
        "document_id":   row["document_id"],
        "exception_id":  exception_id,
        "employee_uuid": body.employee_uuid,
        "resolution":    "MANUAL_OA_ADMIN",
        "actor_id":      current.user_id,
        "actor_type":    "OA_ADMIN",
        "ip_address":    _client_ip(request),
    })

    # Direct Temporal signal — targets this specific running workflow instance
    temporal_client = getattr(request.app.state, "temporal_client", None)
    if temporal_client:
        try:
            wf = temporal_client.get_workflow_handle(f"doc-pipeline-{row['document_id']}")
            await wf.signal(
                "exception_resolved",
                {"employee_uuid": body.employee_uuid, "method": "MANUAL_OA", "confidence": 1.0},
            )
        except Exception as exc:
            from services.error_observability_service import ErrorObservabilityService
            try:
                await ErrorObservabilityService(db).record(
                    exc=exc, source="HTTP", source_detail="resolve_exception:signal_workflow",
                )
            except Exception:
                pass
            # workflow may have timed out — DB is source of truth

    return {"message": SuccessCode.EXCEPTION_RESOLVED}


@router.post("/exceptions/{exception_id}/dismiss", status_code=status.HTTP_200_OK)
async def dismiss_exception(
    exception_id: str,
    request: Request,
    db: DbConn,
    current=Depends(require_oa("oa_admin")),
):
    row = await db.fetchrow(
        "SELECT document_id FROM exception_queue WHERE exception_id=$1 AND tenant_id=$2 AND status='OPEN'",
        exception_id, current.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.EXCEPTION_NOT_FOUND)

    async with db.transaction():
        await db.execute(
            "UPDATE exception_queue SET status='DISMISSED', resolved_by=$2, resolved_at=NOW() "
            "WHERE exception_id=$1 AND tenant_id=$2 AND status='OPEN'",
            exception_id, current.user_id,
        )

    kafka = request.app.state.kafka_producer
    await kafka.exception_resolved({
        "event_type":   "EXCEPTION_DISMISSED",
        "event_id":     str(uuid.uuid4()),
        "occurred_at":  datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tenant_id":    current.tenant_id,
        "document_id":  row["document_id"],
        "exception_id": exception_id,
        "resolution":   "DISMISSED",
        "actor_id":     current.user_id,
        "actor_type":   "OA_ADMIN",
        "ip_address":   _client_ip(request),
    })

    return {"message": SuccessCode.EXCEPTION_DISMISSED}


# ── HRMS API-key push (X-PRANA-Key-ID + X-PRANA-Signature) ────────────────────
# integrations.md "HRMS push endpoint behaviour":
#   validate signature → validate payload → S3 put → INSERT document
#   → kafka.doc_ingested() → 202. Idempotent: dedup handled by
#   _ingest_one()'s file_hash check (reused from the OA-Operator path).
#
# The request body IS the raw file (Content-Type: application/pdf), not
# multipart — ApiKeyAuth verifies HMAC-SHA256 over the raw body, and
# multipart/Form parsing would consume the same stream before the signature
# can be checked. Metadata travels as query params instead.

@router.post("/hrms/upload", status_code=status.HTTP_202_ACCEPTED)
async def hrms_upload(
    request: Request,
    db: DbConn,
    api_key: ApiKeyAuth,
    doc_type: str,
    filename: str,
    doc_period: Optional[str] = None,
):
    """Single-file HRMS partner push. Auth + rate limiting handled by ApiKeyAuth."""
    await _assert_checklist_complete(db, api_key.tenant_id)
    file_bytes = await request.body()  # cached by ApiKeyAuth's earlier read
    _validate_file(filename, file_bytes)

    kafka = request.app.state.kafka_producer
    doc_id, event = await _ingest_one(
        request=request, db=db,
        file_bytes=file_bytes, filename=filename,
        doc_type=doc_type, doc_period=doc_period,
        tenant_id=api_key.tenant_id, actor_id=None,
        actor_type="HRMS_API", batch_id=None, comment=None,
        ip_address=_client_ip(request), user_agent=request.headers.get("user-agent", ""),
    )
    await kafka.doc_ingested(event)
    return {"document_id": doc_id, "pipeline_status": "QUEUED"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _assert_not_zip_bomb(zf: zipfile.ZipFile) -> None:
    """
    Reject decompression bombs (H4) using declared central-directory sizes — no
    decompression happens here. Trips on: an entry too large uncompressed, an absurd
    per-entry compression ratio, or an oversized decompressed total across the archive.
    """
    uncompressed_total = 0
    for entry in zf.infolist():
        if entry.is_dir():
            continue
        if entry.file_size > _MAX_ENTRY_UNCOMPRESSED_BYTES:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=PranaError.ZIP_BOMB_DETECTED)
        if entry.compress_size > 0 and (entry.file_size / entry.compress_size) > _MAX_COMPRESSION_RATIO:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=PranaError.ZIP_BOMB_DETECTED)
        uncompressed_total += entry.file_size
        if uncompressed_total > _MAX_UNCOMPRESSED_TOTAL_BYTES:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=PranaError.ZIP_BOMB_DETECTED)


async def _assert_checklist_complete(db, tenant_id: str) -> None:
    """
    Go-Live Checklist gate — blocks all 3 upload entrypoints until every
    required active item (platform baseline + this tenant's own) has a
    completion row. Called once per HTTP request, before any file processing.

    tenant_id is passed through as-is (no uuid.UUID() cast) — matching every
    other tenant_id use in this file; asyncpg coerces the string at the wire
    level against the UUID column, same as _ingest_one()'s own queries do.
    """
    try:
        await ChecklistService(db).assert_upload_allowed(tenant_id)
    except ChecklistIncompleteError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": PranaError.SETUP_CHECKLIST_INCOMPLETE,
                "missing_item_keys": exc.missing_item_keys,
            },
        )


def _validate_file(filename: str, file_bytes: bytes) -> None:
    ext = filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PranaError.UNSUPPORTED_FILE_TYPE)
    if len(file_bytes) == 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PranaError.EMPTY_FILE)
    # Content sniff (not just extension): a real PDF begins with the %PDF- magic bytes.
    # Rejects a malicious/other file renamed to .pdf before it reaches the pipeline.
    if not file_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=PranaError.UNSUPPORTED_FILE_TYPE)


async def _ingest_one(
    *,
    request: Request,
    db,
    file_bytes: bytes,
    filename: str,
    doc_type: str,
    doc_period: Optional[str],
    tenant_id: str,
    actor_id: str,
    actor_type: str,
    batch_id: Optional[str],
    comment: Optional[str],
    ip_address: str,
    user_agent: str,
) -> tuple[str, dict]:
    """
    Write one document row to DB + S3. Returns (document_id, DOC_INGESTED event dict).
    Does NOT write audit, does NOT start workflows — those are consumer responsibilities.
    """
    settings    = request.app.state.settings
    document_id = str(uuid.uuid4())
    file_hash   = hashlib.sha256(file_bytes).hexdigest()

    # Dedup: same file hash within tenant → return existing id, no duplicate event
    existing = await db.fetchval(
        "SELECT document_id FROM document WHERE tenant_id=$1 AND file_hash_sha256=$2 AND is_deleted=FALSE",
        tenant_id, file_hash,
    )
    if existing:
        # Re-use existing doc_id but still build a minimal event so caller can respond
        event = _build_doc_ingested_event(
            document_id=str(existing), tenant_id=tenant_id, batch_id=batch_id,
            doc_type=doc_type, doc_period=doc_period, filename=filename,
            file_size_bytes=len(file_bytes), file_hash=file_hash,
            s3_key=f"staging/{tenant_id}/{existing}.pdf",
            s3_bucket=settings.s3_bucket_staging,
            actor_id=actor_id, actor_type=actor_type,
            ip_address=ip_address, user_agent=user_agent, comment=comment,
        )
        return str(existing), event

    # Stage 01: upload to S3/MinIO staging
    # hash_prefix: first 4 chars of the UUID distribute writes across 65,536 S3 key prefixes,
    # avoiding the 3,500 req/s per-prefix throttle under large batch loads.
    ext = filename.rsplit(".", 1)[-1].lower()
    hash_prefix = document_id[:4]
    staging_key = f"staging/{hash_prefix}/{tenant_id}/{document_id}.{ext}"
    await request.app.state.s3.put_object_async(
        settings.s3_bucket_staging, staging_key, file_bytes, content_type="application/pdf"
    )

    await db.execute(
        """
        INSERT INTO document
          (document_id, tenant_id, doc_type, doc_period, s3_key, s3_bucket,
           file_size_bytes, file_hash_sha256, pipeline_status,
           uploaded_by_oa, batch_id, is_self_upload,
           original_filename, upload_comment, pushed_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'QUEUED',$9,$10,FALSE,$11,$12,NOW())
        """,
        document_id, tenant_id, doc_type, doc_period,
        staging_key, settings.s3_bucket_staging,
        len(file_bytes), file_hash,
        actor_id, batch_id, filename, comment,
    )

    # Infer statutory retention hold from doc_type — set at upload so ErasureWorkflow
    # can check it without needing the original upload context.
    from datetime import date as _date
    hold_reason, hold_until = compute_hold_until(doc_type, _date.today())
    if hold_until:
        await db.execute(
            "UPDATE document SET statutory_hold_reason=$1, statutory_hold_until=$2, "
            "statutory_hold_set_at=NOW(), statutory_hold_set_by='SYSTEM_INFER' "
            "WHERE document_id=$3",
            hold_reason, hold_until, document_id,
        )

    event = _build_doc_ingested_event(
        document_id=document_id, tenant_id=tenant_id, batch_id=batch_id,
        doc_type=doc_type, doc_period=doc_period, filename=filename,
        file_size_bytes=len(file_bytes), file_hash=file_hash,
        s3_key=staging_key, s3_bucket=settings.s3_bucket_staging,
        actor_id=actor_id, actor_type=actor_type,
        ip_address=ip_address, user_agent=user_agent, comment=comment,
    )
    return document_id, event


def _build_doc_ingested_event(
    *, document_id: str, tenant_id: str, batch_id: Optional[str],
    doc_type: str, doc_period: Optional[str], filename: str,
    file_size_bytes: int, file_hash: str,
    s3_key: str, s3_bucket: str,
    actor_id: str, actor_type: str,
    ip_address: str, user_agent: str, comment: Optional[str],
) -> dict:
    return {
        "event_type":        "DOC_INGESTED",
        "event_id":          str(uuid.uuid4()),
        "occurred_at":       datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tenant_id":         tenant_id,
        "document_id":       document_id,
        "batch_id":          batch_id,
        "doc_type":          doc_type,
        "doc_period":        doc_period,
        "s3_key":            s3_key,
        "s3_bucket":         s3_bucket,
        "file_size_bytes":   file_size_bytes,
        "file_hash_sha256":  file_hash,
        "original_filename": filename,
        "upload_comment":    comment,
        "actor_id":          actor_id,
        "actor_type":        actor_type,
        "ip_address":        ip_address,
        "user_agent":        user_agent,
    }


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _client_ip(request: Request) -> str:
    # Spoof-resistant (H3): trust only the hop our proxy appended, not the leftmost.
    from lib.client_ip import get_client_ip
    return get_client_ip(request, request.app.state.settings.trusted_proxy_count)


def _actor_type(role: str, is_elevated: bool = False) -> str:
    if role == "oa_admin":
        return "OA_ADMIN"
    if is_elevated:
        return "OA_OPERATOR_ELEVATED"
    return "OA_OPERATOR"

