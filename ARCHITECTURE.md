# Architecture

LegalRAG follows **Clean Architecture** (a.k.a. Hexagonal / Ports-and-Adapters). The rule is
one-way: **dependencies point inward** — Domain has no imports from any other layer,
Application depends only on Domain, Infrastructure and Interfaces depend on both, and
nothing outside `interfaces/` may import a framework (FastAPI, Typer, MCP).

```
┌────────────────────────────────────────────────────────────────────────────┐
│  interfaces/          HTTP · CLI · MCP servers  (delivery, framework code) │
├────────────────────────────────────────────────────────────────────────────┤
│  infrastructure/      Chroma · SentenceTransformers · OpenAI · MCP client  │
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
│   │   ├── response_schema.py      # JSON Schema + validate_response
│   │   └── exceptions.py           # DomainError, GuardrailBlocked, OutOfScope...
│   │
│   ├── application/                # Orchestration; depends only on domain
│   │   ├── __init__.py             # Facade — single import surface for services
│   │   ├── ports.py                # Protocol interfaces (VectorStore, Embedder, Reranker,
│   │   │                           #   LLMClient, DocumentSource, MCPHostPort, Clock)
│   │   ├── dto.py                  # Command / Result DTOs (framework-free)
│   │   ├── agents/                 # Agent definitions
│   │   │   ├── legal_agent.py      # LegalAgent, FixedWorkflow, compare_strategies
│   │   │   └── orchestrator.py     # Orchestrator (planner + workers + synthesiser)
│   │   └── workflows/              # Multi-step use cases
│   │       ├── ingestion.py
│   │       ├── retrieval.py
│   │       ├── generation.py       # ExtractiveGenerator, LLMGenerator
│   │       ├── qa.py               # QaService (guardrail → filter → retrieve → generate)
│   │       ├── race.py             # AgentRace, MultiAgentRace, MeteredLegalAgent
│   │       ├── judge.py            # JudgeService + deterministic assertions
│   │       ├── evaluation.py       # hit-rate@k
│   │       └── mcp_lookup.py
│   │
│   ├── infrastructure/             # Concrete adapters; implements ports
│   │   ├── settings.py             # pydantic-settings — 12-factor config
│   │   ├── errors.py               # Infrastructure exceptions (transient / permanent)
│   │   ├── observability/
│   │   │   └── logging.py          # Structured JSON logging + request-id context
│   │   ├── vector_store/
│   │   │   └── chroma.py           # ChromaVectorStore (implements VectorStore port)
│   │   ├── embeddings/
│   │   │   ├── sentence_transformer_embedder.py
│   │   │   └── cross_encoder_reranker.py
│   │   ├── llm/openai_compatible.py
│   │   ├── documents/
│   │   │   ├── markdown_loader.py
│   │   │   └── pdf_loader.py
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
│   └── e2e/                        # HTTP TestClient over a fake-backed Container
└── data/                           # Chroma index and markdown corpus
```

## Design decisions

### Ports vs Adapters
Every external dependency (vector store, embedder, reranker, LLM, MCP host, filesystem,
clock) is a **Protocol** in `application/ports.py`. Services accept ports through
constructor injection. Concrete implementations live in `infrastructure/` and are
never imported by services.

Benefits:
- Tests replace ports with in-memory fakes — no monkeypatching, no `@lru_cache`
  contamination, no Chroma files.
- Swapping Chroma for Weaviate or SentenceTransformers for OpenAI embeddings is one
  new adapter, no service changes.

### Composition root
`legal_rag/composition.py` wires ports → adapters → services from a single
`Settings` object. Interfaces (HTTP, CLI, MCP) each build their container once at
startup and hand services down through DI.

### Config
`infrastructure/settings.py` uses `pydantic-settings.BaseSettings`. Env vars are
read once, validated at startup, and passed as an immutable object. No module-level
env reads. No hard-coded API keys. `.env.example` documents the surface.

### Logging & observability
`infrastructure/logging.py` configures **structured JSON logging** on the root
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

### Backward compatibility
Every old import path (`app.main`, `legal_assistant.*`, `mcp_servers.*`, `cli.py`)
is preserved as a **thin re-export shim**. Deprecation is silent for now; a
`DeprecationWarning` can be added in a follow-up. CLI, MCP server args, and API
routes are unchanged.

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
application/services/qa.py              (guardrails → filter → retrieval → generation)
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
