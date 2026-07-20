"""
CSAMReportService — mandatory CSAM reporting to NCMEC CyberTipline, required
under the POCSO Act + IT Act whenever stage03_scan.py flags CSAM. Backs
workflows/security.py's CSAMReportingWorkflow activities. Zero Temporal imports.

Dev mode (ncmec_report_url unset): logs instead of calling out, matching the
sms_provider "dev" fallback in services/sms_service.py. Unlike SMS this is a
mandatory legal filing, not a UX nicety, so the dev path logs at CRITICAL —
never silently drop it during local runs that might paper over a bug.
"""
import logging
from typing import Optional

import httpx

from config import Settings

log = logging.getLogger(__name__)


class CSAMReportService:

    def __init__(self, db, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    async def report_to_ncmec(self, *, document_id: str, tenant_id: Optional[str]) -> dict:
        """Submits a CyberTipline report. Returns {"report_id": ...}."""
        url = self._settings.ncmec_report_url
        if not url:
            log.critical(
                "CSAMReportService: DEV MODE — would report document_id=%s tenant_id=%s "
                "to NCMEC CyberTipline (ncmec_report_url not configured)",
                document_id, tenant_id,
            )
            return {"report_id": "DEV-NOOP"}

        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=30, write=10, pool=10)) as client:
            resp = await client.post(
                url,
                json={"document_id": document_id, "tenant_id": tenant_id},
                headers={"Authorization": f"Bearer {self._settings.ncmec_api_key}"},
            )
        resp.raise_for_status()
        return {"report_id": resp.json().get("report_id", "")}
