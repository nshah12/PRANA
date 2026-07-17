"""
KMSRotationService — business logic behind workflows/security.py's KEK/HMAC
rotation activities (KMSKeyRotationWorkflow, HMACSecretRotationWorkflow).
Zero Temporal imports.

KEK rotation provisions a brand-new AWS KMS CMK for the tenant (not AWS's
native same-key annual rotation) and re-wraps every employee_master.enc_dek
under it, so a suspected-compromised key can actually be retired rather than
merely have its backing material rotated in place. kms_key_log.dek_rewrap_count
records how many rows were touched.

HMAC rotation swaps the platform-wide pan_token secret in Secrets Manager. It
does NOT eagerly re-hash employee_master.pan_token for every employee — the
pan_token_version registry in services/encryption_service.py re-derives each
employee's pan_token lazily on their next login. schema.sql's kms_key_log
comment ("4-8 hours for 1 crore employees, DEK rewrap is the bottleneck")
describes KEK rotation's dek_rewrap step, not this one.

KNOWN GAP: schema.sql documents "HMACSecretRotationWorkflow requires 2 DISTINCT
PA accounts (4-eyes enforcement)" but workflows/security.py's
HMACSecretRotationWorkflow (Pattern 4, perpetual, no signals) has no approval
gate at all. Adding one is a workflow-shape change (new signals +
wait_condition on 2 distinct approver IDs), not something this service can add
on its own — flagged here rather than silently half-built.
"""
import uuid


class KMSRotationService:

    def __init__(self, db, kms_service=None, secrets_client=None) -> None:
        self._db = db
        self._kms = kms_service
        self._secrets = secrets_client

    async def get_next_tenant_for_rotation(self, *, interval_days: int) -> dict:
        """Tenant most overdue for KEK rotation — never rotated sorts first,
        then oldest last-rotation. Empty dict if none are due yet."""
        row = await self._db.fetchrow(
            """
            SELECT t.tenant_id, t.kek_arn, MAX(k.checked_at) AS last_rotated_at
            FROM tenant t
            LEFT JOIN kms_key_log k
              ON k.tenant_id = t.tenant_id AND k.key_type = 'TENANT_KEK' AND k.event_type = 'ROTATED'
            WHERE t.status = 'ACTIVE'
            GROUP BY t.tenant_id, t.kek_arn
            HAVING MAX(k.checked_at) IS NULL
                OR MAX(k.checked_at) < NOW() - ($1 || ' days')::interval
            ORDER BY last_rotated_at ASC NULLS FIRST
            LIMIT 1
            """,
            interval_days,
        )
        return {"tenant_id": str(row["tenant_id"]), "kek_arn": row["kek_arn"]} if row else {}

    async def rotate_tenant_kek(self, *, tenant_id: str, kek_arn: str) -> None:
        rewrapped = 0
        new_kek_arn = kek_arn
        if self._kms:
            new_kek_arn = self._kms.create_tenant_kek(tenant_id)
            rows = await self._db.fetch(
                "SELECT employee_uuid, enc_dek FROM employee_master WHERE tenant_id=$1",
                uuid.UUID(tenant_id),
            )
            async with self._db.transaction():
                for row in rows:
                    dek = self._kms.unwrap_dek(row["enc_dek"], kek_arn)
                    new_enc_dek = self._kms.wrap_dek(dek, new_kek_arn)
                    await self._db.execute(
                        "UPDATE employee_master SET enc_dek=$1 WHERE employee_uuid=$2",
                        new_enc_dek, row["employee_uuid"],
                    )
                    rewrapped += 1
                await self._db.execute(
                    "UPDATE tenant SET kek_arn=$1 WHERE tenant_id=$2",
                    new_kek_arn, uuid.UUID(tenant_id),
                )

        await self._db.execute(
            """
            INSERT INTO kms_key_log
              (log_id, tenant_id, key_type, event_type, status, rotation_trigger, dek_rewrap_count, checked_at)
            VALUES ($1, $2, 'TENANT_KEK', 'ROTATED', 'ROTATED', 'SCHEDULED', $3, NOW())
            """,
            uuid.uuid4(), uuid.UUID(tenant_id), rewrapped,
        )

    async def rotate_hmac_secret(self, *, secret_id: str) -> None:
        if self._secrets:
            self._secrets.rotate_secret(SecretId=secret_id)
        await self._db.execute(
            """
            INSERT INTO kms_key_log
              (log_id, tenant_id, key_type, event_type, status, rotation_trigger, dek_rewrap_count, checked_at)
            VALUES ($1, NULL, 'PLATFORM_HMAC', 'ROTATED', 'ROTATED', 'SCHEDULED', 0, NOW())
            """,
            uuid.uuid4(),
        )
