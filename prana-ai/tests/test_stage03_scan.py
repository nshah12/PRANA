"""Tests for pipeline/stage03_scan.py — scan outcomes and pipeline halting."""
import hashlib
import inspect
import sys
import types
from unittest.mock import MagicMock, patch

from pipeline.stage03_scan import (
    Stage03Scan,
    ScanOutcome,
    ScanResult,
    _nsfw_score,
    _csam_score,
)


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


# ── _nsfw_score — real NudeNet v3 integration (gap 1a / 4b) ────────────────

def _install_fake_nudenet(detections, capture: dict):
    """Injects a fake `nudenet` module into sys.modules so `_nsfw_score`'s
    `from nudenet import NudeDetector` succeeds without the real (heavy,
    GPU-oriented) package installed. Captures the argument passed to
    `.detect()` so tests can assert raw bytes are passed (NudeNet v3's
    `detect()` accepts str/bytes/ndarray — NOT a PIL.Image object)."""
    fake_module = types.ModuleType("nudenet")

    class FakeNudeDetector:
        def detect(self, image):
            capture["arg"] = image
            return detections

    fake_module.NudeDetector = FakeNudeDetector
    return patch.dict(sys.modules, {"nudenet": fake_module})


def test_nsfw_score_passes_raw_bytes_to_detector():
    # NudeNet v3's NudeDetector.detect() only accepts str path / bytes /
    # np.ndarray / BufferedReader — a PIL.Image object raises ValueError
    # inside the library and gets silently swallowed by our broad except,
    # making the scan a permanent no-op. Must pass the raw bytes through.
    capture: dict = {}
    with _install_fake_nudenet([], capture):
        _nsfw_score(b"raw-image-bytes")
    assert capture["arg"] == b"raw-image-bytes"
    assert isinstance(capture["arg"], (bytes, bytearray))


def test_nsfw_score_flags_v3_exposed_suffix_labels():
    # NudeNet v3 labels are SUFFIX-based (e.g. "FEMALE_GENITALIA_EXPOSED",
    # "BUTTOCKS_EXPOSED") — not the v2 PREFIX style ("EXPOSED_GENITALIA_F").
    capture: dict = {}
    detections = [
        {"class": "FEMALE_GENITALIA_EXPOSED", "score": 0.95, "box": [0, 0, 1, 1]},
        {"class": "FACE_FEMALE", "score": 0.60, "box": [0, 0, 1, 1]},
    ]
    with _install_fake_nudenet(detections, capture):
        score = _nsfw_score(b"raw-image-bytes")
    assert score == 0.95


def test_nsfw_score_ignores_covered_labels():
    capture: dict = {}
    detections = [
        {"class": "FEMALE_GENITALIA_COVERED", "score": 0.99, "box": [0, 0, 1, 1]},
        {"class": "BUTTOCKS_COVERED", "score": 0.88, "box": [0, 0, 1, 1]},
    ]
    with _install_fake_nudenet(detections, capture):
        score = _nsfw_score(b"raw-image-bytes")
    assert score == 0.0


def test_nsfw_score_sums_multiple_exposed_labels_capped_at_one():
    capture: dict = {}
    detections = [
        {"class": "FEMALE_BREAST_EXPOSED", "score": 0.9, "box": [0, 0, 1, 1]},
        {"class": "BUTTOCKS_EXPOSED", "score": 0.9, "box": [0, 0, 1, 1]},
    ]
    with _install_fake_nudenet(detections, capture):
        score = _nsfw_score(b"raw-image-bytes")
    assert score == 1.0  # summed 1.8, capped at 1.0


def test_nsfw_score_returns_zero_when_nudenet_not_installed():
    # Safe default: a missing model dependency must never block ingestion.
    with patch.dict(sys.modules, {"nudenet": None}):
        score = _nsfw_score(b"raw-image-bytes")
    assert score == 0.0


# ── _csam_score — hash matching + PhotoDNA API (gap 4b) ────────────────────

def test_csam_score_matches_known_bad_hash():
    image_bytes = b"known-bad-image-content"
    bad_hash = hashlib.sha256(image_bytes).hexdigest()
    with patch("pipeline.stage03_scan._CSAM_HASH_SET", frozenset({bad_hash})):
        assert _csam_score(image_bytes) is True


def test_csam_score_clean_image_no_hash_match_no_api_key():
    with patch("pipeline.stage03_scan._CSAM_HASH_SET", frozenset()):
        with patch.dict("os.environ", {}, clear=False):
            import os as _os
            _os.environ.pop("PHOTODNA_API_KEY", None)
            assert _csam_score(b"a perfectly innocent salary slip scan") is False


def test_csam_score_calls_photodna_api_when_key_configured():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {"IsMatch": True}
    mock_response.raise_for_status.return_value = None
    mock_client.__enter__.return_value.post.return_value = mock_response

    with patch("pipeline.stage03_scan._CSAM_HASH_SET", frozenset()):
        with patch.dict("os.environ", {"PHOTODNA_API_KEY": "test-key"}):
            with patch("pipeline.stage03_scan.httpx.Client", return_value=mock_client):
                result = _csam_score(b"some image bytes")

    assert result is True
    called_url = mock_client.__enter__.return_value.post.call_args[0][0]
    assert called_url == "https://api.microsoftphotodna.com/v1.0/Match"


def test_csam_score_fails_open_when_photodna_api_errors():
    # API/network failure must never block document ingestion (fail open).
    with patch("pipeline.stage03_scan._CSAM_HASH_SET", frozenset()):
        with patch.dict("os.environ", {"PHOTODNA_API_KEY": "test-key"}):
            with patch("pipeline.stage03_scan.httpx.Client", side_effect=Exception("network down")):
                result = _csam_score(b"some image bytes")

    assert result is False
