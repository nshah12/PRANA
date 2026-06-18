@../CLAUDE.md

# PRANA Ask — Employee Chatbot

## What is this
A standalone RAG chatbot that answers employee questions about their own career vault.
Completely separate from the document pipeline (`prana-ai`). Different LLM, different vector store scope, different scaling profile.

```
prana-ask/
  ask_service.py       ← Orchestrates: query → context → LLM → post-process guard
  context_builder.py   ← Assembles RAG context scoped to one employee
  api/                 ← FastAPI router: POST /ask (separate deployable endpoint)
```

## Deployment
- Separate Docker image — GPU instance (1x A10 or T4 sufficient for 8B model)
- Exposed as internal API: `ask.prana.internal/ask`
- `prana-api` proxies employee requests here after JWT validation
- Scales on active user sessions, not document volume (different from `prana-ai`)

## LLM
- **Model:** `meta-llama/Llama-3.1-8B-Instruct` (config: `ask_llm_model`)
- **Backend:** HuggingFace Inference Endpoints now → local vLLM/Ollama later
- **Temperature:** 0.3 (conversational, not deterministic like extraction)
- **Max context:** 6,000 tokens per query
- **Rate limit:** 20 queries / employee / hour (config: `ask_rate_limit_per_hour`)

## Scope Boundary (non-negotiable)
`employee_user_id` from JWT is the hard scope limit — every DB query and vector search is filtered by it.
Never accept `employee_user_id` from the request body — always from JWT claims only.

## RAG Architecture

```
Employee query
     ↓
context_builder.py
  ├── career timeline         (employee_master rows, employer/role/dates)
  ├── cached insights         (career_event.insight_text — pre-generated, no re-LLM)
  ├── vault summary           (doc types available, date ranges)
  └── relevant doc summaries  (embedding similarity, scoped to employee)
     ↓
ask_service.py → LLM (Llama 3.1 8B)
     ↓
post-process guard  ← blocks any ₹ amounts or PAN patterns in response
     ↓
Response to employee
```

## Privacy Rules for Ask PRANA

**Context passed to LLM must never contain:**
- Raw ₹ salary amounts — use percentile labels from `benchmark_service`
- PAN numbers — these are `[NIK_REDACTED]` in all stored text
- Another employee's data — strict `employee_user_id` filter on every query

**Post-process guard in `ask_service.py`:**
```python
_BLOCK_PATTERNS = [
    re.compile(r"₹\s*[\d,]+"),              # rupee amounts
    re.compile(r"Rs\.?\s*[\d,]+"),           # Rs. amounts
    re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"), # PAN pattern
]
```
If LLM response matches any pattern → refuse + log + return safe error message. Never return the raw response.

## System Prompt
```
You are Ask PRANA, an AI career advisor for the employee whose data you have been given.
Rules:
- NEVER reveal raw salary amounts, CTC figures, PAN numbers, or exact financial figures
- Express compensation as trends, percentiles, or qualitative labels only
- Answer ONLY from the provided context — do not invent missing data
- If information is unavailable, say: "I don't have that in your vault yet"
- Keep responses concise — this is a mobile chat interface
```

## Vector Store for Ask PRANA
- Collection per employee: `employee_{employee_user_id}` (not per tenant — employee-scoped)
- Each vector point = embedding of `career_event.insight_text` (insight summary, not raw doc)
- Model: `BAAI/bge-m3` (same as prana-ai, separate Qdrant instance)
- Re-indexed by `InsightRefreshWorkflow` whenever a new document is ROUTED

## What Ask PRANA can answer
- "What was my last salary increment?" → from INCREMENT_LETTER insights
- "How many companies have I worked at?" → from career timeline
- "Is my PF linked to my UAN?" → from PF_ACKNOWLEDGEMENT doc
- "When did I join NPCI?" → from JOINING_LETTER or APPOINTMENT_LETTER
- "What does my Form 16 say about my tax?" → from FORM_16 insights (not raw figures)

## What Ask PRANA must NOT answer
- "What is my exact salary?" → blocked (raw ₹)
- "What is my PAN number?" → blocked (NIK)
- "What is Rahul's salary?" → blocked (different employee)
- Anything not in the employee's own vault → "I don't have that information"
