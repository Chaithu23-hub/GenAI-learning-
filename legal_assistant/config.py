"""Central configuration for the legal document assistant.

All tunables live here so every other module reads from one place.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = PROJECT_ROOT / "data" / "legal"    # raw legal documents (markdown)
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"  # persisted vector store

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
# 50-token overlap so a clause straddling a chunk boundary stays retrievable
# from at least one of the overlapping windows.
CHUNK_SIZE_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 50

# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
# vector store first (cheap, high recall), then keep only the N best after
# cross-encoder re-ranking (expensive, high precision).
TOP_K_CANDIDATES = 5
TOP_N_ANSWERS = 3

# Cross-encoder relevance thresholds for the ms-marco-MiniLM model. Its
# scores are uncalibrated logits: empirically > 0 ~= relevant, > ~3 ~= strong.
MIN_RELEVANT_SCORE = 0.0
HIGH_CONFIDENCE_SCORE = 3.0

# ---------------------------------------------------------------------------
# Models (downloaded automatically on first use, cached in ~/.cache)
# ---------------------------------------------------------------------------
# fast on CPU; swap this string for bge-large-en-v1.5 or e5-large to benchmark
# higher-MTEB models on legal retrieval accuracy without other changes.
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# ---------------------------------------------------------------------------
# LLM backend — any OpenAI-compatible endpoint (Ollama, LM Studio, OpenAI).
# Defaults point at a local Ollama server; override via environment variables.
# ---------------------------------------------------------------------------
LLM_BASE_URL = os.environ.get("LEGAL_RAG_LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.environ.get("LEGAL_RAG_LLM_API_KEY", "ollama")
# here; point LEGAL_RAG_LLM_BASE_URL / LEGAL_RAG_LLM_MODEL at a GPT, Claude, or
# LLaMA endpoint to compare families without changing any other code.
LLM_MODEL = os.environ.get("LEGAL_RAG_LLM_MODEL", "llama3.2")

# deterministic and traceable (same question + same chunks -> same answer).
LLM_TEMPERATURE = 0.0

# ---------------------------------------------------------------------------
# Fixed response strings required by the assistant contract
# ---------------------------------------------------------------------------
OUT_OF_SCOPE_ANSWER = "I don't know — this information is not in the provided documents."
GUARDRAIL_ANSWER = "I can only answer questions about the legal documents in this knowledge base."
NO_DRAFTING_ANSWER = (
    "I retrieve and explain existing contract language; "
    "I do not draft, modify, or invent contract terms."
)
_DRAFTING_ANSWER = (
    "I retrieve and explain existing contract language; "
    "I do not draft, modify, or invent contract terms."
)
