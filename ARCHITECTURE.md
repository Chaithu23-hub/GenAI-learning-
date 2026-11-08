# Architecture

LegalRAG follows **Clean Architecture** (a.k.a. Hexagonal / Ports-and-Adapters). The rule is
one-way: **dependencies point inward** — Domain has no imports from any other layer,
Application depends only on Domain, Infrastructure and Interfaces depend on both, and
nothing outside `interfaces/` may import a framework (FastAPI, Typer, MCP).

```
┌────────────────────────────────────────────────────────────────────────────┐
│  interfaces/          HTTP · CLI · MCP servers  (delivery, framework code) │
├────────────────────────────────────────────────────────────────────────────┤
│  infrastructure/      Chroma · SentenceTransformers · Groq · MCP client    │
│                       pydantic-settings · structlog                        │
├────────────────────────────────────────────────────────────────────────────┤
│  application/         Services (use cases) + Ports (Protocols) + DTOs      │
├────────────────────────────────────────────────────────────────────────────┤
│  domain/              Entities · Value Objects · Policies · Response schema│
└────────────────────────────────────────────────────────────────────────────┘
                             ← dependencies point inward
```

## Package layout

```
backend/
├── legal_rag/                      # Clean Architecture package
│   ├── domain/                     # Pure business rules; NO I/O, NO frameworks
│   │   ├── entities.py             # Chunk, Document, RetrievedChunk, Citation, Answer, AgentState
│   │   ├── policies.py             # Guardrails, injection defence, completeness, trajectory audit
│   │   ├── evidence.py             # Bind explicit document/clause references to evidence
│   │   ├── pages.py                # Validate cited page lists and ranges
│   │   ├── response_schema.py      # JSON Schema + validate_response
│   │   └── exceptions.py           # DomainError, GuardrailBlocked, OutOfScope...
│   │
│   ├── application/                # Orchestration; depends only on domain
│   │   ├── __init__.py             # Facade — single import surface for services
│   │   ├── ports.py                # Protocol interfaces (VectorStore, Embedder, Reranker,
│   │   │                           #   LLMClient, DocumentSource, MCPHostPort, Clock)
│   │   ├── agents/                 # Agent definitions
│   │   │   ├── legal_agent.py      # LegalAgent, FixedWorkflow, compare_strategies
│   │   │   └── orchestrator.py     # Orchestrator (planner + workers + synthesiser)
│   │   └── workflows/              # Multi-step use cases
│   │       ├── ingestion.py
│   │       ├── retrieval.py
│   │       ├── generation.py       # LLMGenerator: Groq answers, evidence checks and correction
│   │       ├── qa.py               # QaService (guardrail → filter → retrieve → generate)
│   │       ├── race.py             # AgentRace, MultiAgentRace, MeteredLegalAgent
│   │       ├── judge.py            # JudgeService + deterministic assertions
│   │       ├── evaluation.py       # hit-rate@k
│   │       ├── corpus_lookup.py    # Source-backed contract and clause lookup
│   │       └── mcp_lookup.py
│   │
│   ├── infrastructure/             # Concrete adapters; implements ports
│   │   ├── settings.py             # pydantic-settings — 12-factor config
│   │   ├── errors.py               # Infrastructure exceptions (transient / permanent)
│   │   ├── execution.py            # Bounded blocking work with request context propagation
│   │   ├── observability/
│   │   │   └── logging.py          # Structured JSON logging + request-id context
│   │   ├── vector_store/
│   │   │   └── chroma.py           # ChromaVectorStore (implements VectorStore port)
│   │   ├── embeddings/
│   │   │   ├── sentence_transformer_embedder.py
│   │   │   └── cross_encoder_reranker.py
│   │   ├── llm/groq.py              # Groq via OpenAI-compatible SDK transport
│   │   ├── documents/
│   │   │   ├── shared_corpus_loader.py # Markdown, DOCX and corpus PDFs
│   │   │   ├── pdf_loader.py       # Isolated upload extraction adapter
│   │   │   ├── pdf_worker.py       # Child-process parser entry point
│   │   │   └── process_limits.py   # Parser process memory limits
│   │   ├── prompts/                # Versioned prompt templates
│   │   │   ├── qa_system.py
│   │   │   ├── orchestrator_prompts.py
│   │   │   └── judge_prompts.py
│   │   ├── mcp/stdio_host.py
│   │   ├── chunking/section_chunker.py
│   │   └── retrieval/rrf.py
│   │
│   ├── interfaces/                 # Delivery mechanisms
│   │   ├── http/                   # FastAPI: app, routers, DI, errors, middleware, schemas
│   │   ├── cli/                    # Typer CLI
│   │   └── mcp_servers/            # clause_search + contract_repository
│   │
│   └── composition.py              # Composition Root: builds services from settings
│
├── tests/
│   ├── unit/                       # Pure domain
│   ├── fakes/                      # In-memory port implementations
│   ├── integration/                # Services wired against fakes
│   ├── e2e/                        # HTTP, subprocess, filesystem and CI-tool checks
│   └── slow/                       # Real model/database and format-parity checks
└── data/                           # Chroma index and markdown corpus
```

## File placement

New files follow the existing dependency layers; keep a module with the capability it implements.

| Responsibility | Location | Examples |
| --- | --- | --- |
| Pure legal evidence rules | `backend/legal_rag/domain/` | `evidence.py`, `pages.py` |
| Use cases depending on ports | `backend/legal_rag/application/workflows/` | `corpus_lookup.py` |
| External I/O and execution adapters | `backend/legal_rag/infrastructure/` | `execution.py`, `documents/pdf_worker.py`, `documents/process_limits.py` |
| Framework endpoints and DTOs | `backend/legal_rag/interfaces/` | HTTP routers, CLI, MCP servers |
| Pure rule tests and in-memory substitutes | `backend/tests/unit/`, `backend/tests/fakes/` | `test_evidence_associations.py`, `documents.py` |
| Service and adapter coordination tests without disk/network | `backend/tests/integration/` | Ingestion versions, lexical cache, executor tests |
| Boundary checks requiring filesystem or subprocesses | `backend/tests/e2e/` | CI helpers, offline benchmark, PDF worker, HTTP/MCP tests |
| Real dependencies and format fixtures | `backend/tests/slow/` | Chroma, embedding/reranking models, document-format parity |
| Workflow definitions and shared action setup | `.github/workflows/`, `.github/actions/` | CI, RAG evaluation, deployment readiness, setup-backend |
| CI-only dependencies and dependency updates | `.github/` | `requirements-ci.txt`, `dependabot.yml` |
| CI gate implementations | `scripts/ci/` | Quality, tests, security, workflow validation |
| Developer evaluation tools | `scripts/evaluation/` | `measure_retrieval.py` |
| Local review findings and planning records | `docs/reviews/`, `docs/superpowers/specs/`, `docs/superpowers/plans/` | Dated review, approved design and implementation plan |
| Installed repository skills | `.agents/skills/` | Keep `skills-lock.json` at repository root for the skill manager |

Generated evaluation output belongs in ignored `backend/data/evaluation/generated/`; the persistent index belongs in ignored `backend/data/chroma/`. Keep test fixtures in the repository, outside the production image. Keep local dependencies and model caches in their existing ignored locations. Superpowers plugin files remain in the plugin manager's installation directory; project designs and plans stay under `docs/superpowers/`.

Before deleting a file, check its callers, dynamic imports, CLI/subprocess entry points, workflow references, tests and Docker inputs. An untracked file is not necessarily disposable: new source modules and regression tests still need to be included when the changes are committed. Update imports, commands, path filters and documentation together when moving an active file.

## Design decisions

### Ports vs Adapters
Every external dependency (vector store, embedder, reranker, LLM, MCP host, filesystem,
clock) is a **Protocol** in `application/ports.py`. Services accept ports through
constructor injection. Concrete implementations live in `infrastructure/` and are
never imported by services.

Benefits:
- Tests replace ports with in-memory fakes — no monkeypatching, no `@lru_cache`
  contamination, no Chroma files.
- Swapping the vector store or embedding provider is one
  new adapter, no service changes.

### Composition root
`legal_rag/composition.py` wires ports → adapters → services from a single
`Settings` object. Interfaces (HTTP, CLI, MCP) each build their container once at
startup and hand services down through DI.

Prompt and tool definitions have one source under `infrastructure/prompts/`.
Generation, orchestration, and judging import those definitions rather than
keeping inline copies that can drift from the version registry.

### Config
`infrastructure/settings.py` uses `pydantic-settings.BaseSettings`. Env vars are
read once, validated at startup, and passed as an immutable object. No module-level
env reads. No hard-coded API keys. `.env.example` documents the surface.

### Logging & observability
`infrastructure/observability/logging.py` configures **structured JSON logging** on the root
logger. Every request gets an id via ASGI middleware; every service logs at
INFO with `extra={...}`. Token usage, latency, and cost are logged, never
printed to stderr. LLM prompts are logged at DEBUG only.

### Error handling
- `domain/exceptions.py` — business-rule failures (`GuardrailBlocked`,
  `OutOfScope`, `SchemaValidationError`).
- `infrastructure/errors.py` — I/O failures (`VectorStoreUnavailable`,
  `LLMBackendError`, `TransientLLMError` — for retry classification).
- HTTP layer maps each family to a proper status code via handlers in
  `interfaces/http/errors.py`. Never leaks stack traces to the client.

### Testing pyramid
- **Unit** — pure domain (chunking, guardrails, schema, policies).
- **Contract** — every port has a fake adapter and a shared test suite that both
  fake and real adapter must pass.
- **Integration** — services wired against fakes.
- **E2E** — FastAPI `TestClient` against a real composition root with fake infra.
- **Slow** (marked `@pytest.mark.slow`) — real Chroma + real embeddings.

### Entry points and evaluation data

HTTP starts at `legal_rag.interfaces.http.app:app`. The CLI runs through
`python -m legal_rag.interfaces.cli` or the installed `legal-rag` command.
MCP entry points live under `legal_rag.interfaces.mcp_servers`.

Required evaluation labels are in `backend/data/evaluation/labels.json` and are
included in the backend image. Settings controls that input path and the ignored
`backend/data/evaluation/generated/` report directory. Historical reports and
unused learning material are preserved outside the production tree. Supporting
maintenance and review notes remain local under the ignored `docs/` directory.

### Document answers

All document questions, including numbered-clause requests, use hybrid retrieval
and the configured Groq model. Retrieved metadata accompanies the model context.
The backend checks source identity, verbatim excerpts, recognized quotations,
clause references and physical page claims before returning the answer. Invalid
answers receive one correction attempt and then raise `SchemaValidationError`.
Provider failures propagate through the infrastructure error taxonomy; there is
no offline answer generator or excerpt fallback. Greeting-only messages call the
configured LLM conversation adapter once, with instructions to match the user's
salutation without inventing legal facts or citations. They skip document
retrieval and return no sources. Provider errors propagate; invalid model replies
return HTTP 502; a missing conversation adapter returns HTTP 500. There is no
static greeting fallback. A greeting followed by a contract question retains
normal grounded QA. Input refusals remain
part of QA routing. The obsolete static greeting_answer setting has been removed.

### Embedded Chroma security assessment

The vector-store adapter forces `chromadb.api.rust.RustBindingsAPI` with implicit
Chroma `.env` loading disabled. It passes `embedding_function=None`; embeddings
come from the application's existing embedder port. The Chroma persistence
directory and restored indexes must be trusted local inputs. Disabling the
embedding function does not make attacker-written persisted configuration safe.
Do not start a Chroma HTTP server or share the index with untrusted writers under
this assessment.

On 2026-11-08, repository owner **Chaithu23-hub** approved a deployment applicability
assessment for **chromadb 1.5.9**, expiring at **2026-12-08 00:00 UTC**. It covers
only these server-boundary findings:

| Advisory | Server boundary outside the reviewed embedded deployment |
| --- | --- |
| [GHSA-f4j7-r4q5-qw2c](https://github.com/advisories/GHSA-f4j7-r4q5-qw2c) / PYSEC-2026-311 / CVE-2026-45829 | Remote collection creation and model configuration |
| [GHSA-2wm9-hf6c-p5cr](https://github.com/advisories/GHSA-2wm9-hf6c-p5cr) / PYSEC-2026-3813 / CVE-2026-45830 | Server cross-tenant authorization |
| [GHSA-36p7-vc44-83pf](https://github.com/advisories/GHSA-36p7-vc44-83pf) / PYSEC-2026-3814 / CVE-2026-45833 | Remote collection update and model configuration |
| [GHSA-xph7-9rjv-w5fr](https://github.com/advisories/GHSA-xph7-9rjv-w5fr) / PYSEC-2026-3815 / CVE-2026-45831 | Server RBAC resource scoping |

Chroma remains an affected dependency; this assessment does not claim an upstream
patch. `scripts/ci/security_checks.py` still audits every installed package and
reports all findings, with assessed non-applicable and blocking counts separately.
Only the exact approved identities/aliases and package version qualify. A newly
listed fix requires an upgrade rather than reuse of this exception. Unknown
findings, changed versions, incomplete or failed scans, expired approval, or a
changed fingerprint of runtime/deployment files block CI. The fingerprint
normalizes LF/CRLF to support Windows and Linux checkouts. It also covers added
default Compose filenames and automatic override files. Every fingerprinted
file change selects the security job, including frontend build/deployment files.

Changing reviewed runtime source, dependency manifests, workflows, Docker/Compose
or other deployment entry points requires a fresh scope review before updating
`REVIEWED_SCOPE_SHA256`. Do not regenerate it merely to clear CI. Application
authorization, confidential documents and citation checks remain independent
security requirements; this assessment does not establish tenant isolation.

## Request lifecycle — `POST /api/ask`

```
HTTP request
   │
   ▼
interfaces/http/routers/qa.py           (Pydantic validation)
   │
   ▼
interfaces/http/dependencies.py         (resolve QaService from composition root)
   │
   ▼
application/workflows/qa.py             (guardrails → route → retrieve → generate)
   │       │           │           │
   │       ▼           ▼           ▼
   │    domain      RetrievalSvc  GeneratorPort
   │   policies         │
   │                    ▼
   │             infrastructure/persistence + embeddings + retrieval/rrf
   │
   ▼
domain/response_schema.py               (validate against JSON Schema)
   │
   ▼
Pydantic HTTP response
```
