# LegalRAG

An Angular chat workspace and FastAPI service for searching legal contracts and amendments. Groq writes answers from retrieved passages, and the backend validates citations and quotations before returning them. The chat displays the answer; the API retains supporting evidence. An LLM classifies conversational intent, including casually misspelled greetings, and generates a fresh reply without document retrieval. Document QA generates fresh LLM refusals for unrelated questions and questions with insufficient supporting evidence.

## Features and functionality

- **Document ingestion:** load Markdown, DOCX and text-based PDF contracts, preserve document metadata, and split content into section-aware chunks. Administrators can upload PDFs through the API.
- **Hybrid retrieval:** combine SentenceTransformers embeddings in local, embedded Chroma with lexical search, fuse results using reciprocal rank fusion, and rerank with a cross-encoder.
- **Grounded answers:** retrieve supporting passages, enforce document and clause constraints, and validate source identity, excerpts and quotations. Responses include confidence and an explicit out-of-scope flag.
- **Natural conversation:** use fresh LLM calls for greetings and unsupported questions, with separate sampling settings. Repeated requests can produce different wording; uniqueness is not guaranteed.
- **Agent workflows:** run bounded tool-using agents, compare them with a fixed workflow, and access contract lookup through MCP integrations.
- **Operations and evaluation:** structured logs, request IDs, health endpoints, metrics, automated tests, and separate synthetic RAG evaluation gates.

Document processing follows `load → section-aware chunking → embeddings → persistent Chroma index`. Document questions follow `input guardrails → intent/scope routing → retrieval → fusion and reranking → LLM answer → evidence review and validation`. Social messages bypass retrieval. Answers without sufficient evidence become refusals rather than general-knowledge legal answers.

The default embedding model is `sentence-transformers/all-MiniLM-L6-v2`; reranking uses `cross-encoder/ms-marco-MiniLM-L-6-v2`. Extracted passages and questions used for document answers are sent to the configured Groq service. Confirm that this processing is suitable for your documents before ingesting confidential material. Citation checks support review; they do not establish legal correctness or replace review of the original agreement.

## Project structure

```text
.github/
  workflows/               CI, RAG evaluation, and deployment readiness
  actions/setup-backend/   Shared Python dependency setup
  requirements-ci.txt      CI-only validation tools
  dependabot.yml           Dependency update configuration
backend/
  legal_rag/
    domain/                Entities, clause/page/evidence rules, response schema
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
skills-lock.json           Installed repository skill versions (keep at root)
scripts/
  ci/                      CI gates and local validation helpers
  evaluation/              Developer retrieval comparisons
  README.md                Tool usage and output locations
docs/
  reviews/                 Local review findings
  superpowers/specs/       Superpowers design documents
  superpowers/plans/       Superpowers implementation plans
AGENTS.md                  Contribution rules
ARCHITECTURE.md             Layer design
docker-compose.yml         Local full-stack deployment
Makefile                   Development shortcuts
```

Historical learning notes and generated reports are kept separately. Agents, evaluation workflows, CLI commands, MCP servers, and tests remain part of the application. Supporting review and deployment notes under `docs/` are local files and are not versioned. See [file placement rules](ARCHITECTURE.md#file-placement) before adding or moving files, and [repository tools](scripts/README.md) for validation commands.

## Run with Docker

Prerequisites: Docker with Compose. From the repository root:

```powershell
Copy-Item backend/.env.example backend/.env  # First setup only; do not overwrite an existing file.
# Edit backend/.env: configure GROQ_API_KEY and distinct random
# LEGAL_RAG_API_KEY (reader) and LEGAL_RAG_ADMIN_API_KEY (administrator).
docker compose --env-file backend/.env up -d --build
# Populate the index on first setup, or after changing the corpus:
docker compose exec backend python -m legal_rag.interfaces.cli ingest
```

- Chat: http://localhost
- API docs: http://localhost:8000/api/docs
- Public liveness: http://localhost:8000/api/live
- Detailed health: http://localhost:8000/api/health (reader or administrator key)
- Metrics: http://localhost:8000/metrics

Compose reads backend configuration from `backend/.env`. Passing `--env-file backend/.env` also supplies the reader key to the frontend build. Browser configuration is public; the admin and Groq keys stay on the backend. The backend port is published only on `127.0.0.1`; nginx proxies browser API requests. Model downloads can make the first retrieval request slow. The `backend/data` bind mount preserves documents and the vector index across container recreation; the named `model_cache` volume preserves Hugging Face model downloads.

After editing application code, run `docker compose --env-file backend/.env up -d --build` again. Dependencies are installed before source is copied, so unchanged dependency layers are reused. BuildKit caches pip/npm downloads for dependency-layer rebuilds. The first build after changing requirements or the Dockerfile can still install packages; source-only edits do not require reinstalling them. Keep the same Docker builder and its build cache, and use ordinary builds without `--no-cache` for this workflow. Container restarts alone do not incorporate edited source files. Preserve volumes when stopping the app (`docker compose down`, without `-v`).

The backend image installs CPU PyTorch and the Python runtime dependencies, runs Uvicorn as a non-root user, and exposes port 8000. The frontend image builds Angular with Node.js and serves the compiled assets through nginx. Compose maps the configured reader key to the explicitly public `PUBLIC_READER_TOKEN` frontend build argument; provider and administrator keys stay in the backend runtime environment.

HTTP startup fails unless reader and admin keys are nonempty and distinct. Send the appropriate key in `X-API-Key`: either role can read and query, while `/api/ingest` and `/api/upload` require the admin key. Query parameters do not authenticate requests. For local anonymous reads, explicitly set `LEGAL_RAG_DEVELOPMENT_MODE=true`; writes still require an admin key. CLI commands do not require HTTP credentials. `/api/live` reports only process liveness; detailed health requires reader access in production. Metrics and interactive API documentation remain public; restrict them at the deployment proxy for an external deployment. Shared keys do not provide per-user identity or tenant isolation.

## LLM configuration

Keep `GROQ_API_KEY` in the ignored `backend/.env`. Groq is the answer provider:

| Provider | Settings |
|---|---|
| Groq | `LEGAL_RAG_LLM_PROVIDER=groq`, `GROQ_API_KEY`, `LEGAL_RAG_GROQ_MODEL` |

Document answers require a working Groq model; provider failures return errors, and answers that still fail evidence validation after one correction attempt return HTTP 422. Leave `LEGAL_RAG_LLM_BASE_URL` unset to use Groq's endpoint. The `openai` Python package supplies Groq's compatible API transport; it does not require an OpenAI API key. All runtime settings are defined in [Settings](backend/legal_rag/infrastructure/settings.py); examples are in [backend/.env.example](backend/.env.example).

Conversational routing uses the LLM rather than a greeting spelling list. Classification runs at temperature zero, followed by a separate generated reply at `LEGAL_RAG_GREETING_TEMPERATURE` (default `0.8`). Input guardrails run first; explicit document scopes retain grounded QA. Invalid classification falls back to document QA, while invalid conversational output returns an error. Every request makes fresh model calls; wording may occasionally repeat without conversation-history tracking.

For substantive document answers, an additional LLM call selects cited chunk IDs containing omitted applicability conditions. The code appends the original excerpt for each selected ID as a document-labeled quotation; the model cannot supply new condition text. The original answer and sources remain unchanged. The generator validates the final citations and quotations before returning the answer. The extra model call adds latency and token usage; both calls are included in generation usage totals.

After changing backend-only configuration, recreate the backend:

```powershell
docker compose --env-file backend/.env up -d --build backend
```

After rotating the reader key, rebuild both services with the full Compose command above; restarting the frontend does not replace credentials embedded in its JavaScript bundle.

## Configuration reference

Copy [backend/.env.example](backend/.env.example) to `backend/.env` once and edit it locally. Settings load `.env` relative to the working directory, so run local backend and CLI commands from `backend/`. Environment variables override file values. Never commit the populated file.

| Variable | Purpose / default |
|---|---|
| `GROQ_API_KEY` | Required provider credential for LLM calls; backend only. |
| `LEGAL_RAG_GROQ_MODEL` | Groq model; `openai/gpt-oss-20b`. |
| `LEGAL_RAG_API_KEY` | Reader credential; public when embedded in the frontend. |
| `LEGAL_RAG_ADMIN_API_KEY` | Separate administrator credential; backend only. |
| `LEGAL_RAG_DEVELOPMENT_MODE` | `false`; explicitly enable for local anonymous reads. |
| `LEGAL_RAG_DOCS_DIR` | Corpus directory; defaults to `backend/data/shared-corpus/contracts`. |
| `LEGAL_RAG_CHROMA_DIR` | Persistent index directory; defaults to `backend/data/chroma`. |
| `LEGAL_RAG_HYBRID_ENABLED` | Enable dense plus lexical retrieval; `true`. |
| `LEGAL_RAG_TOP_K_CANDIDATES` / `LEGAL_RAG_TOP_N_ANSWERS` | Retrieval/reranking limits. Settings defaults are `20` / `8`; the example `.env` overrides them to `5` / `3`. |
| `LEGAL_RAG_GREETING_TEMPERATURE` | Social reply variation; `0.8`. |
| `LEGAL_RAG_UNSUPPORTED_RESPONSE_TEMPERATURE` | Refusal variation; `0.7`. |
| `LEGAL_RAG_CORS_ORIGINS` | JSON array of permitted browser origins for direct cross-origin API access. |
| `LEGAL_RAG_API_URL` | Frontend build setting; `/api` by default. For a separately hosted API, include its `/api` path. |

The two path settings resolve inside the container when using Docker; use paths such as `/app/data/...` for overrides there. `LEGAL_RAG_API_URL` is read by the frontend build script, not backend Settings. See [Settings](backend/legal_rag/infrastructure/settings.py) for all limits, model names, agent budgets and timeouts.

[frontend/.env.example](frontend/.env.example) documents the two public frontend build variables. The frontend script reads the process environment; copying that template to `.env` alone does not load it. Set variables in the terminal as shown below, or in your hosting provider's build settings. Compose supplies the reader key from `backend/.env` when invoked with `--env-file backend/.env`. Keep provider and administrator keys out of frontend settings, command output and build artifacts. Private `.env` variants are excluded by Git and Docker ignore rules; the example templates intentionally contain no credentials.

## LLM monitoring with Langfuse

Langfuse monitoring is optional and disabled by default. It instruments the shared LLM client used by document answers, evidence review, conversational routing, greetings, refusals and judge calls. HTTP worker operations and CLI workflows have parent execution spans, with child generations recording model, sampling parameters, duration, token usage and outcome. Each workflow receives an internally generated trace identity; client-supplied request IDs do not control trace parenting.

HTTP workflows use stable operation names such as `answer-question`, `inspect-retrieval` and `run-legal-agent`. Retrieval appears beneath its workflow as a `retrieve-context` observation of type `retriever`; agent execution uses type `agent`, and MCP lookup uses type `tool`. This makes requests and slow retrieval steps easier to find without exporting document text. Tests explicitly disable monitoring and ignore the private `.env`; real-SDK tests use an in-memory exporter.

Create a Langfuse project in your chosen region or self-hosted deployment. The pinned Python SDK v5 requires Langfuse Cloud or self-hosted Langfuse **4.59.0 or later**; see the [official compatibility guidance](https://langfuse.com/docs/observability/sdk/upgrade-path/python-v4-to-v5). Add the following to your private `backend/.env`, using the project URL and keys from its settings:

```dotenv
LEGAL_RAG_LANGFUSE_ENABLED=true
LEGAL_RAG_LANGFUSE_BASE_URL=https://your-approved-langfuse-host.example
LEGAL_RAG_LANGFUSE_PUBLIC_KEY=
LEGAL_RAG_LANGFUSE_SECRET_KEY=
LEGAL_RAG_LANGFUSE_ENVIRONMENT=development
LEGAL_RAG_LANGFUSE_CAPTURE_CONTENT=false
```

Fill both blank key values locally; the host above is an example, not a provisioned service. These settings are backend-only and use this application's `LEGAL_RAG_` prefix. Recreate the backend after configuration changes with `docker compose --env-file backend/.env up -d --build backend`, or restart the local backend process. Changing the dependency list triggers the necessary package-install layer once; later code-only rebuilds reuse it.

With `CAPTURE_CONTENT=false`, monitoring omits prompts, responses, retrieved passages, document identifiers and tool arguments. To track prompt and generated-response content, explicitly set `LEGAL_RAG_LANGFUSE_CAPTURE_CONTENT=true` for an approved project and corpus. That exports legal text to the configured destination. Captured copies are bounded by `LEGAL_RAG_LANGFUSE_MAX_CONTENT_CHARS` (default 12000), with configured credentials and common credential fields/patterns redacted. This does not detect all sensitive content. Monitoring does not change the answer, evidence validation or API response schema.

Generate a synthetic greeting through `/api/ask`, then inspect its workflow and generation observations in your Langfuse project. In metadata mode, input/output should be absent; with full capture enabled, inspect a synthetic prompt and reply before using real documents. Exports are asynchronous, so allow time for ingestion. HTTP shutdown and CLI completion perform bounded best-effort cleanup; forced shutdown or an unavailable destination can lose observations. Monitoring failures do not retry the LLM or turn a successful answer into a failed request. A successful application response does not prove Langfuse delivery; verify the dashboard separately.

For programmatic verification, use the official `langfuse-cli` observations API with a bounded time range and `--trace-id`; request the `model` and `usage` fields to audit model names and tokens. This uses the current Observations API v2 rather than deprecated trace-list endpoints. See [Langfuse tracing best practices](https://langfuse.com/docs/observability/best-practices) and the [official AI skill](https://github.com/langfuse/skills).

## Local development

Python 3.13 and Node.js 22 are used in CI and Docker. The frontend uses Angular 21.2 and TypeScript 5.9; local Node.js must be at least 22.12.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
# First setup only, if Docker setup has not already created this file:
# Copy-Item backend/.env.example backend/.env
# Edit backend/.env and supply the provider, reader and administrator keys.
Push-Location backend
..\.venv\Scripts\python.exe -m legal_rag.interfaces.cli ingest
..\.venv\Scripts\python.exe -m uvicorn legal_rag.interfaces.http.app:app --reload --port 8000
Pop-Location
```

In another terminal:

```powershell
Push-Location frontend
npm ci
# Use the reader key configured in backend/.env; never use the administrator key.
$env:LEGAL_RAG_API_KEY = '<your-reader-key>'
node scripts/set-env.js
npm start -- --configuration production
Pop-Location
```

The Angular development server is available at http://localhost:4200 and proxies `/api` to port 8000. The production configuration loads the generated reader key. For anonymous local reads instead, explicitly enable `LEGAL_RAG_DEVELOPMENT_MODE=true` on the backend and use `npm start` with the default development configuration. Administrator credentials are still required for writes. PowerShell examples use the Windows Python launcher; on other platforms, use `python3.13 -m venv .venv` and `.venv/bin/python` in place of the Windows executable paths.

The first ingestion downloads embedding models and builds the index; it can take longer than later runs. To add documents locally, place supported files in the configured corpus directory and run `ingest` again. The HTTP upload endpoint accepts PDFs only and converts extracted text to Markdown before ingestion. Scanned images require text extraction outside this application; no OCR pipeline is configured.

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

Backend tests are organized by responsibility: `tests/unit/` covers domain rules and adapters, `tests/integration/` checks workflows with in-memory fakes, and `tests/e2e/` exercises the HTTP contract and infrastructure boundaries. Coverage includes grounded and unsupported response generation, conversational routing, clause references, evidence scope, citation validation and error handling. To run only unit and integration tests, use `python -m pytest tests/unit tests/integration -m "not slow"` from `backend/` with the virtual environment active. Run `python -m pytest tests/` for the full suite, including slow infrastructure tests; the latter needs the local Chroma and SentenceTransformers dependencies and model weights.

For the same quality and synthetic RAG gates used by CI, run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .github/requirements-ci.txt
.\.venv\Scripts\python.exe scripts/ci/quality_checks.py
.\.venv\Scripts\python.exe scripts/ci/evaluate_rag.py
```

The quality gate includes Ruff linting/format checks and scoped mypy checks. RAG evaluation uses synthetic fixtures and scripted answers to check retrieval, evidence and citation behavior without legal documents or provider keys. Optional `--real-models` uses local embedding/reranking models and can download model weights; it still does not assess live LLM factual accuracy. See [repository tools](scripts/README.md) for additional checks.

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

`validate-judge` summarizes the human labels and reports `not_evaluated` with null agreement values. The fixture has no saved model predictions, so it cannot establish judge agreement or before/after improvement. Race commands report their actual runs separately. Evaluation file access is provided through the container's evaluation I/O port. MCP lookups have a total deadline controlled by `LEGAL_RAG_MCP_TIMEOUT_SECONDS` (default 30 seconds).

## API response contract

Use `X-API-Key` on authenticated requests. The principal endpoints are:

| Method and route | Function | Access |
|---|---|---|
| `POST /api/ask` | Answer a question; optional `document_type` is `contract` or `amendment`. | Reader or administrator |
| `POST /api/inspect` | Return retrieved chunks and the structured answer. | Reader or administrator |
| `POST /api/ingest` | Re-ingest the configured corpus. | Administrator |
| `POST /api/upload` | Accept multipart `files` containing PDFs; `auto_ingest` defaults to `true`. | Administrator |
| `POST /api/agent` | Run `agent`, `fixed` or `compare` strategy. | Reader or administrator |
| `POST /api/mcp/lookup` | Look up a `contract_id` through MCP. | Reader or administrator |
| `GET /api/live` | Process liveness. | Public |
| `GET /api/health` | Configuration health details. | Reader or administrator |

Example from PowerShell after ingestion, using a reader key already set in the terminal:

```powershell
$headers = @{ 'X-API-Key' = $env:LEGAL_RAG_API_KEY }
$body = @{ question = 'What is the late payment fee in MSA-2026-014?' } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8000/api/ask -Method Post `
    -Headers $headers -ContentType 'application/json' -Body $body
```

The response shape is shown below; the text and citation are illustrative, not extracted legal facts:

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

For `/api/ask` and `/api/inspect`, unsupported questions receive an LLM-generated refusal with `out_of_scope: true`, `sources: []`, and `confidence: "low"`. The refusal model receives only the reason, without the question or document passages. Each request generates new wording; phrasing can occasionally repeat because no conversation history is stored. Set `LEGAL_RAG_UNSUPPORTED_RESPONSE_TEMPERATURE` (default `0.7`, greater than `0` and at most `2`) independently of grounded answer generation. Conservative output checks require limitation wording and reject obvious citations, quotations, links and numeric claims; they are not a general factual verifier. Provider failures return errors, and invalid refusal output returns HTTP 502 after one correction attempt. Input guardrail blocks remain fixed safe responses; direct generator and agent contracts retain their internal out-of-scope sentinel.

## Deployment and maintenance

- Read [architecture](ARCHITECTURE.md) and [contribution rules](AGENTS.md) before modifying the backend. Repository skills live under `.agents/skills/`.
- GitHub Actions workflows live in `.github/workflows/`; local validation commands are documented in [scripts/README.md](scripts/README.md).
- Keep provider credentials and `LEGAL_RAG_ADMIN_API_KEY` on the backend. Only the reader `LEGAL_RAG_API_KEY` may enter the public frontend build; rebuild the frontend after rotating it.
- The Compose data mount preserves documents and indexes. Successful re-ingestion removes obsolete chunks for sources in that batch. Removing a file does not automatically revoke its indexed source. Chroma upsert and stale-chunk cleanup are separate operations; preserve backups and avoid concurrent index writers during replacement.
- Health reports configuration, not model access or index readiness. Verify a known question and its sources after deployment.
- CI audits frontend production dependencies. At the 2026-11-08 review, the Angular 21 upgrade removed production advisories and all high/critical entries in the full npm audit; 21 moderate development-toolchain entries remained in the CLI/build dependencies. These packages are excluded from the nginx runtime image; development-server exposure requires separate review.
- For public deployment, use TLS and authentication, restrict administrative endpoints, and configure the frontend origin.

Markdown in Git is limited to README files, contribution/architecture instructions, skill resources, and the contract corpus. Other supporting Markdown stays local through `.gitignore`.
