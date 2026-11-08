# ── Backend Dockerfile ─ multi-stage: heavy ML deps in builder, lean runtime ──
FROM python:3.13-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN --mount=type=cache,id=legal-rag-pip-py313,target=/root/.cache/pip,sharing=locked \
    pip install -r requirements.txt

# ── Runtime stage ────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.13/site-packages \
                    /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Application source
COPY legal_rag/ ./legal_rag/
COPY mcp_servers.json ./
COPY pyproject.toml ./
COPY data/evaluation/labels.json ./data/evaluation/labels.json
COPY data/shared-corpus/contracts/ ./data/shared-corpus/contracts/

# Data directories (Chroma persisted via bind mount in compose)
RUN mkdir -p data/legal data/chroma

# Non-root user
RUN useradd --create-home --shell /bin/false appuser && \
    mkdir -p /home/appuser/.cache/huggingface && \
    chown -R appuser:appuser /home/appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/live')"

CMD ["uvicorn", "legal_rag.interfaces.http.app:app", "--host", "0.0.0.0", "--port", "8000"]
