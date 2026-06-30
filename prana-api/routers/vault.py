"""
Employee vault — authenticated employee reads their own documents.

GET  /vault/documents              — list all documents (cross-employer)
GET  /vault/documents/{id}         — stream decrypted + watermarked PDF
GET  /vault/timeline               — career events (all employers, newest first)
GET  /vault/health                 — vault completeness score + gap detail
GET  /vault/employers              — employer stubs in vault
GET  /vault/profile                — employee profile across employers
POST /vault/share                  — create C-Share token
GET  /vault/share                  — list employee's active share tokens
DELETE /vault/share/{share_id}     — revoke share token
POST /vault/requests               — request document from employer
GET  /vault/requests               — list employee's requests

All routes require employee JWT. tenant_id / employee_user_id always from JWT.
"""
import io
from typing import Optional

import boto3
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from dependencies import AuthUser, Employee, DbConn
from services.vault_service import VaultService
from services.share_service import ShareService
from errors import PranaError

router = APIRouter()


def _vault(request: Request, db: DbConn, current) -> VaultService:
    settings = request.app.state.settings
    return VaultService(
        db=db,
        kms=request.app.state.kms_service,
        s3_client=request.app.state.s3,
        documents_bucket=settings.s3_bucket_documents,
        kafka_producer=getattr(request.app.state, "kafka_producer", None),
    )


def _share(request: Request, db: DbConn) -> ShareService:
    return ShareService(db=db, redis=request.app.state.redis, settings=request.app.state.settings)


# ── Documents ─────────────────────────────────────────────────────────────────

@router.get("/documents")
async def list_documents(
    request: Request,
    db: DbConn,
    current: Employee,
    doc_type: Optional[str] = None,
    tenant_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    svc = _vault(request, db, current)
    docs = await svc.list_documents(
        current.user_id,
        doc_type=doc_type,
        tenant_id=tenant_id,
        limit=min(limit, 100),
        offset=offset,
    )
    return {"documents": docs, "count": len(docs)}


@router.get("/documents/{document_id}")
async def view_document(
    document_id: str,
    request: Request,
    db: DbConn,
    current: Employee,
    download: bool = False,
):
    """
    Streams the decrypted document with PRANA watermark.
    Writes document_access_log for every call.
    """
    svc = _vault(request, db, current)
    try:
        plaintext, doc_type = await svc.get_document_bytes(
            document_id=document_id,
            employee_user_id=current.user_id,
            actor_ip=request.client.host if request.client else "0.0.0.0",
            session_id=current.session_id,
            access_type="DOWNLOAD" if download else "VIEW",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    try:
        watermarked = _apply_watermark(plaintext, current.user_id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WATERMARK_ENGINE_UNAVAILABLE",
        ) from exc

    disposition = "attachment" if download else "inline"
    media_type = "application/pdf" if plaintext[:4] == b"%PDF" else "application/octet-stream"

    return StreamingResponse(
        io.BytesIO(watermarked),
        media_type=media_type,
        headers={"Content-Disposition": f'{disposition}; filename="{document_id}.pdf"'},
    )


# ── Timeline ──────────────────────────────────────────────────────────────────

@router.get("/documents/{document_id}/credential")
async def get_credential(document_id: str, request: Request, db: DbConn, current: Employee):
    """
    Career Passport credential card — returns verification metadata for a ROUTED document.
    Employee-facing: used to display QR code + share credential with recruiters/banks.
    Privacy: returns only non-sensitive metadata — no raw salary, no PAN, no insights.
    """
    row = await db.fetchrow(
        """
        SELECT d.document_id, d.pipeline_status, d.verification_code,
               d.doc_type, d.doc_period, d.pushed_at, d.routed_at, d.file_hash_sha256,
               t.tenant_name
        FROM document d
        JOIN employee_master em ON em.employee_uuid = d.employee_uuid
        JOIN employee_user eu ON eu.employee_user_id = em.employee_user_id
        JOIN tenant t ON t.tenant_id = d.tenant_id
        WHERE d.document_id = $1::uuid
          AND eu.employee_user_id = $2::uuid
          AND d.is_deleted = FALSE
        LIMIT 1
        """,
        document_id, current.user_id,
    )

    if not row or row["pipeline_status"] != "ROUTED" or not row["verification_code"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.DOCUMENT_NOT_FOUND)

    code = row["verification_code"]
    return {
        "verification_code": code,
        "verify_url":        f"https://verify.prana.in/{code}",
        "qr_url":            f"/public/qr/{code}",
        "doc_type":          row["doc_type"],
        "doc_period":        row["doc_period"],
        "pushed_by":         row["tenant_name"],
        "pushed_at":         row["pushed_at"].isoformat() if row["pushed_at"] else None,
        "routed_at":         row["routed_at"].isoformat() if row["routed_at"] else None,
        "file_hash_sha256":  row["file_hash_sha256"],
    }


@router.get("/timeline")
async def get_timeline(request: Request, db: DbConn, current: Employee):
    svc = _vault(request, db, current)
    events = await svc.get_timeline(current.user_id)
    return {"events": events}


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def get_health(request: Request, db: DbConn, current: Employee):
    svc = _vault(request, db, current)
    health = await svc.get_health(current.user_id)
    if not health:
        return {"overall_score": 0, "gap_count": 0, "gap_detail": [], "computed_at": None}
    import json as _json
    gap = health["gap_detail"] or []
    if isinstance(gap, str):
        try: gap = _json.loads(gap)
        except Exception: gap = []
    return {
        "overall_score": health["overall_score"],
        "gap_count": health["gap_count"],
        "gap_detail": gap,
        "computed_at": health["computed_at"].isoformat() if health.get("computed_at") else None,
    }


# ── Employers ─────────────────────────────────────────────────────────────────

@router.get("/employers")
async def get_employers(request: Request, db: DbConn, current: Employee):
    svc = _vault(request, db, current)
    employers = await svc.get_employers(current.user_id)
    return {"employers": employers}


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get("/profile")
async def get_profile(request: Request, db: DbConn, current: Employee):
    """
    Returns employee_user data + all employer records (no raw ₹ or PAN).
    enc_pan and enc_dek are never returned — only derived display fields.
    """
    row = await db.fetchrow(
        """
        SELECT eu.employee_user_id, eu.mobile, eu.status,
               eu.created_at,
               em.full_name, em.designation, em.department,
               em.employee_user_id AS master_user_id
        FROM employee_user eu
        LEFT JOIN employee_master em ON em.employee_user_id = eu.employee_user_id
          AND em.status = 'ACTIVE'
        WHERE eu.employee_user_id = $1
        LIMIT 1
        """,
        current.user_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    svc = _vault(request, db, current)
    employers = await svc.get_employers(current.user_id)

    # Build vault_url from name slug (display only, no PII risk)
    name_slug = (row["full_name"] or "user").lower().replace(" ", "-")
    short_id = str(row["employee_user_id"])[:8]

    return {
        "employee_user_id": str(row["employee_user_id"]),
        "name": row["full_name"] or "—",
        "mobile": row["mobile"],
        "status": row["status"],
        "vault_url": f"prana.in/vault/{name_slug}-{short_id}",
        "has_totp": True,   # if logged in, TOTP was already verified
        "employer_count": len(employers),
        "active_since": row["created_at"].isoformat() if row["created_at"] else None,
        "employers": employers,
    }


# ── Career (growth index + employer timeline) ──────────────────────────────────

@router.get("/career")
async def get_career(request: Request, db: DbConn, current: Employee):
    """
    Returns career growth data derived entirely from insights (no raw ₹).
    growth_data: list of {period, index, employer_id, employer_name, note}
    employers: list of {id, name, role, from, to}
    events: list of career_event rows (JOINED/PROMOTED/EXITED/INCREMENT)
    """
    employee_uuid = await db.fetchval(
        "SELECT employee_uuid FROM employee_master WHERE employee_user_id=$1 ORDER BY doj DESC LIMIT 1",
        current.user_id,
    )
    if not employee_uuid:
        return {"growth_data": [], "employers": [], "events": []}

    # Career events in chronological order
    event_rows = await db.fetch(
        """
        SELECT ce.event_type, ce.event_date,
               t.tenant_name AS employer_name,
               em.designation, em.department,
               em.employee_uuid,
               ce.metadata
        FROM career_event ce
        JOIN employee_master em ON em.employee_uuid = ce.employee_uuid
        JOIN tenant t ON t.tenant_id = em.tenant_id
        WHERE ce.employee_user_id = $1
        ORDER BY ce.event_date ASC
        """,
        current.user_id,
    )

    # Employer timeline — one entry per employer (group by tenant)
    employer_rows = await db.fetch(
        """
        SELECT DISTINCT ON (em.tenant_id)
               em.employee_uuid AS id,
               t.tenant_name AS name,
               em.designation AS role,
               em.doj AS "from",
               em.dol AS "to"
        FROM employee_master em
        JOIN tenant t ON t.tenant_id = em.tenant_id
        WHERE em.employee_user_id = $1
        ORDER BY em.tenant_id, em.doj ASC
        """,
        current.user_id,
    )

    # Build growth_data: derive index from salary_band percentile insights
    # Index 100 = first document's salary band; subsequent increments are relative
    growth_rows = await db.fetch(
        """
        SELECT d.doc_period, d.doc_type,
               t.tenant_name AS employer_name,
               em.employee_uuid AS employer_id,
               ce.insight_text,
               (d.extracted_fields->>'growth_index')::int AS growth_index,
               d.routed_at
        FROM document d
        JOIN employee_master em ON em.employee_uuid = d.employee_uuid
        JOIN tenant t ON t.tenant_id = em.tenant_id
        LEFT JOIN career_event ce ON ce.doc_uuid = d.document_id
        WHERE d.employee_uuid IN (
            SELECT employee_uuid FROM employee_master WHERE employee_user_id=$1
          )
          AND d.pipeline_status = 'ROUTED'
          AND d.doc_type IN ('SALARY_SLIP','INCREMENT_LETTER','PROMOTION_LETTER')
          AND d.doc_period IS NOT NULL
          AND d.is_deleted = FALSE
        ORDER BY d.doc_period ASC
        """,
        current.user_id,
    )

    # Normalise: baseline index 100 from first point
    growth_data = []
    baseline = None
    for i, row in enumerate(growth_rows):
        raw_idx = row["growth_index"] or (100 + i * 5)  # fallback if LLM didn't produce index
        if baseline is None:
            baseline = raw_idx
        idx = round((raw_idx / baseline) * 100) if baseline else 100
        growth_data.append({
            "period": row["doc_period"],
            "index": idx,
            "employer_id": str(row["employer_id"]),
            "employer_name": row["employer_name"],
            "doc_type": row["doc_type"],
            "note": row["insight_text"] or "",
        })

    employers = [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "role": r["role"] or "",
            "from": r["from"].isoformat() if r["from"] else None,
            "to": r["to"].isoformat() if r["to"] else None,
        }
        for r in employer_rows
    ]

    events = [
        {
            "id": str(i),
            "type": _event_type_to_ui(r["event_type"]),
            "label": _event_label(r["event_type"], r["employer_name"], r["designation"]),
            "employer_id": str(r["employee_uuid"]),
            "at": r["event_date"].isoformat() if r["event_date"] else None,
        }
        for i, r in enumerate(event_rows)
    ]

    return {
        "growth_data": growth_data,
        "employers": employers,
        "events": events,
    }


def _event_type_to_ui(event_type: str) -> str:
    return {
        "JOINED": "join",
        "EXITED": "leave",
        "PROMOTED": "promotion",
        "INCREMENT": "increment",
    }.get(event_type, "join")


def _event_label(event_type: str, employer_name: str, designation: Optional[str]) -> str:
    labels = {
        "JOINED": f"Joined {employer_name}",
        "EXITED": f"Left {employer_name}",
        "PROMOTED": f"Promoted to {designation or 'Senior Role'} at {employer_name}",
        "INCREMENT": f"Salary increment at {employer_name}",
    }
    return labels.get(event_type, f"{event_type} at {employer_name}")


# ── Share ─────────────────────────────────────────────────────────────────────

class CreateShareIn(BaseModel):
    document_ids: list[str] = Field(..., min_length=1, max_length=10)
    expires_hours: int = Field(72, ge=1, le=720)
    max_views: Optional[int] = Field(3, ge=1, le=50)
    recipient_label: Optional[str] = Field(None, max_length=120)
    otp_required: bool = False
    recipient_email: Optional[str] = None


@router.post("/share", status_code=status.HTTP_201_CREATED)
async def create_share(
    body: CreateShareIn,
    request: Request,
    db: DbConn,
    current: Employee,
):
    svc = _share(request, db)
    try:
        result = await svc.create(
            employee_user_id=current.user_id,
            document_ids=body.document_ids,
            expires_hours=body.expires_hours,
            max_views=body.max_views,
            recipient_label=body.recipient_label,
            otp_required=body.otp_required,
            recipient_email=body.recipient_email,
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return result


@router.get("/share")
async def list_shares(request: Request, db: DbConn, current: Employee):
    svc = _share(request, db)
    shares = await svc.list_shares(current.user_id)
    return {"shares": shares}


@router.delete("/share/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share(share_id: str, request: Request, db: DbConn, current: Employee):
    svc = _share(request, db)
    try:
        await svc.revoke(share_id, current.user_id)
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PranaError.NOT_FOUND)


# ── Activity feed ─────────────────────────────────────────────────────────────

@router.get("/activity")
async def get_activity(
    request: Request,
    db: DbConn,
    current: Employee,
    limit: int = 50,
):
    """
    Returns document access log + pipeline push events for the authenticated employee.
    Never surfaces raw salary figures — doc_type and metadata only.
    """
    access_rows = await db.fetch(
        """
        SELECT dal.access_id, dal.document_id, d.doc_type, d.doc_period,
               t.tenant_name AS employer_name,
               dal.access_type, dal.accessed_at,
               dal.share_token_id
        FROM document_access_log dal
        JOIN document d ON d.document_id = dal.document_id
        JOIN tenant t ON t.tenant_id = dal.tenant_id
        WHERE dal.employee_user_id = $1
        ORDER BY dal.accessed_at DESC
        LIMIT $2
        """,
        current.user_id, min(limit, 100),
    )

    pipeline_rows = await db.fetch(
        """
        SELECT d.document_id, d.doc_type, d.doc_period,
               t.tenant_name AS employer_name,
               d.pipeline_status, d.resolution_method, d.resolution_confidence,
               d.pushed_at, d.routed_at
        FROM document d
        JOIN employee_master em ON em.employee_uuid = d.employee_uuid
        JOIN tenant t ON t.tenant_id = em.tenant_id
        WHERE em.employee_user_id = $1
        ORDER BY d.pushed_at DESC
        LIMIT $2
        """,
        current.user_id, min(limit, 100),
    )

    return {
        "access_log": [
            {
                "id": str(r["access_id"]),
                "document_id": str(r["document_id"]),
                "doc_type": r["doc_type"],
                "doc_period": r["doc_period"],
                "employer_name": r["employer_name"],
                "access_type": r["access_type"],
                "accessed_at": r["accessed_at"].isoformat() if r["accessed_at"] else None,
                "via_share": r["share_token_id"] is not None,
            }
            for r in access_rows
        ],
        "pipeline_pushes": [
            {
                "document_id": str(r["document_id"]),
                "doc_type": r["doc_type"],
                "doc_period": r["doc_period"],
                "employer_name": r["employer_name"],
                "pipeline_status": r["pipeline_status"],
                "resolution_method": r["resolution_method"],
                "pushed_at": r["pushed_at"].isoformat() if r["pushed_at"] else None,
                "routed_at": r["routed_at"].isoformat() if r["routed_at"] else None,
            }
            for r in pipeline_rows
        ],
    }


# ── Document requests ─────────────────────────────────────────────────────────

class CreateDocRequestIn(BaseModel):
    tenant_id: str
    doc_type: str
    period: Optional[str] = None
    note: Optional[str] = Field(None, max_length=500)


@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def request_document(
    body: CreateDocRequestIn,
    request: Request,
    db: DbConn,
    current: Employee,
):
    svc = _vault(request, db, current)
    try:
        doc_request_id = await svc.request_document(
            employee_user_id=current.user_id,
            tenant_id=body.tenant_id,  # sec03-cross-tenant-ok: employee selects which employer to request from; service validates employment via DB JOIN
            doc_type=body.doc_type,
            period=body.period,
            note=body.note,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return {"doc_request_id": doc_request_id}


@router.get("/requests")
async def list_requests(request: Request, db: DbConn, current: Employee):
    svc = _vault(request, db, current)
    requests = await svc.list_requests(current.user_id)
    return {"requests": requests}


# ── Watermark ─────────────────────────────────────────────────────────────────

def _apply_watermark(pdf_bytes: bytes, employee_user_id: str) -> bytes:
    """
    Stamps 'PRANA - Confidential - {masked_id}' diagonally on every page.

    Primary: PyMuPDF (fitz) — fast, vector text, preserves PDF structure.
    Fallback: reportlab overlay — pure-Python, always available on prana-api.

    NEVER returns unwatermarked bytes for a valid PDF.
    Raises RuntimeError if both engines fail — callers must surface this as 500
    rather than silently serve an unwatermarked document (compliance violation).
    """
    if pdf_bytes[:4] != b"%PDF":
        return pdf_bytes

    masked = employee_user_id[:8] + "..."
    wm_text = f"PRANA - Confidential - {masked}"

    # ── Primary: PyMuPDF ──────────────────────────────────────────────────────
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            rect = page.rect
            page.insert_text(
                (rect.width * 0.1, rect.height * 0.5),
                wm_text,
                fontsize=18,
                color=(0.8, 0.8, 0.8),
                rotate=45,
            )
        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()
    except ImportError:
        pass  # fall through to reportlab

    # ── Fallback: reportlab overlay ───────────────────────────────────────────
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as rl_canvas
        from pypdf import PdfReader, PdfWriter

        # Build a one-page watermark PDF in memory
        wm_buffer = io.BytesIO()
        c = rl_canvas.Canvas(wm_buffer, pagesize=A4)
        width, height = A4
        c.setFont("Helvetica", 40)
        c.setFillColorRGB(0.8, 0.8, 0.8, alpha=0.4)
        c.saveState()
        c.translate(width / 2, height / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, wm_text)
        c.restoreState()
        c.save()
        wm_buffer.seek(0)

        # Merge watermark overlay onto every page of the original PDF
        reader = PdfReader(io.BytesIO(pdf_bytes))
        wm_reader = PdfReader(wm_buffer)
        wm_page = wm_reader.pages[0]
        writer = PdfWriter()
        for page in reader.pages:
            page.merge_page(wm_page)
            writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception as exc:
        # Both engines failed — must NOT serve unwatermarked document
        raise RuntimeError(
            f"Watermark engine unavailable — refusing to serve unwatermarked document: {exc}"
        ) from exc
