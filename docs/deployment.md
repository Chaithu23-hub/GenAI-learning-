# Deployment

## Docker

Run `docker compose up -d --build` from the repository root. The frontend serves on port 80 and proxies `/api/` to the backend on port 8000. Container health checks use the frontend root and backend `/api/health`.

Compose loads application settings from `backend/.env`. Use a separate environment for each deployment and keep credentials out of the repository and image. Select one LLM provider and supply only the credentials it needs. Provider limits or unavailable models can prevent generation; the health endpoint reports configuration, not a live model-access guarantee.

The runtime image excludes pytest and Ruff. Tests and lint run separately in CI using `backend/requirements-dev.txt`.

## Persistent data

The Compose bind mount `./backend/data:/app/data` contains source documents, the vector index, and evaluation labels. Back up this directory using your deployment's backup process. Do not remove it as a cache-cleaning operation. Re-run ingestion after changing source documents.

Embedding and reranking models download on first use into the container user's cache. The current Compose setup does not persist that cache; container recreation can cause another download. Mount a dedicated cache volume if cold starts matter to your deployment.

Generated evaluation reports are written to `backend/data/evaluation/generated/` by default and are not source files. Keep labelled evaluation inputs under version control.

## Access and transport

The supplied Compose file is a local deployment. Before exposing it publicly, put it behind a TLS reverse proxy, restrict access to administrative routes such as upload/ingest/inspect, and configure CORS for the actual frontend origin. Decide which API docs and metrics endpoints should be reachable from outside.

`LEGAL_RAG_API_KEY` provides a shared API gate for protected application routes. It is not a per-user identity or session system. A key embedded into a browser build is visible to browser users; do not treat it as a server secret. For a public deployment, enforce authentication at a trusted gateway or add a proper identity integration. Provider credentials (`GROQ_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`) belong only on the backend.

## Frontend hosting

Docker serves the frontend and backend under one origin using nginx. The optional `frontend/vercel.json` supports a static frontend deployment; the build script reads `LEGAL_RAG_API_URL` and `LEGAL_RAG_API_KEY`. `LEGAL_RAG_API_URL` must include the `/api` suffix, for example `https://api.example.com/api`.

Build outputs and generated environment files must not contain provider credentials. The previous free-hosting walkthrough is retained in the archive; verify any provider's current storage, quota, and pricing before using it.

## Verify a release

The 2026-10-29 repository cleanup is a structural cleanup, not a security certification.
The installed frontend dependency audit still reports seven runtime advisories
(three high and four moderate). Review and upgrade the affected framework/packages
before a public release; this cleanup does not perform a framework migration.

1. Run backend lint/tests and frontend build/tests in CI.
2. Check `/api/health`, `/metrics`, and the frontend response.
3. Ingest a known corpus, ask a known contract question, and verify its answer against the source document.
4. Verify the selected model using the deployment's own credentials and monitor quota/error responses.
5. Confirm restart persistence and restore procedures for documents and the vector index.
