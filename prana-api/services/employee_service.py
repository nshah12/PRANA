"""
Employee master CRUD.
pan_token computed here → NIK dropped immediately → never stored anywhere.
"""
import uuid
from datetime import date, timedelta
from typing import Optional

import asyncpg

from services.encryption_service import compute_pan_token, encrypt_nik_fpe, generate_dek, KMSService


class EmployeeService:

    def __init__(self, db: asyncpg.Connection, kms: KMSService, platform_hmac_secret: str):
        self._db  = db
        self._kms = kms
        self._hmac_secret = platform_hmac_secret

    async def create(
        self,
        *,
        nik: str,              # cleartext PAN/NIK — used once, dropped after this call
        tenant_id: str,
        emp_id_org: Optional[str],
        full_name: str,
        designation: Optional[str],
        department: Optional[str],
        grade: Optional[str],
        location: Optional[str],
        employment_type: str,
        cost_centre: Optional[str],
        uan: Optional[str],
        doj: date,
        created_by: str,
        kek_arn: str,
    ) -> dict:
        """
        Create or upsert employee_user + employee_master for one employee.
        NIK is processed here and immediately discarded — never written to any table.
        """
        pan_token = compute_pan_token(nik, self._hmac_secret)

        # DEK per employee — wrapped with tenant KEK
        dek = generate_dek()
        enc_dek = self._kms.wrap_dek(dek, kek_arn)
        enc_pan = encrypt_nik_fpe(nik, dek)

        # Drop nik and dek from memory as early as possible
        del nik, dek

        async with self._db.transaction():
            # Upsert employee_user (same person may already exist from another tenant)
            eu_row = await self._db.fetchrow(
                "SELECT employee_user_id FROM employee_user WHERE pan_token=$1", pan_token
            )
            if eu_row:
                employee_user_id = str(eu_row["employee_user_id"])
            else:
                employee_user_id = str(uuid.uuid4())
                await self._db.execute(
                    """
                    INSERT INTO employee_user
                      (employee_user_id, pan_token, enc_pan, enc_dek, status)
                    VALUES ($1,$2,$3,$4,'PENDING_ACTIVATION')
                    """,
                    employee_user_id, pan_token, enc_pan, enc_dek,
                )

            # Create employee_master for this tenant
            employee_uuid = str(uuid.uuid4())
            await self._db.execute(
                """
                INSERT INTO employee_master
                  (employee_uuid, employee_user_id, tenant_id, pan_token, enc_pan, enc_dek,
                   emp_id_org, full_name, designation, department, grade, location,
                   employment_type, cost_centre, uan, doj, created_by)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
                """,
                employee_uuid, employee_user_id, tenant_id, pan_token, enc_pan, enc_dek,
                emp_id_org, full_name, designation, department, grade, location,
                employment_type, cost_centre, uan, doj, created_by,
            )

            await self._db.execute(
                """
                INSERT INTO career_event
                  (pan_token, employee_user_id, employee_uuid, tenant_id, event_type, event_date, event_title, verified)
                VALUES ($1,$2,$3,$4,'JOINED',$5,$6,TRUE)
                """,
                pan_token, employee_user_id, employee_uuid, tenant_id, doj,
                f"Joined {await self._tenant_name(tenant_id)}",
            )

        return {
            "employee_uuid": employee_uuid,
            "employee_user_id": employee_user_id,
            "pan_token": pan_token,
        }

    async def mark_alumni(
        self,
        employee_uuid: str,
        dol: date,
        tenant_id: str,
        push_window_months: int,
        changed_by: str,
    ) -> None:
        """Set dol, compute push_window_expires, status → ALUMNI."""
        push_expires = dol + timedelta(days=push_window_months * 30)

        async with self._db.transaction():
            row = await self._db.fetchrow(
                "SELECT pan_token, employee_user_id, status FROM employee_master WHERE employee_uuid=$1 AND tenant_id=$2",
                employee_uuid, tenant_id,
            )
            if not row:
                raise ValueError("EMPLOYEE_NOT_FOUND")
            if row["status"] != "ACTIVE":
                raise ValueError("NOT_ACTIVE")

            await self._db.execute(
                """
                UPDATE employee_master
                SET dol=$2, push_window_expires=$3, status='ALUMNI', updated_at=NOW()
                WHERE employee_uuid=$1
                """,
                employee_uuid, dol, push_expires,
            )
            await self._db.execute(
                """
                INSERT INTO career_event
                  (pan_token, employee_user_id, employee_uuid, tenant_id, event_type, event_date, event_title, verified)
                VALUES ($1,$2,$3,$4,'EXITED',$5,'Resigned / Separated',TRUE)
                """,
                row["pan_token"], row["employee_user_id"], employee_uuid, tenant_id, dol,
            )
            await self._db.execute(
                """
                INSERT INTO employee_master_history
                  (employee_uuid, tenant_id, field_name, old_value, new_value, changed_by, changed_by_role, change_source)
                VALUES ($1,$2,'status','ACTIVE','ALUMNI',$3,'oa_admin','MANUAL')
                """,
                employee_uuid, tenant_id, changed_by,
            )

    async def update(
        self,
        employee_uuid: str,
        tenant_id: str,
        fields: dict,
        changed_by: str,
        changed_by_role: str,
        elevation_id: Optional[str] = None,
    ) -> None:
        """Update mutable profile fields. Every change logged to employee_master_history."""
        allowed = {"designation","department","grade","location","employment_type","cost_centre","reporting_manager"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return

        current = await self._db.fetchrow(
            f"SELECT {','.join(updates.keys())} FROM employee_master WHERE employee_uuid=$1 AND tenant_id=$2",
            employee_uuid, tenant_id,
        )
        if not current:
            raise ValueError("EMPLOYEE_NOT_FOUND")

        async with self._db.transaction():
            set_clause = ", ".join(f"{k}=${i+2}" for i, k in enumerate(updates))
            await self._db.execute(
                f"UPDATE employee_master SET {set_clause}, updated_at=NOW() WHERE employee_uuid=$1",
                employee_uuid, *updates.values(),
            )
            history_rows = [
                (employee_uuid, tenant_id, k, str(current[k]), str(v), changed_by, changed_by_role, elevation_id)
                for k, v in updates.items()
            ]
            await self._db.executemany(
                """
                INSERT INTO employee_master_history
                  (employee_uuid, tenant_id, field_name, old_value, new_value,
                   changed_by, changed_by_role, elevation_id)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                """,
                history_rows,
            )

    async def search(
        self,
        tenant_id: str,
        *,
        emp_id_org: Optional[str] = None,
        name: Optional[str] = None,
        pan_token: Optional[str] = None,
        active_only: bool = True,
        limit: int = 50,
    ) -> list[dict]:
        conditions = ["tenant_id=$1"]
        params: list = [tenant_id]
        i = 2

        if active_only:
            conditions.append("dol IS NULL")

        if pan_token:
            conditions.append(f"pan_token=${i}"); params.append(pan_token); i += 1
        elif emp_id_org:
            conditions.append(f"emp_id_org=${i}"); params.append(emp_id_org); i += 1
        elif name:
            conditions.append(f"full_name ILIKE ${i}"); params.append(f"%{name}%"); i += 1

        where = " AND ".join(conditions)
        rows = await self._db.fetch(
            f"""
            SELECT employee_uuid, employee_user_id, pan_token, emp_id_org,
                   full_name, designation, department, grade, location,
                   doj, dol, status, vault_completeness
            FROM employee_master WHERE {where}
            ORDER BY full_name LIMIT {limit}
            """,
            *params,
        )
        return [dict(r) for r in rows]

    async def get(self, employee_uuid: str, tenant_id: str) -> Optional[dict]:
        row = await self._db.fetchrow(
            """
            SELECT employee_uuid, employee_user_id, pan_token, emp_id_org,
                   full_name, designation, department, grade, location, uan,
                   doj, dol, push_window_expires, status, vault_completeness,
                   employment_type, cost_centre, created_at, updated_at
            FROM employee_master WHERE employee_uuid=$1 AND tenant_id=$2
            """,
            employee_uuid, tenant_id,
        )
        return dict(row) if row else None

    async def _tenant_name(self, tenant_id: str) -> str:
        row = await self._db.fetchrow("SELECT tenant_name FROM tenant WHERE tenant_id=$1", tenant_id)
        return row["tenant_name"] if row else "Unknown"
