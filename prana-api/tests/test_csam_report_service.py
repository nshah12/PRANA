"""Tests for services/csam_report_service.py — implements the previously-stub
report_csam_to_ncmec activity (workflows/security.py's CSAMReportingWorkflow),
a mandatory legal filing under the POCSO Act + IT Act.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Settings
from services.csam_report_service import CSAMReportService


@pytest.mark.asyncio
async def test_dev_mode_logs_critical_and_does_not_call_out():
    settings = Settings(ncmec_report_url="")
    db = MagicMock()
    svc = CSAMReportService(db, settings)

    with patch("services.csam_report_service.log") as mock_log:
        result = await svc.report_to_ncmec(document_id="doc-1", tenant_id="t-1")

    assert result == {"report_id": "DEV-NOOP"}
    mock_log.critical.assert_called_once()


@pytest.mark.asyncio
async def test_configured_mode_posts_to_ncmec_and_returns_report_id():
    settings = Settings(ncmec_report_url="https://cybertipline.example/report", ncmec_api_key="secret-key")
    db = MagicMock()
    svc = CSAMReportService(db, settings)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"report_id": "CT-12345"}
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await svc.report_to_ncmec(document_id="doc-1", tenant_id="t-1")

    assert result == {"report_id": "CT-12345"}
    call_kwargs = mock_client.post.call_args
    assert call_kwargs.args[0] == "https://cybertipline.example/report"
    assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer secret-key"


@pytest.mark.asyncio
async def test_configured_mode_raises_on_http_error():
    settings = Settings(ncmec_report_url="https://cybertipline.example/report")
    db = MagicMock()
    svc = CSAMReportService(db, settings)

    import httpx
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock(status_code=500),
    ))

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await svc.report_to_ncmec(document_id="doc-1", tenant_id="t-1")
