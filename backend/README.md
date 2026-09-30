---
title: LegalRAG
emoji: ⚖️
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 8000
pinned: false
license: mit
---

# LegalRAG — backend (Hugging Face Space)

Production-grade RAG pipeline for legal contracts. Answers are grounded in
retrieved contract and amendment passages with source citations.

See [../README.md](../README.md) for the full project overview and
[../ARCHITECTURE.md](../ARCHITECTURE.md) for the layer design.

## Space configuration

Set these under **Settings → Variables and secrets** in the Space UI.

**Required (secrets):**

- `GOOGLE_API_KEY` — your Google AI Studio Gemini key ([get one free](https://aistudio.google.com/app/apikey)).
- `LEGAL_RAG_API_KEY` — a long random string; every backend call must send it as `X-API-Key`.

**Optional overrides:**

- `LEGAL_RAG_LLM_PROVIDER` (default `google`; use `extractive` to disable the LLM)
- `LEGAL_RAG_LOG_FORMAT=json`
- `LEGAL_RAG_CORS_ORIGINS='["https://<your-vercel-project>.vercel.app"]'`

## First boot

On cold start the Space downloads:

- `sentence-transformers/all-MiniLM-L6-v2` (~90 MB)
- `cross-encoder/ms-marco-MiniLM-L-6-v2` (~90 MB)

Both are cached in the Space's persistent `/data` mount, so subsequent starts
are fast. Then run one ingest to populate Chroma:

```
POST https://<space>.hf.space/api/ingest  (with X-API-Key)
```

## Endpoints

- `GET  /api/health`     configuration + prompt versions
- `POST /api/ask`        answer a legal question
- `POST /api/inspect`    answer + full retrieval trace
- `POST /api/ingest`     rebuild the index
- `POST /api/upload`     PDF → markdown → re-ingest
- `POST /api/agent`      run the agent, fixed workflow, or comparison
- `POST /api/mcp/lookup` MCP tool discovery + contract lookup
- `GET  /metrics`        Prometheus metrics (no auth)
- `GET  /api/docs`       OpenAPI Swagger UI
