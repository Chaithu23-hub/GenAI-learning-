# LegalRAG

A production-grade **Retrieval-Augmented Generation (RAG)** platform designed for legal contracts and amendments. Every answer is strictly grounded in retrieved text with verified verbatim source citations.

---

## Key Highlights

- **Clean / Hexagonal Architecture**: Strict separation of concerns (`domain → application → infrastructure → interfaces`) with Protocol ports for all external I/O.
- **Hybrid Retrieval & Reranking**: Dense embeddings + BM25 keyword search fused with Reciprocal Rank Fusion (RRF) and scored by a Cross-Encoder reranker.
- **Hierarchical Legal Chunking**: Clause-aware chunking preserving section hierarchy, table rows, and cross-document amendment context.
- **Guaranteed Source Grounding**: Every cited passage is verified verbatim against the knowledge base prior to response delivery.
- **Flexible Interfaces**: FastAPI REST service with OpenAPI documentation, Typer CLI, Model Context Protocol (MCP) servers, and Angular UI.

---

## Repository Structure

```
backend/legal_rag/
├── domain/            # Pure business entities, policies, and response schema
├── application/       # Ports (Protocols), DTOs, and orchestrations
├── infrastructure/    # Chroma vector store, embeddings, reranker, LLMs, loaders
├── interfaces/        # FastAPI HTTP routers, Typer CLI, MCP servers
└── composition.py     # Dependency injection container

backend/tests/         # Unit, integration, e2e, and real infrastructure tests
backend/data/          # Legal contract corpus and amendment sets
frontend/              # Angular web interface
eval/                  # Shared corpus golden benchmarks and reports
```

For design rationale, see [ARCHITECTURE.md](ARCHITECTURE.md) and contribution standards in [AGENTS.md](AGENTS.md).

---

## Getting Started

### Prerequisites

- Python 3.11+
- (Optional) `GOOGLE_API_KEY` for LLM generation; offline keyword-extractive generator runs without an API key.

### Setup & Ingestion

```bash
# 1. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate      # On Windows PowerShell: .\.venv\Scripts\Activate.ps1

# 2. Install dependencies
cd backend
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

# 3. Environment configuration
cp .env.example .env

# 4. Ingest corpus
python -m legal_rag ingest
```

### Running the Services

```bash
# Start backend API (http://localhost:8000)
python -m uvicorn legal_rag.interfaces.http.app:app --reload --port 8000

# Start frontend (http://localhost:4200)
cd ../frontend
npm install && npm start
```

- **Interactive API Docs**: `http://localhost:8000/api/docs`
- **Health Check**: `http://localhost:8000/api/health`

### Docker Deployment

```bash
docker compose up --build
```
Runs the backend API on `:8000` and the web frontend on `:80`.

---

## Core API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Service readiness and active configuration |
| `POST` | `/api/ask` | Submit a legal question and receive a grounded answer |
| `POST` | `/api/inspect` | Returns answer with full retrieval scores and traces |
| `POST` | `/api/ingest` | Triggers indexing of documents in the configured corpus directory |
| `POST` | `/api/upload` | Upload PDF documents, convert to text, and ingest |
| `POST` | `/api/agent` | Run agent reasoning, comparison, or orchestrator workflows |
| `POST` | `/api/mcp/lookup` | Discover and query contracts via MCP servers |

---

## CLI Commands

The Typer CLI exposes the pipeline directly in the terminal:

```bash
# Ingest contracts
python -m legal_rag ingest

# Run legal question answering
python -m legal_rag agent "What are the payment terms under the Northwind agreement?"

# Run automated evaluation
python -m legal_rag evaluate --k 3
python -m legal_rag validate-judge
```

---

## Testing & Quality Assurance

The test suite enforces full testability without requiring external network calls:

```bash
# Run standard test suite (unit + integration + e2e)
python -m pytest backend/tests/ -m "not slow"

# Run by test layer
python -m pytest backend/tests/unit/
python -m pytest backend/tests/integration/
python -m pytest backend/tests/e2e/

# Run shared-corpus golden benchmark
python eval/evaluate_shared_corpus.py
```
