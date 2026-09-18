# LegalRAG

A local legal-document assistant with a FastAPI backend and Angular frontend. Answers are grounded in the contract files under `backend/data/legal/` and include source citations.

## Run locally

### Backend

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Health check: `http://localhost:8000/api/health`

### Frontend

```powershell
Push-Location frontend
npm install
npm start
```

Open `http://localhost:4200`.

The Angular dev server proxies `/api` requests to the backend. Extractive answers work locally without an LLM key. Gemini mode requires `GOOGLE_API_KEY` in the backend environment.

## Tests

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest tests
```

## Docker

```powershell
docker compose up --build
```

The compose setup serves the API on port `8000` and the production frontend on port `80`.

## Project layout

- `backend/app/` - FastAPI routes and schemas
- `backend/legal_assistant/` - ingestion, retrieval, generation, safety, and agent workflows
- `backend/mcp_servers/` - MCP tool servers
- `frontend/src/` - Angular application
- `backend/data/legal/` - sample contracts and amendments
- `eval/` - evaluation evidence and Week 9 MCP artifacts
