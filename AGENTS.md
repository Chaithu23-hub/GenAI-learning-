# AGENTS.md — Legal Document RAG Assistant

## Project overview

Learning project: a grounded RAG pipeline over sample legal documents (2 contracts +
2 amendments in `data/legal/`). Retrieval is fully local (sentence-transformers bi-encoder +
Chroma/HNSW + cross-encoder re-ranking). Generation defaults to an offline extractive fallback;
an LLM backend activates automatically when an OpenAI-compatible endpoint (e.g. Ollama) is
reachable, or via `--backend llm`.

## Environment

- Python 3.13 per-user install at `%LOCALAPPDATA%\Programs\Python\Python313`
- Project venv at `.venv` — activate with `.venv\Scripts\Activate.ps1`
- torch is CPU-only (installed from `https://download.pytorch.org/whl/cpu`); do NOT run a plain
  `pip install torch` (pulls the ~2.5 GB CUDA wheel)

## Commands

```powershell
python main.py ingest                # chunk + embed + store data/legal/*.md
python main.py ask "question"        # one question (--filter, --backend, --json)
python main.py chat                  # interactive loop
.venv\Scripts\streamlit.exe run ui.py  # web UI (question box, sources, re-ingest button)
pytest tests/                        # unit + end-to-end tests
```

## Conventions

- Every code path implementing a curriculum concept carries a `# [TOPIC: <name>] — ...`
  comment. Preserve these when editing; add one for any new concept you implement.
- The response JSON shape is fixed by `RESPONSE_SCHEMA` in `legal_assistant/schema.py`.
  Do not add/remove fields without updating `validate_response` and the README contract.
- Document corpus lives in `data/legal/`; filenames starting with `amendment` get
  `document_type="amendment"` metadata (see `vector_store.document_type_for`).
- Tunables (chunk size, top-K/N, thresholds, model names, LLM endpoint) belong in
  `legal_assistant/config.py` — no magic numbers elsewhere.
