"""
AlumniService — alumni network: per-org consent + contact detail sharing.

Consent model (uses employee_consent with tenant_id):
  tenant_id IS NULL  → global consent (document_processing, insight_generation)
  tenant_id NOT NULL → per-org consent (alumni_visibility for a specific past employer)

When employee grants alumni_visibility for tenant T:
  CHRO of T sees: full_name, designation, dept, grade, city, DOJ, DOL
  + mobile (if share_mobile=TRUE) + email (if share_email=TRUE)
  CHRO downloads CSV and contacts employee directly via call/email/WhatsApp.
  In-app outreach messages are supplementary.

Withdrawal: immediate — next CHRO query excludes the employee.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)

_MIN_EXIT_DAYS = 30  # employee must have left ≥ 30 days ago to appear to CHRO


class AlumniService:
    def __init__(self, db, kafka=None, config: dict | None = None):
        self._db     = db
        self._kafka  = kafka
        self._config = config or {}

    # ── Employee: global alumni consent (applies across all past employers) ──

    async def set_alumni_consent(self, employee_user_id: str, grant: bool) -> dict[str, Any]:
        await self._db.execute(
            """
            INSERT INTO employee_consent
              (employee_user_id, tenant_id, purpose, is_active, consent_version, updated_at)
            VALUES ($1, NULL, 'alumni_visibility', $2, '1.0', NOW())
            ON CONFLICT (employee_user_id, COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid), purpose)
            DO UPDATE SET is_active = EXCLUDED.is_active, updated_at = NOW()
            """,
            employee_user_id, grant,
        )
        if not grant:
            await self._db.execute(
                """
                UPDATE alumni_outreach SET status = 'OPTED_OUT', updated_at = NOW()
                WHERE employee_user_id = $1 AND status NOT IN ('OPTED_OUT', 'REPLIED')
                """,
                employee_user_id,
            )
        return {"alumni_visibility_consent": grant}

    async def get_alumni_consent(self, employee_user_id: str) -> dict[str, Any]:
        row = await self._db.fetchrow(
            """
            SELECT is_active FROM employee_consent
            WHERE employee_user_id = $1 AND tenant_id IS NULL AND purpose = 'alumni_visibility'
            """,
            employee_user_id,
        )
        return {"alumni_visibility_consent": bool(row["is_active"]) if row else False}

    # ── Employee: per-org consent ────────────────────────────────────────────

    async def list_past_employers(self, employee_user_id: str) -> dict[str, Any]:
        """
        All past employers with current alumni consent status for each.
        Drives the per-org consent toggle list in mobile app.
        """
        rows = await self._db.fetch(
            """
            SELECT em.tenant_id,
                   em.employee_uuid,
                   t.name           AS company_name,
                   em.designation,
                   em.department,
                   em.doj,
                   em.dol,
                   COALESCE(ec.is_active,    FALSE) AS granted,
                   COALESCE(ec.share_mobile, TRUE)  AS share_mobile,
                   COALESCE(ec.share_email,  TRUE)  AS share_email,
                   ec.consented_at  AS granted_at,
                   ec.updated_at
            FROM   employee_master em
            JOIN   tenant t ON t.tenant_id = em.tenant_id
            LEFT JOIN employee_consent ec
                   ON ec.employee_user_id = em.employee_user_id
                  AND ec.tenant_id        = em.tenant_id
                  AND ec.purpose          = 'alumni_visibility'
            WHERE  em.employee_user_id = $1
              AND  em.dol IS NOT NULL
              AND  em.is_deleted = FALSE
            ORDER  BY em.dol DESC
            """,
            employee_user_id,
        )
        return {"items": [_serialize_past_employer(r) for r in rows]}

    async def set_per_org_consent(
        self,
        employee_user_id: str,
        tenant_id: str,
        granted: bool,
        share_mobile: bool = True,
        share_email: bool  = True,
    ) -> dict[str, Any]:
        """
        Grant or withdraw alumni_visibility consent for one specific past employer.
        Uses UPSERT on employee_consent (tenant_id scoped) — idempotent.
        """
        exists = await self._db.fetchval(
            """
            SELECT 1 FROM employee_master
            WHERE employee_user_id = $1 AND tenant_id = $2
              AND dol IS NOT NULL AND is_deleted = FALSE
            """,
            employee_user_id, tenant_id,
        )
        if not exists:
            return {"error": "NOT_A_PAST_EMPLOYER"}

        await self._db.execute(
            """
            INSERT INTO employee_consent
              (employee_user_id, tenant_id, purpose, is_active,
               share_mobile, share_email, consent_version, updated_at)
            VALUES ($1, $2, 'alumni_visibility', $3, $4, $5, '1.0', NOW())
            ON CONFLICT ON CONSTRAINT uq_consent_per_org
            DO UPDATE SET
              is_active    = EXCLUDED.is_active,
              share_mobile = EXCLUDED.share_mobile,
              share_email  = EXCLUDED.share_email,
              updated_at   = NOW()
            """,
            employee_user_id, tenant_id, granted, share_mobile, share_email,
        )
        return {
            "tenant_id":    tenant_id,
            "granted":      granted,
            "share_mobile": share_mobile,
            "share_email":  share_email,
        }

    # ── Employee: inbox ──────────────────────────────────────────────────────

    async def list_employee_outreach(
        self,
        employee_user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        rows = await self._db.fetch(
            """
            SELECT ao.outreach_id, t.name AS company_name,
                   ao.subject, ao.body_text, ao.status,
                   ao.sent_at, ao.read_at, ao.reply_body, ao.replied_at
            FROM   alumni_outreach ao
            JOIN   tenant t ON t.tenant_id = ao.tenant_id
            WHERE  ao.employee_user_id = $1
            ORDER  BY ao.sent_at DESC
            LIMIT  $2 OFFSET $3
            """,
            employee_user_id, limit, offset,
        )
        total = await self._db.fetchval(
            "SELECT COUNT(*) FROM alumni_outreach WHERE employee_user_id = $1",
            employee_user_id,
        )
        return {
            "items": [_serialize_outreach_for_employee(r) for r in rows],
            "total": int(total or 0),
        }

    async def mark_outreach_read(self, employee_user_id: str, outreach_id: str) -> None:
        await self._db.execute(
            """
            UPDATE alumni_outreach
            SET status = 'READ', read_at = NOW()
            WHERE outreach_id = $1 AND employee_user_id = $2 AND status = 'SENT'
            """,
            outreach_id, employee_user_id,
        )

    async def reply_to_outreach(
        self,
        employee_user_id: str,
        outreach_id: str,
        reply_body: str,
    ) -> None:
        """
        Employee sends a single reply to a CHRO outreach message.
        Idempotent — once replied, subsequent calls are silently ignored.
        """
        await self._db.execute(
            """
            UPDATE alumni_outreach
            SET status = 'REPLIED', reply_body = $3, replied_at = NOW(),
                read_at = COALESCE(read_at, NOW())
            WHERE outreach_id     = $1
              AND employee_user_id = $2
              AND replied_at IS NULL
            """,
            outreach_id, employee_user_id, reply_body,
        )

    # ── CHRO: alumni list with contact details ───────────────────────────────

    async def list_alumni(
        self,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
        city: str | None = None,
        designation_contains: str | None = None,
        min_tenure_months: int | None = None,
    ) -> dict[str, Any]:
        """
        Consented alumni for this tenant. Returns full contact details where shared.
        Filtered by employee_consent WHERE tenant_id = this tenant AND purpose = alumni_visibility.
        """
        city_pat        = f"%{city}%"                 if city                else None
        desig_pat       = f"%{designation_contains}%" if designation_contains else None
        min_tenure_days = min_tenure_months * 30       if min_tenure_months   else None

        rows = await self._db.fetch(
            """
            SELECT em.employee_uuid,
                   em.employee_user_id,
                   em.full_name,
                   em.designation,
                   em.department,
                   em.grade,
                   em.location,
                   em.doj,
                   em.dol,
                   CASE WHEN ec.share_mobile THEN eu.mobile ELSE NULL END AS mobile,
                   CASE WHEN ec.share_email  THEN eu.email  ELSE NULL END AS email,
                   (SELECT status  FROM alumni_outreach ao
                    WHERE ao.employee_user_id = em.employee_user_id
                      AND ao.tenant_id = $1
                    ORDER BY ao.sent_at DESC LIMIT 1) AS last_outreach_status,
                   (SELECT sent_at FROM alumni_outreach ao
                    WHERE ao.employee_user_id = em.employee_user_id
                      AND ao.tenant_id = $1
                    ORDER BY ao.sent_at DESC LIMIT 1) AS last_outreach_at
            FROM   employee_master em
            JOIN   employee_consent ec
                   ON ec.employee_user_id = em.employee_user_id
                  AND ec.tenant_id        = $1
                  AND ec.purpose          = 'alumni_visibility'
            JOIN   employee_user eu ON eu.employee_user_id = em.employee_user_id
            WHERE  em.tenant_id    = $1
              AND  em.dol IS NOT NULL
              AND  em.dol <= (NOW() - ($2 * INTERVAL '1 day'))
              AND  ec.is_active    = TRUE
              AND  em.is_deleted   = FALSE
              AND  ($3::text IS NULL OR LOWER(em.location)    LIKE LOWER($3))
              AND  ($4::text IS NULL OR LOWER(em.designation) LIKE LOWER($4))
              AND  ($5::int  IS NULL OR (em.dol - em.doj) >= ($5 * INTERVAL '1 day'))
            ORDER  BY em.dol DESC
            LIMIT  $6 OFFSET $7
            """,
            tenant_id, _MIN_EXIT_DAYS, city_pat, desig_pat, min_tenure_days, limit, offset,
        )
        total = await self._db.fetchval(
            """
            SELECT COUNT(*)
            FROM   employee_master em
            JOIN   employee_consent ec
                   ON ec.employee_user_id = em.employee_user_id
                  AND ec.tenant_id        = $1
                  AND ec.purpose          = 'alumni_visibility'
            WHERE  em.tenant_id  = $1
              AND  em.dol IS NOT NULL
              AND  em.dol <= (NOW() - ($2 * INTERVAL '1 day'))
              AND  ec.is_active  = TRUE
              AND  em.is_deleted = FALSE
              AND  ($3::text IS NULL OR LOWER(em.location)    LIKE LOWER($3))
              AND  ($4::text IS NULL OR LOWER(em.designation) LIKE LOWER($4))
              AND  ($5::int  IS NULL OR (em.dol - em.doj) >= ($5 * INTERVAL '1 day'))
            """,
            tenant_id, _MIN_EXIT_DAYS, city_pat, desig_pat, min_tenure_days,
        )
        return {
            "items": [_serialize_alumni_for_chro(r) for r in rows],
            "total": int(total or 0),
        }

    async def download_alumni_csv(
        self,
        tenant_id: str,
        city: str | None = None,
        designation_contains: str | None = None,
        min_tenure_months: int | None = None,
    ) -> str:
        city_pat        = f"%{city}%"                 if city                else None
        desig_pat       = f"%{designation_contains}%" if designation_contains else None
        min_tenure_days = min_tenure_months * 30       if min_tenure_months   else None

        rows = await self._db.fetch(
            """
            SELECT em.full_name, em.designation, em.department, em.grade,
                   em.location, em.doj, em.dol,
                   CASE WHEN ec.share_mobile THEN eu.mobile ELSE NULL END AS mobile,
                   CASE WHEN ec.share_email  THEN eu.email  ELSE NULL END AS email
            FROM   employee_master em
            JOIN   employee_consent ec
                   ON ec.employee_user_id = em.employee_user_id
                  AND ec.tenant_id        = $1
                  AND ec.purpose          = 'alumni_visibility'
            JOIN   employee_user eu ON eu.employee_user_id = em.employee_user_id
            WHERE  em.tenant_id  = $1
              AND  em.dol IS NOT NULL
              AND  em.dol <= (NOW() - ($2 * INTERVAL '1 day'))
              AND  ec.is_active  = TRUE
              AND  em.is_deleted = FALSE
              AND  ($3::text IS NULL OR LOWER(em.location)    LIKE LOWER($3))
              AND  ($4::text IS NULL OR LOWER(em.designation) LIKE LOWER($4))
              AND  ($5::int  IS NULL OR (em.dol - em.doj) >= ($5 * INTERVAL '1 day'))
            ORDER  BY em.dol DESC
            """,
            tenant_id, _MIN_EXIT_DAYS, city_pat, desig_pat, min_tenure_days,
        )
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "Full Name", "Designation", "Department", "Grade", "City",
            "Date of Joining", "Date of Leaving", "Mobile", "Email",
            "Tenure", "Time Since Exit",
        ])
        for r in rows:
            writer.writerow([
                r["full_name"],
                r["designation"] or "",
                r["department"]  or "",
                r["grade"]       or "",
                r["location"]    or "",
                r["doj"].isoformat() if r["doj"] else "",
                r["dol"].isoformat() if r["dol"] else "",
                r["mobile"] or "Not shared",
                r["email"]  or "Not shared",
                _tenure_band(r["doj"], r["dol"]) if r["doj"] and r["dol"] else "",
                _time_since_exit(r["dol"]) if r["dol"] else "",
            ])
        return buf.getvalue()

    # ── CHRO: in-app outreach ────────────────────────────────────────────────

    async def send_outreach(
        self,
        tenant_id: str,
        oa_user_id: str,
        employee_uuid: str,
        subject: str,
        body_text: str,
    ) -> dict[str, Any]:
        max_per_month = int(self._config.get("outreach_max_per_month", 3))

        row = await self._db.fetchrow(
            """
            SELECT em.employee_user_id, em.dol, ec.is_active AS consent_active
            FROM   employee_master em
            JOIN   employee_consent ec
                   ON ec.employee_user_id = em.employee_user_id
                  AND ec.tenant_id        = $2
                  AND ec.purpose          = 'alumni_visibility'
            WHERE  em.employee_uuid = $1 AND em.tenant_id = $2
            """,
            employee_uuid, tenant_id,
        )
        if not row:
            return {"error": "ALUMNI_NOT_FOUND"}
        if not row["consent_active"]:
            return {"error": "ALUMNI_NO_CONSENT"}
        if not row["dol"] or row["dol"] > date.today() - timedelta(days=_MIN_EXIT_DAYS):
            return {"error": "EMPLOYEE_STILL_ACTIVE"}

        employee_user_id = str(row["employee_user_id"])

        recent_count = await self._db.fetchval(
            """
            SELECT COUNT(*) FROM alumni_outreach
            WHERE  tenant_id        = $1
              AND  employee_user_id = $2
              AND  sent_at         >= NOW() - INTERVAL '30 days'
              AND  status          != 'OPTED_OUT'
            """,
            tenant_id, employee_user_id,
        )
        try:
            count = int(recent_count or 0)
        except (TypeError, ValueError):
            count = 0
        if count >= max_per_month:
            return {"error": "OUTREACH_RATE_LIMIT", "limit": max_per_month}

        outreach_id = await self._db.fetchval(
            """
            INSERT INTO alumni_outreach
              (tenant_id, employee_uuid, employee_user_id, sent_by_oa_user, subject, body_text)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING outreach_id
            """,
            tenant_id, employee_uuid, employee_user_id, oa_user_id, subject, body_text,
        )

        if self._kafka:
            await self._kafka.notify_bell({
                "event_type":   "ALUMNI_OUTREACH_RECEIVED",
                "recipient_id": employee_user_id,
                "outreach_id":  str(outreach_id),
                "subject":      subject,
            })
            await self._kafka.notify_email({
                "event_type":   "ALUMNI_OUTREACH_RECEIVED",
                "recipient_id": employee_user_id,
                "outreach_id":  str(outreach_id),
                "subject":      subject,
            })
        return {"outreach_id": str(outreach_id), "status": "SENT"}

    async def list_sent_outreach(
        self,
        tenant_id: str,
        employee_uuid: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        rows = await self._db.fetch(
            """
            SELECT ao.outreach_id, ao.employee_uuid, em.full_name,
                   em.designation, ao.subject, ao.status,
                   ao.sent_at, ao.read_at, ao.replied_at
            FROM   alumni_outreach ao
            JOIN   employee_master em USING (employee_uuid)
            WHERE  ao.tenant_id = $1
              AND  ($2::uuid IS NULL OR ao.employee_uuid = $2::uuid)
            ORDER  BY ao.sent_at DESC
            LIMIT  $3 OFFSET $4
            """,
            tenant_id, employee_uuid, limit, offset,
        )
        total = await self._db.fetchval(
            """
            SELECT COUNT(*) FROM alumni_outreach ao
            WHERE ao.tenant_id = $1
              AND ($2::uuid IS NULL OR ao.employee_uuid = $2::uuid)
            """,
            tenant_id, employee_uuid,
        )
        return {
            "items": [_serialize_outreach_for_chro(r) for r in rows],
            "total": int(total or 0),
        }


# ── Serializers ───────────────────────────────────────────────────────────────

def _tenure_band(doj: date, dol: date) -> str:
    months = (dol - doj).days // 30
    if months < 12: return "< 1 year"
    if months < 24: return "1–2 years"
    if months < 48: return "2–4 years"
    if months < 84: return "4–7 years"
    return "7+ years"

def _time_since_exit(dol: date) -> str:
    months = (date.today() - dol).days // 30
    if months < 1:  return "< 1 month ago"
    if months < 12: return f"{months} month{'s' if months != 1 else ''} ago"
    years = months // 12
    return f"{years} year{'s' if years != 1 else ''} ago"

def _serialize_past_employer(r: Any) -> dict[str, Any]:
    return {
        "tenant_id":    str(r["tenant_id"]),
        "employee_uuid": str(r["employee_uuid"]),
        "company_name": r["company_name"],
        "designation":  r["designation"] or "",
        "department":   r["department"]  or "",
        "doj":          r["doj"].isoformat() if r["doj"] else None,
        "dol":          r["dol"].isoformat() if r["dol"] else None,
        "tenure_band":  _tenure_band(r["doj"], r["dol"]) if r["doj"] and r["dol"] else "",
        "granted":      bool(r["granted"]),
        "share_mobile": bool(r["share_mobile"]),
        "share_email":  bool(r["share_email"]),
    }

def _serialize_alumni_for_chro(r: Any) -> dict[str, Any]:
    return {
        "employee_uuid":        str(r["employee_uuid"]),
        "designation":          r["designation"] or "",
        "department":           r["department"]  or "",
        "grade":                r["grade"]       or "",
        "city":                 r["location"]    or "",
        "doj":                  r["doj"].isoformat() if r["doj"] else None,
        "dol":                  r["dol"].isoformat() if r["dol"] else None,
        "tenure_band":          _tenure_band(r["doj"], r["dol"]) if r["doj"] and r["dol"] else "",
        "time_since_exit":      _time_since_exit(r["dol"]) if r["dol"] else "",
        "last_outreach_status": r["last_outreach_status"],
        "last_outreach_at":     r["last_outreach_at"].isoformat() if r["last_outreach_at"] else None,
    }

def _serialize_outreach_for_employee(r: Any) -> dict[str, Any]:
    return {
        "outreach_id":  str(r["outreach_id"]),
        "company_name": r["company_name"],
        "subject":      r["subject"],
        "body_text":    r["body_text"],
        "status":       r["status"],
        "sent_at":      r["sent_at"].isoformat(),
        "read_at":      r["read_at"].isoformat()    if r["read_at"]    else None,
        "reply_body":   r["reply_body"]              if r["reply_body"] else None,
        "replied_at":   r["replied_at"].isoformat() if r["replied_at"] else None,
    }

def _serialize_outreach_for_chro(r: Any) -> dict[str, Any]:
    return {
        "outreach_id":   str(r["outreach_id"]),
        "employee_uuid": str(r["employee_uuid"]),
        "full_name":     r["full_name"],
        "designation":   r["designation"] or "",
        "subject":       r["subject"],
        "status":        r["status"],
        "sent_at":       r["sent_at"].isoformat(),
        "read_at":       r["read_at"].isoformat()    if r["read_at"]    else None,
        "replied_at":    r["replied_at"].isoformat() if r["replied_at"] else None,
    }
