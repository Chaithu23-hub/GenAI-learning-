# ─── Frontend Dockerfile ───────────────────────────────────────────────────────
# Stage 1: Build the Angular app
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:1.27-alpine AS runtime

COPY --from=builder /app/dist/frontend/browser /usr/share/nginx/html

# nginx config: proxy /api/* to backend, serve Angular SPA for everything else
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:80 || exit 1

CMD ["nginx", "-g", "daemon off;"]
