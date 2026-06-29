"""
Tenant lifecycle — PA-only operations.
Business logic here; Temporal workflow shell triggers async provisioning.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

import asyncpg

from services.encryption_service import hash_password, KMSService


class TenantService:

    def __init__(self, db: asyncpg.Connection, kms: KMSService):
        self._db = db
        self._kms = kms

    async def create_pending(
        self,
        *,
        tenant_name: str,
        domain: str,
        cin: Optional[str],
        gstin: Optional[str],
        nik_type: str,
        primary_state: str,
        home_region: str,
        self_upload_policy: str,
        storage_quota_gb: int,
        created_by_pa: str,
        # Legal identity
        brand_name: Optional[str] = None,
        entity_type: Optional[str] = None,
        pan_entity: Optional[str] = None,
        tan: Optional[str] = None,
        incorporation_date: Optional[str] = None,
        roc_jurisdiction: Optional[str] = None,
        # Addresses
        reg_address: Optional[dict] = None,
        corp_address: Optional[dict] = None,
        # Contacts
        primary_contact: Optional[dict] = None,
        first_oa_admin_email: Optional[str] = None,
        # DPDP
        dpo_name: Optional[str] = None,
        dpo_email: Optional[str] = None,
        grievance_officer_name: Optional[str] = None,
        grievance_officer_email: Optional[str] = None,
        dpa_accepted_at: Optional[datetime] = None,
        dpa_version: Optional[str] = "1.0",
        # Workforce
        industry: Optional[str] = None,
        employee_headcount_band: Optional[str] = None,
        payroll_frequency: Optional[str] = "MONTHLY",
        fiscal_year_start: Optional[str] = "APRIL",
        hrms_system: Optional[str] = None,
        document_ingestion_method: Optional[str] = "PORTAL_UPLOAD",
        additional_domains: Optional[list] = None,
        push_window_months: int = 6,
        default_language: str = "en",
        # Contract (PA-managed)
        sla_tier: str = "STANDARD",
        onboarding_tier: str = "ASSISTED",
        contract_type: str = "ANNUAL",
        account_manager: Optional[str] = None,
    ) -> dict:
        """
        Creates tenant row in PENDING status with full enterprise profile.
        DomainVerificationWorkflow is triggered by caller after this returns.
        home_region is set here and is IMMUTABLE afterwards.
        """
        import json
        tenant_id = str(uuid.uuid4())

        # DEV: placeholder KEK ARN — prod provisions via TenantProvisioningWorkflow
        kek_arn = f"arn:aws:kms:ap-south-1:123456789012:key/dev-{tenant_id[:8]}"

        reg_address_json = json.dumps(reg_address) if reg_address else None
        corp_address_json = json.dumps(corp_address) if corp_address else None
        primary_contact_json = json.dumps(primary_contact) if primary_contact else None

        await self._db.execute(
            """
            INSERT INTO tenant (
              tenant_id, tenant_name, cin, gstin, domain, nik_type, kek_arn,
              primary_state, home_region, status, storage_quota_gb, self_upload_policy,
              push_window_months, default_language,
              brand_name, entity_type, pan_entity, tan, incorporation_date, roc_jurisdiction,
              reg_address, corp_address, primary_contact,
              dpo_name, dpo_email, grievance_officer_name, grievance_officer_email,
              dpa_accepted_at, dpa_version,
              industry, employee_headcount_band, payroll_frequency, fiscal_year_start,
              hrms_system, document_ingestion_method, additional_domains,
              sla_tier, onboarding_tier, contract_type, account_manager
            ) VALUES (
              $1,$2,$3,$4,$5,$6,$7,
              $8,$9,'PENDING',$10,$11,
              $12,$13,
              $14,$15,$16,$17,$18,$19,
              $20::jsonb,$21::jsonb,$22::jsonb,
              $23,$24,$25,$26,
              $27,$28,
              $29,$30,$31,$32,
              $33,$34,$35,
              $36,$37,$38,$39
            )
            """,
            tenant_id, tenant_name, cin, gstin, domain, nik_type, kek_arn,
            primary_state, home_region, storage_quota_gb, self_upload_policy,
            push_window_months, default_language,
            brand_name, entity_type, pan_entity, tan, incorporation_date, roc_jurisdiction,
            reg_address_json, corp_address_json, primary_contact_json,
            dpo_name, dpo_email, grievance_officer_name, grievance_officer_email,
            dpa_accepted_at, dpa_version,
            industry, employee_headcount_band, payroll_frequency, fiscal_year_start,
            hrms_system, document_ingestion_method, additional_domains,
            sla_tier, onboarding_tier, contract_type, account_manager,
        )

        await self._db.execute(
            """
            INSERT INTO audit_event (event_type, actor_type, actor_id, tenant_id, event_metadata, occurred_at)
            VALUES ('TENANT_PROVISIONED', 'PA', $1, $2, $3, NOW())
            """,
            created_by_pa, tenant_id,
            {"action": "CREATE_PENDING", "domain": domain},
        )

        return {"tenant_id": tenant_id, "status": "PENDING"}

    async def activate(self, tenant_id: str, first_oa_admin_email: str) -> dict:
        """
        Called by TenantProvisioningWorkflow after domain verification passes.
        Creates first OA-Admin account with force_reset=TRUE.
        """
        import secrets
        temp_password = secrets.token_urlsafe(16)

        async with self._db.transaction():
            await self._db.execute(
                "UPDATE tenant SET status='ACTIVE' WHERE tenant_id=$1",
                tenant_id,
            )
            oa_user_id = str(uuid.uuid4())
            await self._db.execute(
                """
                INSERT INTO oa_user
                  (oa_user_id, tenant_id, email, role, temp_password_hash, force_reset, status)
                VALUES ($1,$2,$3,'oa_admin',$4,TRUE,'ACTIVE')
                """,
                oa_user_id, tenant_id, first_oa_admin_email,
                hash_password(temp_password),
            )

        return {
            "tenant_id": tenant_id,
            "oa_admin_id": oa_user_id,
            "temp_password": temp_password,
        }

    async def suspend(self, tenant_id: str, reason: str, pa_id: str) -> None:
        await self._db.execute(
            "UPDATE tenant SET status='SUSPENDED' WHERE tenant_id=$1", tenant_id,
        )
        await self._db.execute(
            "INSERT INTO audit_event (event_type,actor_type,actor_id,tenant_id,event_metadata,occurred_at) "
            "VALUES ('TENANT_PROVISIONED','PA',$1,$2,$3,NOW())",
            pa_id, tenant_id, {"action": "SUSPEND", "reason": reason},
        )

    async def get(self, tenant_id: str) -> Optional[dict]:
        row = await self._db.fetchrow(
            """
            SELECT tenant_id, tenant_name, brand_name, domain, status, home_region,
                   primary_state, nik_type, storage_quota_gb, self_upload_policy,
                   push_window_months, default_language,
                   cin, gstin, pan_entity, tan, entity_type, incorporation_date, roc_jurisdiction,
                   reg_address, corp_address, primary_contact,
                   dpo_name, dpo_email, grievance_officer_name, grievance_officer_email,
                   dpa_accepted_at, dpa_version,
                   industry, employee_headcount_band, payroll_frequency, fiscal_year_start,
                   hrms_system, document_ingestion_method, additional_domains,
                   pf_registration, esic_registration,
                   logo_url, brand_colour, support_email,
                   sla_tier, onboarding_tier, contract_type, account_manager,
                   created_at
            FROM tenant WHERE tenant_id=$1
            """,
            tenant_id,
        )
        if not row:
            return None
        d = dict(row)
        # JSONB columns come back as dicts in asyncpg; ensure they're serialisable
        for col in ("reg_address", "corp_address", "primary_contact"):
            if d.get(col) and not isinstance(d[col], dict):
                import json
                d[col] = json.loads(d[col])
        return d

    async def update_profile(
        self,
        tenant_id: str,
        updated_by: str,
        **fields,
    ) -> None:
        """
        OA-Admin can update profile fields that don't affect data-residency or KEK.
        PA can update any field via the same method with actor_type='PA'.
        Immutable fields (home_region, kek_arn) are never in the allowed set.
        """
        import json

        OA_EDITABLE = {
            "brand_name", "primary_contact", "reg_address", "corp_address",
            "dpo_name", "dpo_email", "grievance_officer_name", "grievance_officer_email",
            "industry", "employee_headcount_band", "payroll_frequency", "fiscal_year_start",
            "hrms_system", "document_ingestion_method", "additional_domains",
            "pf_registration", "esic_registration",
            "logo_url", "brand_colour", "support_email", "default_language",
            "push_window_months", "self_upload_policy",
        }

        updates = {k: v for k, v in fields.items() if k in OA_EDITABLE and v is not None}
        if not updates:
            return

        set_clauses = []
        values = []
        for i, (col, val) in enumerate(updates.items(), start=1):
            if col in ("reg_address", "corp_address", "primary_contact") and isinstance(val, dict):
                set_clauses.append(f"{col} = ${i}::jsonb")
                values.append(json.dumps(val))
            else:
                set_clauses.append(f"{col} = ${i}")
                values.append(val)

        values.append(tenant_id)
        sql = "UPDATE tenant SET " + ", ".join(set_clauses) + " WHERE tenant_id = $" + str(len(values))
        await self._db.execute(sql, *values)

        await self._db.execute(
            "INSERT INTO audit_event (event_type, actor_type, actor_id, tenant_id, event_metadata, occurred_at) "
            "VALUES ('TENANT_PROVISIONED', 'OA', $1, $2, $3, NOW())",
            updated_by, tenant_id,
            {"action": "PROFILE_UPDATE", "fields": list(updates.keys())},
        )

    async def list_all(self, status_filter: Optional[str] = None) -> list[dict]:
        if status_filter:
            rows = await self._db.fetch(
                """
                SELECT tenant_id, tenant_name, domain, status, home_region, primary_state,
                       cin, gstin, industry, employee_headcount_band, sla_tier, created_at
                FROM tenant WHERE status=$1 ORDER BY created_at DESC
                """,
                status_filter,
            )
        else:
            rows = await self._db.fetch(
                """
                SELECT tenant_id, tenant_name, domain, status, home_region, primary_state,
                       cin, gstin, industry, employee_headcount_band, sla_tier, created_at
                FROM tenant ORDER BY created_at DESC
                """
            )
        return [dict(r) for r in rows]

    async def update_config(
        self,
        tenant_id: str,
        key: str,
        value: str,
        updated_by_oa: str,
    ) -> None:
        """OA-Admin can override tenant-level config values."""
        await self._db.execute(
            """
            INSERT INTO tenant_config (tenant_id, config_key, config_value, updated_by, updated_at)
            VALUES ($1,$2,$3,$4,NOW())
            ON CONFLICT (tenant_id, config_key)
            DO UPDATE SET config_value=EXCLUDED.config_value,
                          updated_by=EXCLUDED.updated_by,
                          updated_at=NOW()
            """,
            tenant_id, key, value, updated_by_oa,
        )
