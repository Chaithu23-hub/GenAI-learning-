import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = PROJECT_ROOT / "data" / "legal"    # raw legal documents (markdown)
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"  # persisted vector store


CHUNK_SIZE_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 50


TOP_K_CANDIDATES = 5
TOP_N_ANSWERS = 3
HYBRID_ENABLED = True
RRF_K = 60


MIN_RELEVANT_SCORE = 0.0
HIGH_CONFIDENCE_SCORE = 3.0


EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


LLM_BASE_URL = os.environ.get("LEGAL_RAG_LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.environ.get("LEGAL_RAG_LLM_API_KEY", "ollama")

LLM_MODEL = os.environ.get("LEGAL_RAG_LLM_MODEL", "llama3.2")


LLM_TEMPERATURE = 0.0


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
