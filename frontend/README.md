# LegalRAG frontend

Angular chat UI with Markdown answers, persistent conversation history, suggested questions, and a same-origin API client.

```powershell
npm ci
npm start
npm run build
npm test -- --watch=false --browsers=ChromeHeadless
```

`npm start` runs the development server with `proxy.conf.json`. The production build writes to `dist/frontend/browser`. Docker serves this directory through nginx and proxies `/api/` to the backend.

The build script generates `src/environments/environment.generated.ts` from `LEGAL_RAG_API_URL` (default `/api`) and the optional shared API gate key `LEGAL_RAG_API_KEY`. A remote API URL must include `/api`. Never add an LLM provider key to the frontend. Browser configuration is public.

ChromeHeadless tests need Chrome or a Chromium-compatible executable set through `CHROME_BIN`. CI runs both the production build and these tests.

See the [deployment guide](../docs/deployment.md).
