"""
Stage 04 — LLM Extraction
1. OCR: Tesseract (primary) → AWS Textract (fallback)
2. Redact NIK from text before LLM sees it (LLM never sees raw PAN)
3. LLM extraction via extraction_service
4. Return extracted_fields JSONB — no raw ₹, no PAN ever stored

Privacy: NIK is replaced with [NIK_REDACTED] in OCR text before LLM call.
The raw PAN was already consumed in Stage 02 to compute pan_token — it is not available here.
"""
import re
import io
from typing import Optional

from extraction.extraction_service import ExtractionService, DocType
from llm_client import LLMClient

# Indian PAN pattern — redacted before LLM sees text
_PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")


class Stage04Extract:

    def __init__(self, llm_client: LLMClient, aws_region: str = "ap-south-1"):
        self._extraction_svc = ExtractionService(llm_client)
        self._aws_region = aws_region

    async def run(
        self,
        file_bytes: bytes,
        ext: str,
        doc_type: str,
        doc_period: Optional[str],
    ) -> dict:
        # OCR
        text = self._ocr(file_bytes, ext)

        # Redact NIK before LLM — pan_token already computed in Stage 02
        redacted_text = _PAN_RE.sub("[NIK_REDACTED]", text)

        # LLM extraction
        dt = DocType(doc_type)
        result = await self._extraction_svc.extract(dt, redacted_text)

        return {
            "extracted_fields": result.fields,
            "overall_confidence": result.overall_confidence,
            "low_confidence_fields": result.low_confidence_fields,
        }

    def _ocr(self, file_bytes: bytes, ext: str) -> str:
        try:
            return self._tesseract_ocr(file_bytes, ext)
        except Exception:
            return self._textract_ocr(file_bytes, ext)

    def _tesseract_ocr(self, file_bytes: bytes, ext: str) -> str:
        import pytesseract
        from PIL import Image

        if ext == "pdf":
            images = _pdf_to_images(file_bytes)
        else:
            images = [Image.open(io.BytesIO(file_bytes))]

        return "\n\n".join(
            pytesseract.image_to_string(img, lang="eng+hin")
            for img in images
        )

    def _textract_ocr(self, file_bytes: bytes, ext: str) -> str:
        import boto3
        client = boto3.client("textract", region_name=self._aws_region)
        resp = client.detect_document_text(Document={"Bytes": file_bytes})
        lines = [
            b["Text"] for b in resp.get("Blocks", [])
            if b["BlockType"] == "LINE"
        ]
        return "\n".join(lines)


def _pdf_to_images(file_bytes: bytes) -> list:
    import fitz
    from PIL import Image
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    return images
