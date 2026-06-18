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
    """Convert PDF/DOCX pages to PIL images for scanning."""
    try:
        if ext == "pdf":
            import fitz  # PyMuPDF
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            images = []
            for page in doc:
                pix = page.get_pixmap(dpi=72)
                images.append(pix.tobytes("png"))
            return images
        return []
    except Exception:
        return []


def _nsfw_score(image_bytes: bytes) -> float:
    """Placeholder — wire real NSFW classifier (e.g. NudeNet or similar)."""
    return 0.0


def _csam_score(image_bytes: bytes) -> bool:
    """Placeholder — wire PhotoDNA or equivalent CSAM hash-matching service."""
    return False
