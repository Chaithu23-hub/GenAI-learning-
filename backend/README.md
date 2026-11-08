# LegalRAG backend

FastAPI, CLI, and MCP interfaces over the same dependency-injection container.

Contract questions, including numbered clause requests, use hybrid retrieval and the configured Groq model. The backend validates citations and quotations before returning the answer. `GROQ_API_KEY` is required for document answers; generation failures return errors instead of substitute excerpts. Invalid answers receive one correction attempt, then return HTTP 422 if validation still fails.

- Source: `legal_rag/` (domain, application, infrastructure, interfaces).
- Runtime dependencies: `requirements.txt`; development dependencies: `requirements-dev.txt`.
- Configuration: copy `.env.example` to `.env` on first setup and supply `GROQ_API_KEY`.
- Documents: `data/shared-corpus/contracts/` by default (Markdown); parallel DOCX/PDF
  fixtures and a 32-case golden set live under `data/shared-corpus/`.
- Vector index: `data/chroma/` (ignored).
- Evaluation inputs: `data/evaluation/labels.json`; generated reports: `data/evaluation/generated/` (ignored).

From this directory:

```powershell
python -m uvicorn legal_rag.interfaces.http.app:app --reload --port 8000
python -m legal_rag.interfaces.cli --help
python -m legal_rag.interfaces.cli.evaluate_shared_corpus --help
python -m pytest -m "not slow"
python -m ruff check legal_rag tests
```

Install the development requirements before running tests. Install the runtime requirements when building a service image. The Dockerfile uses the runtime requirements and a non-root user.

See the [project README](../README.md), [architecture](../ARCHITECTURE.md), and [contribution rules](../AGENTS.md).

Retrieval evaluation validates current source/clause labels before scoring and reports hit rate,
reciprocal rank, and required-evidence coverage. Its default six cases are a retrieval-only subset
of the shared golden set, not a legal answer-quality score. Explicit-ID evaluation cases remain supported;
missing labels raise an error rather than returning misleading zero quality.

The developer-only offline comparison runs without Chroma, ML downloads, or model APIs. From the
repository root, reproduce the review's original-code comparison with:

```powershell
.\.venv\Scripts\python.exe scripts/evaluation/measure_retrieval.py --baseline b257f3cdec8a3060029ea7710a9e12e896293969 --output backend/data/evaluation/generated/offline_retrieval_review.json
```

It uses hash embeddings, a token-overlap reranker, real BM25 code over an in-memory collection,
and the unchanged shared golden questions. It records code/corpus hashes and distinguishes source
coverage from answer correctness. The baseline revision must exist in the local Git history.

Generation sends complete indexed chunks, excludes detected instruction-bearing passages, and
checks explicit document/page/clause associations. These conservative checks are not a semantic
proof of every free-form claim. The HTTP body-transfer timeout is configured through
`LEGAL_RAG_HTTP_BODY_TIMEOUT_SECONDS`; it is separate from the blocking-work deadline.

MCP tools now use the configured corpus through the startup Container. They return exact source
passages and metadata, unknown/not-found results, or ambiguity candidates; they do not synthesize
contract text or determine amendment precedence from identifier order.

The review walkthrough and checklist stay local under `docs/`. From the repository root, run
`.\.venv\Scripts\python.exe scripts/ci/run_tests.py --suite backend` for the maintained offline
test gate, and `.\.venv\Scripts\python.exe scripts/ci/quality_checks.py` for lint, format and core
type checks. See [repository tools](../scripts/README.md) for evaluation commands.
