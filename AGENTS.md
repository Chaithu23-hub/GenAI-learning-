# AGENTS.md — Contribution rules for LegalRAG

Read this before writing or modifying code. It exists so any AI or human
contributor produces changes that fit the architecture rather than break it.
Full rationale is in [ARCHITECTURE.md](ARCHITECTURE.md).

## Golden rules

1. **Dependencies point inward.** `interfaces → infrastructure → application → domain`.
   - `domain/` imports nothing from `application`, `infrastructure`, `interfaces`.
   - `application/` imports only from `domain/`.
   - `infrastructure/` may import `domain/` + `application/ports`, never `application/services`.
   - `interfaces/` may import everything; nothing else imports from `interfaces/`.
2. **No framework code outside `interfaces/`.** FastAPI, Typer, MCP SDK, Pydantic BaseModel-as-DTO — all belong there. Services take plain data.
3. **Adapters implement ports.** Every external dependency (Chroma, LLM, embeddings, MCP host, filesystem, clock) is a `Protocol` in `legal_rag/application/ports.py`. Services depend on the port, never on the concrete adapter. New I/O concern → new port → new adapter.
4. **Settings via pydantic-settings.** Never `os.environ` at module import. Read config through `legal_rag.infrastructure.settings.get_settings()` and pass it into constructors.
5. **Structured logging only.** `from legal_rag.infrastructure.logging import get_logger` and call `log.info("event", extra={...})`. No `print(...)`. No writes to stderr.
6. **Error taxonomy.**
   - Business rule failure → raise from `legal_rag.domain.exceptions`.
   - Adapter I/O failure → raise from `legal_rag.infrastructure.errors` (`TransientError` for retryable, `PermanentError` otherwise).
   - HTTP layer's `interfaces/http/errors.py` maps both to problem+json responses. Do not catch-and-swallow.
7. **The response contract is fixed.** `legal_rag/domain/response_schema.RESPONSE_SCHEMA` and the mirror in `legal_rag/interfaces/http/schemas.AnswerResponse` must stay in sync. Adding a field is a coordinated three-file change (schema, DTO, README).
8. **Composition happens once.** Every interface builds a `Container` at startup (`legal_rag/composition.py`). Do not construct concrete adapters inside services or routers.
9. **No global mutable state in services.** No module-level `@lru_cache` inside `application/`. Caching that must survive per process goes in the adapter or the container.
10. **Tests must not touch the network or the disk (except in `tests/e2e/` and `slow`-marked tests).** Use `tests/fakes/` for in-memory implementations of every port.

## When you add a new capability

1. Model it in `domain/entities.py` (data) and `domain/policies.py` (rules) if it is a business concept. Otherwise skip domain.
2. Define its dependencies as ports in `application/ports.py`.
3. Write the service in `application/services/`. Accept ports through the constructor; no side-effects at import.
4. Implement the port(s) in `infrastructure/`.
5. Wire it in `composition.py` as a `cached_property`.
6. Expose it in the correct interface (`interfaces/http/routers/*`, `interfaces/cli/app.py`, or a new MCP server under `interfaces/mcp_servers/`).
7. Write tests at the correct level:
   - Domain rule → `tests/unit/domain/`
   - Service with fake ports → `tests/integration/`
   - HTTP endpoint with `TestClient` → `tests/e2e/`

## Layout reference

```
backend/legal_rag/
├── domain/            # entities.py, policies.py, response_schema.py, exceptions.py
├── application/
│   ├── ports.py       # Protocols for every external dependency
│   ├── agents/        # LegalAgent, Orchestrator
│   └── workflows/     # ingestion, retrieval, generation, qa, race, judge, evaluation, mcp_lookup
├── infrastructure/
│   ├── settings.py, errors.py
│   ├── observability/ # logging (JSON + request id)
│   ├── vector_store/  # chroma.py
│   ├── embeddings/    # sentence_transformer + cross_encoder
│   ├── llm/           # groq.py (OpenAI-compatible SDK transport)
│   ├── documents/     # markdown + pdf loaders
│   ├── prompts/       # versioned prompt templates
│   ├── chunking/      # section chunker
│   ├── mcp/           # stdio host
│   └── retrieval/     # rrf
├── interfaces/
│   ├── http/          # FastAPI: app, routers, dependencies, middleware, errors, schemas
│   ├── cli/           # Typer
│   └── mcp_servers/   # clause_search + contract_repository
└── composition.py     # DI Container
backend/tests/
├── unit/              # pure domain, no I/O
├── fakes/             # in-memory port implementations
├── integration/       # services wired against fakes
└── e2e/               # HTTP TestClient over a fake-backed Container
```

**Import paths**
- Use the facade: `from legal_rag.application import QaService, LegalAgent, Orchestrator, JudgeService, ...`
- Or the specific package: `from legal_rag.application.agents import LegalAgent`, `from legal_rag.application.workflows.qa import QaService`
- `race` module lives under `workflows/` but is imported from its submodule, not the workflows facade, to avoid a workflows ⇄ agents cycle.
- Prompts always come from `legal_rag.infrastructure.prompts` — never define inline in a service.
- Logging is `from legal_rag.infrastructure.observability.logging import get_logger`.

## Commands (Windows / PowerShell)

```powershell
# Run backend
Push-Location backend
..\.venv\Scripts\python.exe -m uvicorn legal_rag.interfaces.http.app:app --reload --port 8000

# CLI
..\.venv\Scripts\python.exe -m legal_rag.interfaces.cli ingest
..\.venv\Scripts\python.exe -m legal_rag.interfaces.cli agent "What is the late payment fee?" --strategy compare
..\.venv\Scripts\python.exe -m legal_rag.interfaces.cli race-orchestrator

# Tests
..\.venv\Scripts\python.exe -m pytest tests/ -v
..\.venv\Scripts\python.exe -m pytest tests/ -m "not slow"
Pop-Location
```

## Docker

`docker compose up --build` runs backend on `:8000` and Angular frontend on `:80`.

## What NOT to do

- Do not add another config file. Every knob lives in `Settings`.
- Do not import a service inside a Protocol/port file.
- Do not read environment variables outside `Settings`.
- Do not return dicts from routers where a Pydantic model exists.
- Do not add a "convenience" module-level function that hides a service.
- Do not commit secrets. `GROQ_API_KEY`, `LEGAL_RAG_API_KEY` go in `.env` (git-ignored).
- Do not use `print()` in library code.

## Codex multi-agent workflow

- Keep the installed Superpowers workflows for planning, TDD, debugging, and verification. Use their relevant skills rather than copying their procedures into agent prompts; Codex agents complement those workflows.
- The main Codex agent owns task triage, coordination, integration, and final verification. Delegate a focused slice when another role or an isolated investigation materially helps; handle trivial lookups and small local fixes directly. Do not ask the user to choose an agent.
- Codex chooses whether to delegate from these project instructions and agent descriptions; this is model-guided, not a deterministic task-rule engine. Do not promise that every matching request will spawn an agent.
- Route codebase discovery to **Explorer**; FastAPI, service, and routine bug fixes to **Python Developer**; embeddings, chunking, hybrid retrieval, BM25, RRF, and reranking to **RAG Specialist**; test-only work to **Test Engineer**; security-sensitive changes involving prompt injection, authorization, tenant isolation, or confidential documents to **Security Reviewer**; and focused maintainability or architecture checks to **Code Reviewer**.
- Start no more than two subagents concurrently and do not let subagents spawn further agents. Give each a bounded objective and only the relevant context. Avoid duplicate searches, broad codebase handoffs, repeated review cycles, and concurrent edits to the same files.
- Use low reasoning for simple, bounded work, medium for ordinary tasks, and high only for genuinely complex or high-risk work. Avoid xhigh, max, and ultra unless a demonstrated need justifies the extra cost. Codex currently documents the concurrent-agent cap, but not a configuration-enforced delegation-depth limit; the no-nesting rule is therefore an instruction.
- Use read-only roles for investigation and review. Assign a single writer to each set of files; have other agents report findings rather than edit those files. Keep handoffs concise and include changed paths, evidence, and validation results.
- Preserve legal clause extraction, exact document/page references, grounded answers with supporting evidence, document-version consistency, confidentiality, tenant isolation, authorization, and the architecture and test rules above. Never trade correctness or security for token savings.
