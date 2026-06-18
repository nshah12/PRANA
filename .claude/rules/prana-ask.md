# PRANA Ask (Chatbot) Rules
# Auto-loaded when editing prana-ask/**

## What Ask PRANA is
Standalone RAG chatbot — separate deployed service (GPU worker).
Employees ask questions about their own career documents in natural language.
Example: "What was my designation at TechCorp?" "How many years have I worked?"

## Stack
- `meta-llama/Llama-3.1-8B-Instruct` — RAG generation model
- `BAAI/bge-m3` — multilingual embeddings (Hindi + English)
- Qdrant — vector database for document chunks
- FastAPI — thin HTTP layer
- NO dependency on prana-api — standalone service

## Privacy guard (NEVER bypass)
The RAG pipeline has a mandatory privacy filter on LLM output:

```
Employee query → embed → Qdrant similarity search → retrieve chunks
→ LLM generates answer → PRIVACY FILTER → response to employee
```

Privacy filter MUST block:
- Any raw ₹ salary figure in the response
- Any PAN or NIK value
- Any other employee's data (cross-contamination check)

If privacy filter blocks content → respond: "I can share insights about your career but cannot share specific financial figures."

## What the chatbot CAN answer
- Career timeline questions ("when did I join X?")
- Designation and grade history
- Document availability ("do I have Form 16 for FY 2023?")
- Insight-level summaries ("your career shows progression from analyst to manager")

## What it CANNOT answer (hard blocks)
- Exact salary amounts
- PAN or any identity number
- Questions about other employees
- Anything requiring real-time DB lookup (RAG only — no live DB queries from Ask)

## Vector store rules
- Chunk size: 512 tokens with 50-token overlap
- Metadata on each chunk: `employee_user_id`, `document_id`, `doc_type`, `tenant_id`
- Qdrant filter on EVERY query: `employee_user_id = current_user` — never skip this filter
- Re-embed on document re-route (pipeline_status → ROUTED triggers embedding job)

## Deployment
- Runs on GPU worker — separate from prana-api
- prana-api proxies `/ask/*` requests to prana-ask service
- prana-ask authenticates employee JWT independently — same secret, different validator
- No shared Python packages with prana-api or prana-ai
