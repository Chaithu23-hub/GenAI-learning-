# LegalRAG

An Angular chat workspace and FastAPI service for searching legal contracts and amendments. Groq writes answers from retrieved passages, and the backend validates citations and quotations before returning them. The chat displays the answer; the API retains supporting evidence. Questions outside document QA receive a fixed refusal.

## Project structure

```text
.github/workflows/          CI: backend lint/tests and frontend build/tests
backend/
  legal_rag/
    domain/                Entities, policies, response schema, exceptions
    application/           Ports, agents, and workflows
    infrastructure/        LLM, retrieval, documents, settings, observability
    interfaces/            HTTP API, CLI, and MCP servers
    composition.py         Dependency injection container
  data/
    shared-corpus/         Shared Markdown, DOCX, PDF contracts and golden cases
    evaluation/labels.json Labelled cases used by judge and race commands
    chroma/                Local vector index (ignored by Git)
  tests/                   Unit, integration, HTTP, and slow infrastructure tests
  requirements.txt         Runtime dependencies
  requirements-dev.txt     Development/test dependencies
frontend/
  src/app/                 Chat UI, state, API client, interceptors, Markdown rendering
  scripts/                 Build-time environment generation
  public/                  Static assets
  Dockerfile               Angular build and nginx runtime
  nginx.conf               Same-origin API proxy and SPA routing
.agents/skills/            Repository skills
AGENTS.md                  Contribution rules
ARCHITECTURE.md             Layer design
docker-compose.yml         Local full-stack deployment
Makefile                   Development shortcuts
```

Historical learning notes and generated reports are kept separately. Agents, evaluation workflows, CLI commands, MCP servers, and tests remain part of the application. Supporting review and deployment notes under `docs/` are local files and are not versioned.

## Run with Docker

Prerequisites: Docker with Compose. From the repository root:

```powershell
Copy-Item backend/.env.example backend/.env  # First setup only; do not overwrite an existing file.
# Edit backend/.env and configure GROQ_API_KEY.
docker compose up -d --build
# Populate the index on first setup, or after changing the corpus:
docker compose exec backend python -m legal_rag.interfaces.cli ingest
```

- Chat: http://localhost
- API docs: http://localhost:8000/api/docs
- Health: http://localhost:8000/api/health
- Metrics: http://localhost:8000/metrics

Compose reads backend configuration from `backend/.env`. The root `.env` is not needed for application configuration. Model downloads can make the first retrieval request slow. The `backend/data` bind mount preserves documents and the vector index across container recreation.

## LLM configuration

Keep `GROQ_API_KEY` in the ignored `backend/.env`. Groq is the answer provider:

| Provider | Settings |
|---|---|
| Groq | `LEGAL_RAG_LLM_PROVIDER=groq`, `GROQ_API_KEY`, `LEGAL_RAG_GROQ_MODEL` |

Document answers require a working Groq model; provider failures return errors, and answers that still fail evidence validation after one correction attempt return HTTP 422. Leave `LEGAL_RAG_LLM_BASE_URL` unset to use Groq's endpoint. The `openai` Python package supplies Groq's compatible API transport; it does not require an OpenAI API key. All runtime settings are defined in [Settings](backend/legal_rag/infrastructure/settings.py); examples are in [backend/.env.example](backend/.env.example).

After changing backend configuration:

```powershell
docker compose up -d --build backend
docker compose restart frontend
```

## Local development

Python 3.13 and Node.js 20 are used in CI and Docker.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
Push-Location backend
..\.venv\Scripts\python.exe -m uvicorn legal_rag.interfaces.http.app:app --reload --port 8000
Pop-Location
```

In another terminal:

```powershell
Push-Location frontend
npm ci
npm start
Pop-Location
```

The Angular development server uses `/api` through its proxy to port 8000.

## Validation

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest -m "not slow"
..\.venv\Scripts\python.exe -m ruff check legal_rag tests
Pop-Location
Push-Location frontend
npm run build
npm test -- --watch=false --browsers=ChromeHeadless
Pop-Location
```

Chrome must be installed for `ChromeHeadless`; `CHROME_BIN` may point to another compatible Chromium executable. Slow backend tests exercise real infrastructure and are excluded from normal CI. CI installs `requirements-dev.txt`; the runtime image installs `requirements.txt`.

## CLI and integrations

Run from `backend/` with the virtual environment active:

```powershell
python -m legal_rag.interfaces.cli --help
python -m legal_rag.interfaces.cli ingest
python -m legal_rag.interfaces.cli agent "What is the late payment fee?" --strategy compare
python -m legal_rag.interfaces.cli evaluate --k 3
python -m legal_rag.interfaces.cli.evaluate_shared_corpus --provider groq
python -m legal_rag.interfaces.cli validate-judge
python -m legal_rag.interfaces.cli race-agent
python -m legal_rag.interfaces.cli race-orchestrator
python -m legal_rag.interfaces.cli mcp-lookup MSA-2021-0142
```

Judge/race labels live under `backend/data/evaluation/`. Generated race reports go to its ignored `generated/` directory. These paths can be overridden with `LEGAL_RAG_EVALUATION_LABELS_PATH` and `LEGAL_RAG_EVALUATION_ARTIFACT_DIR`.

## API response contract

```json
{
  "answer": "The direct response to the question.",
  "reasoning": "Brief supporting evidence summary.",
  "sources": [{"document": "msa.md", "chunk_id": "msa::003", "excerpt": "Supporting passage."}],
  "confidence": "high",
  "out_of_scope": false
}
```

The API retains evidence for audit and integration use. The chat displays only `answer`. Errors use problem+json and include request IDs. See Swagger for all HTTP routes, including ingestion, upload, inspection, agents, and MCP lookup.

## Deployment and maintenance

- Read [architecture](ARCHITECTURE.md) and [contribution rules](AGENTS.md) before modifying the backend. Repository skills live under `.agents/skills/`.
- Keep provider credentials on the backend. `LEGAL_RAG_API_KEY` is a shared API gate; it does not provide per-user identity or tenant isolation.
- The Compose data mount preserves documents and indexes. Back up this data; ingestion upserts do not delete obsolete chunks.
- Health reports configuration, not model access or index readiness. Verify a known question and its sources after deployment.
- For public deployment, use TLS and authentication, restrict administrative endpoints, and configure the frontend origin.

Markdown in Git is limited to README files, contribution/architecture instructions, skill resources, and the contract corpus. Other supporting Markdown stays local through `.gitignore`.
