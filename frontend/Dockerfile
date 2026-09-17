# ─── Frontend Dockerfile ───────────────────────────────────────────────────────
# Stage 1: Build the React app
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
# Inject the backend URL for the production build
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:1.27-alpine AS runtime

COPY --from=builder /app/dist/frontend/browser /usr/share/nginx/html

# nginx config: proxy /api/* to backend, serve Angular SPA for everything else
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://localhost:80 || exit 1

CMD ["nginx", "-g", "daemon off;"]
