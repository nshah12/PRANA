@../CLAUDE.md

# PRANA AI — Extraction Pipeline

## What lives here
Stages 03–05 of the DocumentPipelineWorkflow. Runs on GPU worker pods — separate deploy from `prana-api`.

```
prana-ai/
  llm_client.py              ← LLMClient + EmbeddingClient (OpenAI-compatible)
  extraction/
    extraction_service.py    ← Stage 04: doc_type → prompt → LLM → Pydantic schema
    prompts/                 ← one .py per doc type (10 types)
    schemas/                 ← Pydantic output models per doc type
  resolution/
    resolution_service.py    ← Stage 05: 4-level identity ladder
    fuzzy_service.py         ← rapidfuzz name matching + DOJ tiebreaker
  insights/
    benchmark_service.py     ← raw ₹ → percentile (the privacy boundary)
    career_insight_service.py← LLM career narrative from benchmarked data
```

## Deployment
- Separate Docker image from `prana-api` — GPU instance (at least 1x A10G for 14B model)
- `prana-api` calls `prana-ai` via internal HTTP (not direct Python import)
- Temporal activities in `prana-api/workflows/` call `prana-ai` service endpoints for Stages 04–05
- Scales independently: GPU autoscaling on document ingest volume

## LLM Stack
- **Client:** `llm_client.py` — OpenAI-compatible, works with HuggingFace / Ollama / vLLM
- **Extraction model:** `Qwen/Qwen2.5-14B-Instruct` (config: `extraction_llm_model`)
- **Insight model:** `meta-llama/Llama-3.1-8B-Instruct` (config: `insight_llm_model`)
- **Embeddings:** `BAAI/bge-m3` (config: `embedding_model`) — multilingual, Hindi+English
- **Current backend:** HuggingFace Inference Endpoints → moving to local vLLM/Ollama

Config keys (all in `platform_config`, overridable per tenant):
```
llm_base_url                   # HF endpoint or http://localhost:11434/v1
extraction_llm_model           # Qwen/Qwen2.5-14B-Instruct
insight_llm_model              # meta-llama/Llama-3.1-8B-Instruct
embedding_model                # BAAI/bge-m3
embedding_base_url
llm_request_timeout_seconds    # default 120
```

## Stage 04 — Extraction

**Input:** redacted document text (NIK already `[NIK_REDACTED]` from Stage 02)
**Output:** `extracted_fields` JSONB with per-field confidence scores

10 document types, each with its own prompt + schema:
| Doc type | Prompt file | Schema |
|----------|------------|--------|
| SALARY_SLIP | `prompts/salary_slip.py` | `SalarySlipExtraction` |
| FORM_16 | `prompts/form_16.py` | `Form16Extraction` |
| OFFER_LETTER | `prompts/offer_letter.py` | `OfferLetterExtraction` |
| APPOINTMENT_LETTER | `prompts/appointment_letter.py` | `BaseExtraction` (schema TODO) |
| INCREMENT_LETTER | `prompts/increment_letter.py` | `BaseExtraction` (schema TODO) |
| PROMOTION_LETTER | `prompts/promotion_letter.py` | `BaseExtraction` (schema TODO) |
| EXPERIENCE_LETTER | `prompts/experience_letter.py` | `BaseExtraction` (schema TODO) |
| RELIEVING_LETTER | `prompts/relieving_letter.py` | `BaseExtraction` (schema TODO) |
| JOINING_LETTER | `prompts/joining_letter.py` | `BaseExtraction` (schema TODO) |
| PF_ACKNOWLEDGEMENT | `prompts/pf_acknowledgement.py` | `BaseExtraction` (schema TODO) |

Confidence thresholds:
| Score | Action |
|-------|--------|
| ≥ 0.90 | ROUTED |
| 0.75–0.90 | ROUTED but flagged fields go to exception queue |
| < 0.75 | LOW_CONFIDENCE — OA review required |

## Stage 05 — Identity Resolution

**Input:** `pan_token` (from Stage 02) + `extracted_fields`
**No LLM** — pure algorithmic matching, 4 levels, stop at first success:

```
Level 1 — pan_token exact match       O(1) indexed
Level 2 — employee_id exact match     only if doc has emp_id field
Level 3 — fuzzy name + DOJ           rapidfuzz token_sort_ratio ≥ 88
Level 4 — embedding cosine ≥ 0.92    BAAI/bge-m3, Qdrant per-tenant collection
```

UNRESOLVED → exception_queue → wait up to 7 days for OA-Admin `exception_resolved` signal.

## Privacy Boundary — benchmark_service.py

`benchmark_service.py` is the **only** place raw ₹ values from `extracted_fields` are read.
Output is always percentiles / qualitative labels — never raw amounts.

```
extracted_fields  →  benchmark_service  →  career_context (percentiles only)
                                        →  career_insight_service (LLM)
```

Do not pass `extracted_fields` directly to any LLM call in `insights/`. Always pass through `benchmark_service` first.
