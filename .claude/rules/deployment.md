# PRANA Deployment Boundary Rules
# Auto-loaded when editing prana-ai/** or prana-ask/**
# ENFORCEMENT: scripts/enforce_rules.py — DEPLOY-01 (no cross-service imports)
# Run /enforce before any PR merge. Violations block deployment.

## 3 separate deployed services — no shared Python packages

| Service | Hardware | Purpose |
|---------|---------|---------|
| `prana-api` | CPU | FastAPI REST + Temporal workflow shells |
| `prana-ai` | GPU | 6-stage AI extraction pipeline |
| `prana-ask` | GPU | Employee RAG chatbot |

## Cross-service imports are FORBIDDEN
- `prana-ai` code: imports ONLY from within `prana-ai/`
- `prana-ask` code: imports ONLY from within `prana-ask/`
- Never: `from prana_api.anything import ...` inside prana-ai or prana-ask

## LLM clients (each service has its own)
- `prana-ai/llm_client.py` — `LLMClient` for extraction
- `prana-ask/llm_client.py` — `LLMClient` for RAG

## AI models
- Extraction: `Qwen/Qwen2.5-14B-Instruct`
- Insights/RAG: `meta-llama/Llama-3.1-8B-Instruct`
- Embeddings: `BAAI/bge-m3` (multilingual — Hindi + English)
- OCR: Tesseract (local) → AWS Textract (fallback)

## prana-ai 6-stage pipeline
Stage 01: Ingest & validate
Stage 02: OCR
Stage 03: LLM extraction (Qwen) — full doc in, structured JSON out
Stage 04: Resolution — match employee identity
Stage 05: Insights generation (Llama) — insights only, no raw figures
Stage 06: Route to vault

## Privacy in pipeline
Stage 03 LLM input = full document data (needed for extraction)
Stage 05 LLM output = insights ONLY (raw ₹/PAN never written to DB)
