"""
Tamper-evident audit ledger via Immudb.

Every audit_event row written by AuditConsumer is also dual-written here through
verified_set() — a cryptographically verifiable, append-only key-value store.
Unlike audit_event (an ordinary mutable YugabyteDB table — the REVOKE UPDATE/DELETE
in schema.sql is a comment, never executed as real DDL), Immudb makes tampering
with audit history detectable: verified_get() cryptographically proves a value
has not been altered since it was written.

Follows the same wrapper philosophy as KMSService (services/encryption_service.py):
plain class, primitive constructor args, real exceptions — never a silent placeholder.
"""
import json

from immudb import ImmudbClient


class ImmudbService:
    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self._client = ImmudbClient(f"{host}:{port}")
        self._database = database
        self._login(user, password)

    def _login(self, user: str, password: str) -> None:
        db = self._database.encode() if isinstance(self._database, str) else self._database
        try:
            self._client.login(user, password, database=db)
        except Exception:
            # First boot on a fresh immudb instance: the target database doesn't
            # exist yet. Log into defaultdb, create it, then retry.
            self._client.login(user, password)
            self._client.createDatabase(db)
            self._client.login(user, password, database=db)

    def verified_set(self, key: str, value: dict) -> dict:
        """Write value (JSON-serialized) under key, verified against saved state."""
        payload = json.dumps(value, default=str).encode()
        resp = self._client.verifiedSet(key.encode(), payload)
        return {"id": resp.id, "verified": resp.verified}

    def verified_get(self, key: str) -> dict | None:
        """Read value back and cryptographically verify it. None if the key is absent."""
        try:
            resp = self._client.verifiedGet(key.encode())
        except Exception as e:
            if hasattr(e, "details") and callable(e.details):
                details = e.details()
                if details and details.endswith("key not found"):
                    return None
            raise
        if resp is None:
            return None
        return {"value": json.loads(resp.value), "tx": resp.id, "verified": resp.verified}

    def close(self) -> None:
        try:
            self._client.logout()
        except Exception:
            pass
        self._client.shutdown()
