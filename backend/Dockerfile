# ─── Backend Dockerfile ────────────────────────────────────────────────────────
# Multi-stage build: builder installs heavy ML deps, runtime is lean.

FROM python:3.13-slim AS builder

WORKDIR /build

# Install CPU-only PyTorch first (avoids pulling the ~2.5 GB CUDA wheel)
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY app/ ./app/
COPY legal_assistant/ ./legal_assistant/
COPY mcp_servers/ ./mcp_servers/
COPY mcp_servers.json ./
COPY cli.py ./

# Create the data directories (chroma persisted via bind mount in compose)
RUN mkdir -p data/legal data/chroma

# Non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
