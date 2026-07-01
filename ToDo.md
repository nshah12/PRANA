# PRANA — Parked Work

Items parked here are known gaps, not blockers. Pick up when the time is right.

---

## Frontend

### Static UI copy not through message taxonomy
**Scope:** `prana-mobile/` and `prana-portal/`
**Detail:** API error/success codes flow correctly through `PranaError` → `tError()` / `tSuccess()`. But static UI copy — screen titles, labels, empty states, instructional text — is hardcoded inline in JSX. Examples:
- Mobile: `"Sign in another way"`, `"Before we begin"`, `"Check your messages"`, `"Someone wants in."`, `"Name this phone"`
- Portal: `"Failed to load attrition data."`, `"No active anomalies"`, `"Select date range..."`, inline error strings in `DigestDatePicker.tsx`

**What to do:** Route all static copy through `en.json` + `t()` in both apps. Enables multi-language support later.
**Effort:** Large — touches most screens in both apps.

---

## Testing

### Empty test stubs (TDD-02 warnings)
**Files:** `prana-api/tests/test_base.py`, `test_darwinbox.py`, `test_keka.py`
**Detail:** Test files exist but have no `def test_*()` functions. Enforce warns but does not block.
**What to do:** Replace stubs with real failing tests per TDD rules.

---

## Pipeline

### 14 pipeline gaps (ML, DB, Temporal, testing)
**Detail:** Tracked in memory — `gap_pipeline_doc_identification.md`. Covers NudeNet/PhotoDNA endpoints, unclassified_queue migration, DOC_ROUTED Kafka publish missing, InsightRefresh/EmbeddingUpdate activities unregistered, OA-Admin classify endpoint missing, CSAM child workflow not firing.
**What to do:** Work through prioritised fix order in that memory entry.

---
