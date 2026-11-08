# LegalRAG frontend

Angular chat UI with Markdown answers, persistent conversation history, suggested questions, and a same-origin API client.

```powershell
npm ci
npm start
npm run build
npm test -- --watch=false --browsers=ChromeHeadless
```

`npm start` runs the development server with `proxy.conf.json`. The production build writes to `dist/frontend/browser`. Docker serves this directory through nginx and proxies `/api/` to the backend.

The build script generates `src/environments/environment.generated.ts` from `LEGAL_RAG_API_URL` (default `/api`) and the reader key `LEGAL_RAG_API_KEY`. A remote API URL must include `/api`. Browser configuration is public: never provide `LEGAL_RAG_ADMIN_API_KEY` or an LLM provider key to a frontend build. Reader access does not authorize ingestion or upload.

The default `npm start` uses an empty reader key: explicitly enable `LEGAL_RAG_DEVELOPMENT_MODE=true` on the local backend for anonymous reads. For authenticated local UI access, set `$env:LEGAL_RAG_API_KEY` to the backend reader key, run `node scripts/set-env.js`, then `npm start -- --configuration production` to use the generated environment. Administrative writes always require the separate backend admin key in `X-API-Key`. Docker builds receive only the reader key when run with `docker compose --env-file backend/.env up -d --build` from the repository root. Rebuild the frontend when rotating its reader key.

ChromeHeadless tests need Chrome or a Chromium-compatible executable set through `CHROME_BIN`. CI runs both the production build and these tests.

See the [project README](../README.md) for deployment and configuration notes.
