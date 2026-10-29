# Backend demo: quick checklist

Read [the complete walkthrough](backend-review-walkthrough.md) first.

## Before the review

- Close `.env` and anything showing credentials before screen-sharing.
- Start Docker; run `docker compose up -d --build` and `docker compose ps`.
- Confirm Groq/model and the separate demo index through `/api/health`; health alone is not full readiness.
- Run ingestion and warm the main question in advance. Rehearsal: six documents, 170 chunks.
- Open chat, Swagger, the Northwind Section 3.4 source, and the backend code files below.
- Run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Test-Backend.ps1 -IncludeFormatParity`.
- Keep generated rehearsal evidence available; label saved output honestly if live quota fails.

## Show this sequence

1. Introduce the problem in one minute.
2. Show the original late-payment clause.
3. Explain/load documents -> chunk -> embed -> Chroma upsert.
4. Inspect actual chunk IDs and metadata.
5. Use `/api/inspect` with:

   ```json
   {"question":"What is the late payment interest rate under the Northwind Master Services Agreement?","document_type":"contract"}
   ```

6. Compare answer, source excerpt and top retrieved chunks. Expected: 1.5% monthly, qualified by undisputed amounts and the lower legal maximum.
7. Trace router -> Container -> QaService -> RetrievalService -> LLMGenerator -> Chroma/provider adapters.
8. Show a blocked injection, a drafting refusal and an empty-question 422.
9. Show request ID, logs, tests and the real Chroma filter regression.
10. Show the actual offline benchmark and one improvement area.

## Files to open in order

```text
backend/legal_rag/interfaces/http/app.py
backend/legal_rag/interfaces/http/routers/qa.py
backend/legal_rag/interfaces/http/schemas.py
backend/legal_rag/composition.py
backend/legal_rag/application/ports.py
backend/legal_rag/application/workflows/qa.py
backend/legal_rag/application/workflows/ingestion.py
backend/legal_rag/application/workflows/retrieval.py
backend/legal_rag/application/workflows/generation.py
backend/legal_rag/infrastructure/vector_store/chroma.py
backend/legal_rag/domain/policies.py
backend/tests/slow/test_chroma_metadata_filters.py
```

## Facts to remember

- Current provider: Groq; generation model: `openai/gpt-oss-20b`.
- Retrieval embeddings and cross-encoder are local pretrained models; no fine-tuning.
- Current demo uses candidate k=5/n=3; defaults in Settings differ.
- Chunk sizes are whitespace-word counts despite `tokens` in their setting names.
- 231 non-slow backend tests and four selected adapter/format tests passed.
- Offline benchmark: **20/32**, not a Groq accuracy result or a 100% pass claim.
- The amendment rehearsal used fallback after quote-verification failures.
- The API retains evidence; the UI displays only the answer.
- Metadata filtering is not authorization; local API-key enforcement is currently off.
- Chat display history is not backend conversational memory.
- Agents are policy-driven; the MCP repository is a sample, not a real enterprise integration.

## If something fails

| Symptom | Explain/check |
|---|---|
| Slow first request | Models are warming/downloading; health does not mean models are loaded |
| Provider 429/503 | Quota/rate limit; inspect the actual error, do not repeatedly hammer the API |
| Long quoted reply | Extractive fallback; inspect validation/provider logs |
| Wrong/missing answer | Compare source, filters, retrieval and excerpts before blaming generation |
| New upload breaks ingestion | Duplicate source IDs or parsing issue; use the isolated upload demo |
| Same old response in UI | Start a new chat; previous display history is stored locally |

End with the next priorities: evidence/version correctness, authentication/tenant isolation, reliable indexing, consistent provider failure handling and measurable evaluation.
