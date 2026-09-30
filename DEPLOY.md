# Deploying LegalRAG for free

**Backend** → Hugging Face Spaces (Docker, free CPU tier)
**Frontend** → Vercel (free static hosting)
**LLM** → Google Gemini free tier

## Prerequisites

- Free accounts: [Hugging Face](https://huggingface.co/join), [Vercel](https://vercel.com/signup), [Google AI Studio](https://aistudio.google.com/app/apikey) (Gemini key).
- Optional: GitHub account (Vercel + HF both accept git-connected deploys).

## 1. Backend — Hugging Face Space

1. Create a new Space: SDK **Docker**, hardware **CPU basic (free)**, name it e.g. `legal-rag-backend`.
2. Clone the Space's git repo:
   ```bash
   git clone https://huggingface.co/spaces/<you>/legal-rag-backend
   ```
3. Copy the **contents of `backend/`** into the Space repo root (not `backend/` itself — its children):
   ```bash
   cp -R legal-rag/backend/. legal-rag-backend/
   ```
4. Push:
   ```bash
   cd legal-rag-backend && git add . && git commit -m "initial" && git push
   ```
5. In the Space UI → **Settings → Variables and secrets** add:
   - `GOOGLE_API_KEY` = your Gemini key (secret)
   - `LEGAL_RAG_API_KEY` = long random string (secret)
   - `LEGAL_RAG_CORS_ORIGINS` = `["https://<your-vercel-app>.vercel.app"]`
6. Wait for the build (5–10 min first time — installs torch + downloads models).
7. Hit `https://<you>-legal-rag-backend.hf.space/api/health` — expect `{"status":"ok",...}`.
8. Ingest the corpus once:
   ```bash
   curl -X POST https://<you>-legal-rag-backend.hf.space/api/ingest \
     -H "X-API-Key: <your api key>"
   ```

## 2. Frontend — Vercel

1. Push the repo to GitHub (or use Vercel's direct upload).
2. Vercel → **New Project** → import the repo → **Root Directory: `frontend`**.
3. Vercel auto-detects Angular (via `frontend/vercel.json`). Keep defaults.
4. **Settings → Environment Variables** add:
   - `LEGAL_RAG_API_URL` = `https://<you>-legal-rag-backend.hf.space`
   - `LEGAL_RAG_API_KEY` = the same value set on the Space
5. Deploy. Vercel gives you `https://<project>.vercel.app`.

The build command runs `node scripts/set-env.js` first, which stamps
`src/environments/environment.prod.ts` from the env vars above; `ng build`
picks them up automatically.

## 3. Verify

Open the Vercel URL. Ask "Hi" → welcome message. Ask "What is the late
payment interest rate?" → grounded answer with citations.

Check the backend metrics: `https://<space>/metrics`.

## Ongoing

- **Space sleeps after ~48 h idle** on the free tier — first request wakes it in ~30 s.
- **HF disk is persistent** — Chroma index and downloaded models survive restarts.
- **Rotate the API key** any time by editing the Space + Vercel env vars; no code change.
- **Update the corpus**: push new `.md` files under `data/legal/` and POST `/api/ingest`.

## Alternative frontends

Any static host works; the same env vars apply:
- **Cloudflare Pages**: `wrangler pages deploy dist/frontend/browser`
- **Netlify**: set publish directory `dist/frontend/browser`, build `npm run build -- --configuration production`
- **GitHub Pages**: build locally, push `dist/frontend/browser` to `gh-pages`
