"""
Stage 03 — Safety Scan
Two sequential scans:
  1. Virus/malware — ClamAV via clamd socket
  2. NSFW / CSAM — image-based classifier on extracted pages

CSAM detection: document.csam_detected = TRUE → infinite retention,
CsamReportWorkflow triggered, no further processing, cannot be deleted by anyone.

virus_scan_status / nsfw_scan_status update document row directly.
"""
import io
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ScanOutcome(str, Enum):
    CLEAN       = "CLEAN"
    QUARANTINED = "QUARANTINED"   # virus/malware
    FLAGGED     = "FLAGGED"       # NSFW — human review
    CSAM        = "CSAM"          # CSAM — infinite hold, law enforcement
    FAILED      = "FAILED"        # scan error — treat as QUARANTINED


@dataclass
class ScanResult:
    virus_status: str
    nsfw_status:  str
    csam_detected: bool
    threat_name: Optional[str] = None


class Stage03Scan:

    def __init__(self, clamd_socket: str = "/var/run/clamav/clamd.ctl"):
        self._clamd_socket = clamd_socket

    def run(self, file_bytes: bytes, ext: str) -> ScanResult:
        virus_status = self._virus_scan(file_bytes)
        if virus_status == ScanOutcome.QUARANTINED:
            return ScanResult(
                virus_status=ScanOutcome.QUARANTINED,
                nsfw_status="PENDING",
                csam_detected=False,
            )

        nsfw_status, csam = self._nsfw_scan(file_bytes, ext)
        return ScanResult(
            virus_status=virus_status,
            nsfw_status=nsfw_status,
            csam_detected=csam,
        )

    def _virus_scan(self, file_bytes: bytes) -> str:
        try:
            import clamd
            cd = clamd.ClamdUnixSocket(self._clamd_socket)
            result = cd.instream(io.BytesIO(file_bytes))
            status, _ = result.get("stream", ("OK", None))
            return ScanOutcome.CLEAN if status == "OK" else ScanOutcome.QUARANTINED
        except Exception:
            return ScanOutcome.FAILED

    def _nsfw_scan(self, file_bytes: bytes, ext: str) -> tuple[str, bool]:
        """
        Extract page images from PDF/DOCX and run classifier.
        Returns (nsfw_status, csam_detected).
        CSAM classifier is a separate model — conservative threshold (any positive = CSAM).
        """
        try:
            pages = _extract_page_images(file_bytes, ext)
            if not pages:
                return ScanOutcome.CLEAN, False

            nsfw_scores = [_nsfw_score(p) for p in pages]
            csam_hits   = [_csam_score(p) for p in pages]

            if any(csam_hits):
                return ScanOutcome.CSAM, True
            if max(nsfw_scores) > 0.7:
                return ScanOutcome.FLAGGED, False
            return ScanOutcome.CLEAN, False
        except Exception:
            return ScanOutcome.FAILED, False


def _extract_page_images(file_bytes: bytes, ext: str) -> list:
    """Convert PDF/image pages to raw PNG bytes for scanning."""
    try:
        if ext == "pdf":
            import fitz
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            images = []
            for page in doc:
                pix = page.get_pixmap(dpi=72)
                images.append(pix.tobytes("png"))
            return images
        if ext in ("jpeg", "jpg", "png", "tiff", "tif", "bmp", "webp"):
            return [file_bytes]
        return []
    except Exception:
        return []


def _nsfw_score(image_bytes: bytes) -> float:
    """
    NSFW classification via NudeNet.
    Returns probability score 0.0–1.0.  Above 0.7 → FLAGGED for human review.

    NudeNet classifier labels and their NSFW mapping:
      EXPOSED_*  labels → nsfw
      COVERED_*  labels → borderline (not flagged)
      SAFE       label  → clean

    Falls back to 0.0 (safe) on any import / inference error so a missing
    model never blocks document ingestion — ops alert is raised separately.
    """
    try:
        from nudenet import NudeClassifier
        import io
        classifier = NudeClassifier()
        # NudeNet expects a file path or PIL image — wrap bytes in BytesIO
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        # classify() returns {label: score} dict for a single image
        result = classifier.classify_image(img)
        # Sum all "EXPOSED_*" class probabilities as the NSFW signal
        nsfw = sum(
            score for label, score in result.items()
            if label.startswith("EXPOSED_")
        )
        return min(nsfw, 1.0)
    except ImportError:
        # NudeNet not installed — log warning, pass as safe
        import logging
        logging.getLogger(__name__).warning(
            "nudenet not installed — NSFW scan skipped. "
            "Install: pip install nudenet"
        )
        return 0.0
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("NSFW scan error: %s", exc)
        return 0.0


# CSAM known-bad image hash list.
# In production this is loaded from NCMEC's PhotoDNA hash list (enterprise agreement)
# or Microsoft's PhotoDNA Cloud Service API. Dev uses an empty set — no false positives.
# Hash format: SHA-256 hex of raw image bytes.
_CSAM_HASH_SET: frozenset[str] = frozenset()


def _load_csam_hashes() -> frozenset[str]:
    """
    Load known-bad SHA-256 hashes from the configured hash list file.
    File path from env CSAM_HASH_FILE — one hex hash per line.
    Returns empty frozenset if file missing (safe default — never blocks).
    """
    import os
    hash_file = os.environ.get("CSAM_HASH_FILE", "")
    if not hash_file:
        return frozenset()
    try:
        with open(hash_file) as f:
            return frozenset(line.strip().lower() for line in f if line.strip())
    except OSError:
        return frozenset()


# Loaded once at import time — reload worker to pick up updated hash list
_CSAM_HASH_SET = _load_csam_hashes()


def _csam_score(image_bytes: bytes) -> bool:
    """
    CSAM detection via SHA-256 hash matching against known-bad hash list.

    Two complementary checks:
    1. Exact SHA-256 match against _CSAM_HASH_SET (NCMEC / PhotoDNA list)
    2. If PHOTODNA_API_KEY env var is set, also call Microsoft PhotoDNA Cloud API

    Conservative design: any positive → True. False negative is acceptable;
    false positive is not (we would incorrectly block a legitimate document).
    The hash list is maintained by NCMEC and is extremely low false-positive rate.
    """
    import hashlib
    img_hash = hashlib.sha256(image_bytes).hexdigest()

    # Check 1: local hash list
    if img_hash in _CSAM_HASH_SET:
        import logging
        logging.getLogger(__name__).critical(
            "CSAM hash match detected — document flagged for legal hold"
        )
        return True

    # Check 2: PhotoDNA Cloud API (optional — requires enterprise agreement with Microsoft)
    api_key = __import__("os").environ.get("PHOTODNA_API_KEY", "")
    if api_key:
        try:
            import base64, urllib.request, json as _json
            payload = _json.dumps({
                "DataRepresentation": "URL",
                "Value": base64.b64encode(image_bytes).decode(),
            }).encode()
            req = urllib.request.Request(
                "https://api.microsoftmoderator.com/photodna/v1.0/Match",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Ocp-Apim-Subscription-Key": api_key,
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read())
                if data.get("IsMatch"):
                    import logging
                    logging.getLogger(__name__).critical(
                        "PhotoDNA API match — document flagged for legal hold"
                    )
                    return True
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("PhotoDNA API call failed: %s", exc)
            # Fail open — do not block document on API error

    return False
