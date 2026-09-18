# AGENTS.md — Legal Document RAG Assistant

## Project overview

Learning project: a grounded RAG pipeline over sample legal documents (2 contracts +
2 amendments in `data/legal/`). Retrieval is fully local (sentence-transformers bi-encoder +
Chroma/HNSW + cross-encoder re-ranking). Generation defaults to an offline extractive fallback;
the optional LLM backend uses Google Gemini when `GOOGLE_API_KEY` is configured, or via
`--backend llm`.

## Environment

- Python 3.13 per-user install at `%LOCALAPPDATA%\Programs\Python\Python313`
- Project venv at `.venv` — activate with `.venv\Scripts\Activate.ps1`
- torch is CPU-only (installed from `https://download.pytorch.org/whl/cpu`); do NOT run a plain
  `pip install torch` (pulls the ~2.5 GB CUDA wheel)

## Commands

```powershell
Push-Location backend
..\.venv\Scripts\python.exe cli.py ingest       # chunk + embed + store data/legal/*.md
..\.venv\Scripts\python.exe -m pytest tests/    # unit + end-to-end tests
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
Pop-Location
```

## Conventions

- Keep domain behavior in `legal_assistant/`; keep FastAPI wiring in `app/`.
- `legal_assistant/stores/` owns persistence adapters. `ingestion/` owns indexing orchestration.
- `legal_assistant/retrieval/retrievers/` owns dense, sparse, and fusion strategies.
- Preserve existing compatibility imports from `legal_assistant.ingestion.vector_store` until
  downstream callers have migrated.
- The response JSON shape is fixed by `RESPONSE_SCHEMA` in `legal_assistant/schema.py`.
  Do not add/remove fields without updating `validate_response` and the README contract.
- Document corpus lives in `data/legal/`; filenames starting with `amendment` get
  `document_type="amendment"` metadata (see `vector_store.document_type_for`).
- Tunables (chunk size, top-K/N, thresholds, model names, LLM endpoint) belong in
  `legal_assistant/config.py` — no magic numbers elsewhere.
