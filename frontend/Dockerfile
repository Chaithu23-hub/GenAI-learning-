# ─── Frontend Dockerfile ───────────────────────────────────────────────────────
# Stage 1: Build the Angular app
FROM node:22-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json* ./
RUN --mount=type=cache,id=legal-rag-npm-node22,target=/root/.npm,sharing=locked \
    npm ci --prefer-offline

COPY . .
# This token is public in browser assets; never supply provider/admin credentials.
# Name the build argument explicitly as public and scope the script's variable
# to this command rather than retaining it in the builder image environment.
ARG PUBLIC_READER_TOKEN=""
RUN node -e "process.env.LEGAL_RAG_API_KEY = process.env.PUBLIC_READER_TOKEN; \
    require('node:child_process').execFileSync('npm', ['run', 'build'], {stdio: 'inherit'})"

# Stage 2: Serve with nginx
FROM nginx:1.27-alpine AS runtime

COPY --from=builder /app/dist/frontend/browser /usr/share/nginx/html

# nginx config: proxy /api/* to backend, serve Angular SPA for everything else
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:80 || exit 1

CMD ["nginx", "-g", "daemon off;"]
