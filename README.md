# LegalRAG

A production-grade **Retrieval-Augmented Generation** service for legal contracts.
Every answer is grounded in retrieved passages with source citations; every
external dependency is behind a Protocol port so the whole thing is testable
without touching the network.

- **Architecture**: Clean / Hexagonal. See [ARCHITECTURE.md](ARCHITECTURE.md).
- **Contribution rules**: See [AGENTS.md](AGENTS.md).
- **Weekly work log**: See `WEEK3_REQUIREMENTS.md` … `WEEK10_REQUIREMENTS.md`.

## What it does

1. **Ingest** markdown contracts and amendments (or PDFs via `/api/upload`).
2. **Chunk** by section headings, embed with SentenceTransformers, index in Chroma.
3. **Retrieve** with dense + BM25 → RRF fusion → cross-encoder rerank.
4. **Guard** against prompt injection, drafting requests, and out-of-scope questions.
5. **Generate** grounded JSON answers (extractive by default, LLM when configured).
6. **Verify** every cited excerpt against the vector store before returning it.
7. **Expose** the pipeline over FastAPI, a Typer CLI, and MCP servers.
8. **Audit** with trajectory checks, deterministic judge assertions, and agent-vs-orchestrator races.

## Layout

```
backend/legal_rag/
├── domain/            # Entities, policies, response schema — pure Python
├── application/       # Ports (Protocols), DTOs, services (use cases)
├── infrastructure/    # Chroma, SentenceTransformers, OpenAI, MCP, settings, logging
├── interfaces/        # HTTP (FastAPI), CLI (Typer), MCP servers
└── composition.py     # DI container
backend/tests/
├── unit/              # Pure domain
├── fakes/             # In-memory port implementations
├── integration/       # Services wired against fakes
└── e2e/               # HTTP TestClient over the container
frontend/              # Angular UI (unchanged)
eval/                  # Evaluation evidence and MCP artifacts
data/legal/            # Contract + amendment corpus
```

Full explanation: [ARCHITECTURE.md](ARCHITECTURE.md).

## Quick start

### Prerequisites

- Python 3.13
- (Optional) Google Gemini API key for the LLM-backed generator; otherwise the
  extractive generator runs offline.

### Backend

```powershell
# From repo root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
Push-Location backend
..\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
..\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Configure
Copy-Item .env.example .env
# edit .env if you have a GOOGLE_API_KEY

# Ingest the sample corpus
..\.venv\Scripts\python.exe -m legal_rag ingest

# Serve
..\.venv\Scripts\python.exe -m uvicorn legal_rag.interfaces.http.app:app --reload --port 8000
Pop-Location
```

Health check: `http://localhost:8000/api/health`.
Interactive docs: `http://localhost:8000/api/docs`.

### Frontend

```powershell
Push-Location frontend
npm install
npm start
Pop-Location
```

Angular dev server on `http://localhost:4200`, proxied `/api` → backend.

### Docker

```powershell
docker compose up --build
```

Backend on `:8000`, production frontend on `:80`.

## CLI

```powershell
..\.venv\Scripts\python.exe -m legal_rag ingest
..\.venv\Scripts\python.exe -m legal_rag agent "What is the late payment fee?" --strategy compare
..\.venv\Scripts\python.exe -m legal_rag evaluate --k 3
..\.venv\Scripts\python.exe -m legal_rag validate-judge
..\.venv\Scripts\python.exe -m legal_rag race-agent
..\.venv\Scripts\python.exe -m legal_rag race-orchestrator
..\.venv\Scripts\python.exe -m legal_rag mcp-lookup MSA-2021-0142
```

## API

Every endpoint accepts JSON, returns JSON, echoes a `X-Request-ID`, and maps
errors to RFC 7807 problem+json responses.

| Method | Path              | Purpose                                                   |
|--------|-------------------|-----------------------------------------------------------|
| GET    | `/api/health`     | Service configuration + readiness                          |
| POST   | `/api/ask`        | Answer one legal question                                  |
| POST   | `/api/inspect`    | Answer + full retrieval trace (debugging)                  |
| POST   | `/api/ingest`     | Re-ingest all documents in `data/legal/`                   |
| POST   | `/api/upload`     | Upload PDFs → convert to markdown → optional re-ingest     |
| POST   | `/api/agent`      | Run the agent, fixed workflow, or the comparison           |
| POST   | `/api/mcp/lookup` | Discover MCP servers and look up a contract by id          |

### Response contract (fixed)

```json
{
  "answer": "…",
  "reasoning": "…",
  "sources": [{"document": "msa.md", "chunk_id": "msa::003", "excerpt": "…"}],
  "confidence": "high | medium | low",
  "out_of_scope": false
}
```

## Configuration

Every knob is a `pydantic-settings` field on `legal_rag.infrastructure.settings.Settings`
and can be overridden via environment variables (`LEGAL_RAG_*` prefix). See
[`backend/.env.example`](backend/.env.example) for the full list.

## Tests

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest tests/ -v                    # everything
..\.venv\Scripts\python.exe -m pytest tests/unit/                  # pure domain
..\.venv\Scripts\python.exe -m pytest tests/integration/           # services + fakes
..\.venv\Scripts\python.exe -m pytest tests/e2e/                   # HTTP
..\.venv\Scripts\python.exe -m pytest -m "not slow"                # skip real infra
Pop-Location
```

## Observability

- **Structured JSON logs** on stdout (`LEGAL_RAG_LOG_FORMAT=text` for local dev).
- Every HTTP request is assigned a `X-Request-ID` and every log line inside the request carries it in the `request_id` field.
- Token usage per LLM call is logged at `DEBUG`.
- Health endpoint reports the effective config for platform smoke tests.

## Security notes

- No secrets in code. `GOOGLE_API_KEY` and `LEGAL_RAG_API_KEY` come from env vars only.
- API key auth on every endpoint when `LEGAL_RAG_API_KEY` is set.
- Prompt injection is blocked at the query level (`domain/policies.py`) and inside retrieved documents (`sanitize_document_text`).
- Contract drafting requests are refused with a fixed sentinel.

## Extending

New capability → new port in `application/ports.py`, new adapter in
`infrastructure/`, wire in `composition.py`, expose in an interface.
Full checklist in [AGENTS.md](AGENTS.md).
