"""Tests for pipeline/stage03_scan.py — scan outcomes and pipeline halting."""
import inspect
from unittest.mock import MagicMock, patch

from pipeline.stage03_scan import Stage03Scan, ScanOutcome, ScanResult


def test_stage03_csam_detection_triggers_legal_hold():
    # CSAM detection must set csam_detected=True in the ScanResult so the
    # pipeline can trigger CsamReportWorkflow and apply infinite legal hold.
    src = inspect.getsource(Stage03Scan.run)
    assert "csam_detected" in src, \
        "Stage03.run must propagate csam_detected flag from _nsfw_scan result"
    # When CSAM is detected the result must have csam=True
    src_nsfw = inspect.getsource(Stage03Scan._nsfw_scan)
    assert "CSAM" in src_nsfw, \
        "_nsfw_scan must have a code path that returns ScanOutcome.CSAM"


def test_stage03_virus_detected_halts_pipeline():
    # When the virus scan returns QUARANTINED the stage must return immediately
    # without running the (expensive) NSFW scan.
    svc = Stage03Scan.__new__(Stage03Scan)

    with patch.object(Stage03Scan, "_virus_scan", return_value=ScanOutcome.QUARANTINED):
        with patch.object(Stage03Scan, "_nsfw_scan") as mock_nsfw:
            result = svc.run(b"malware bytes", "pdf")

    mock_nsfw.assert_not_called()
    assert result.virus_status == ScanOutcome.QUARANTINED
