.PHONY: help install install-dev install-frontend backend-run frontend-run test test-slow test-fast lint format ingest race

help:
	@echo "Common commands:"
	@echo "  make install          Install backend deps into current Python env"
	@echo "  make install-dev      Install backend test and lint dependencies"
	@echo "  make install-frontend Install Angular deps"
	@echo "  make backend-run      Run the FastAPI backend on :8000"
	@echo "  make frontend-run     Run the Angular dev server on :4200"
	@echo "  make test             Run unit + integration + e2e (skip slow)"
	@echo "  make test-slow        Run everything including real Chroma/model tests"
	@echo "  make test-fast        Unit + fake-backed integration only"
	@echo "  make lint             ruff check"
	@echo "  make format           ruff format + ruff --fix"
	@echo "  make ingest           CLI: chunk + embed + store the corpus"
	@echo "  make race             CLI: single agent vs orchestrator race"

install:
	cd backend && python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
	cd backend && python -m pip install -r requirements.txt

install-frontend:
	cd frontend && npm ci

install-dev:
	cd backend && python -m pip install -r requirements-dev.txt

backend-run:
	cd backend && python -m uvicorn legal_rag.interfaces.http.app:app --reload --port 8000

frontend-run:
	cd frontend && npm start

test:
	cd backend && python -m pytest -m "not slow"

test-slow:
	cd backend && python -m pytest

test-fast:
	cd backend && python -m pytest tests/unit tests/integration -m "not slow"

lint:
	cd backend && python -m ruff check .

format:
	cd backend && python -m ruff format .
	cd backend && python -m ruff check --fix .

ingest:
	cd backend && python -m legal_rag.interfaces.cli ingest

race:
	cd backend && python -m legal_rag.interfaces.cli race-orchestrator
