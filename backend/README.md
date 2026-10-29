# LegalRAG backend

FastAPI, CLI, and MCP interfaces over the same dependency-injection container.

- Source: `legal_rag/` (domain, application, infrastructure, interfaces).
- Runtime dependencies: `requirements.txt`; development dependencies: `requirements-dev.txt`.
- Configuration: copy `.env.example` to `.env` on first setup and choose an LLM provider.
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

See the [project README](../README.md), [architecture](../ARCHITECTURE.md), and [deployment guide](../docs/deployment.md).

For the backend-focused student review, use the [walkthrough](../docs/backend-review-walkthrough.md)
and [quick checklist](../docs/demo-checklist.md). The disposable-container check script is
`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Test-Backend.ps1 -IncludeFormatParity`
from the repository root.
