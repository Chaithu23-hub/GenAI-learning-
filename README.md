# LegalRAG

A local legal-document assistant with a FastAPI backend and Angular frontend. Answers are
grounded in contract and amendment passages retrieved from the local document library, with
source citations and guardrails against out-of-scope, injection, and drafting requests.

## Run locally

### Backend

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Health check: `http://localhost:8000/api/health`

For ingestion, evaluation, and agent workflows:

```powershell
..\.venv\Scripts\python.exe cli.py ingest
..\.venv\Scripts\python.exe cli.py evaluate
..\.venv\Scripts\python.exe cli.py agent "What is the late payment fee?" --strategy compare
Pop-Location
```

### Frontend

```powershell
Push-Location frontend
npm install
npm start
```

Open `http://localhost:4200`. The Angular dev server proxies `/api` requests to the backend.
Extractive answers work without an LLM key; Gemini mode requires `GOOGLE_API_KEY`.

## RAG pipeline

- Ingestion: markdown documents are chunked, embedded, and stored in Chroma.
- Retrieval: dense and BM25-style sparse results are fused with reciprocal rank fusion, then
  reranked with a cross-encoder.
- Generation: extractive mode is the offline default; optional Gemini generation validates
  grounded JSON responses and citations.
- Storage: persistence adapters live in `backend/legal_assistant/stores/`.
- Safety: query guardrails reject prompt injection, unsupported questions, and drafting requests.

The fixed response contract contains `answer`, `reasoning`, `sources`, `confidence`, and
`out_of_scope`. Source entries include the document, chunk ID, and supporting excerpt.

## Project layout

- `backend/app/` - FastAPI routes, middleware, and schemas
- `backend/legal_assistant/ingestion/` - chunking, embedding, and indexing orchestration
- `backend/legal_assistant/stores/` - Chroma and lexical-search adapters
- `backend/legal_assistant/retrieval/` - dense, sparse, hybrid fusion, and reranking
- `backend/legal_assistant/generation/` - grounded answer generation and validation
- `backend/legal_assistant/safety/` - query and agent guardrails
- `backend/legal_assistant/evaluation/` - retrieval and answer-quality evaluation
- `backend/legal_assistant/agent/` - agent workflows and MCP host integration
- `backend/mcp_servers/` - MCP tool servers
- `backend/data/legal/` - sample contracts and amendments
- `frontend/src/` - Angular application
- `eval/` - evaluation evidence and MCP artifacts

## Setup

Python 3.13 is required. From the repository root:

```powershell
.venv\Scripts\Activate.ps1
Push-Location backend
..\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
Pop-Location
```

The first ingestion or query downloads the sentence-transformer and cross-encoder models.

## Tests

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest tests
Pop-Location
```

## Docker

```powershell
docker compose up --build
```

Docker serves the API on port `8000` and the production frontend on port `80`.