import os
from pathlib import Path

# The backend/ folder is the project root for all path resolution.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DOCS_DIR = PROJECT_ROOT / "data" / "legal"
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"

# ---------------------------------------------------------------------------
# [Chunk size & overlap]
# ---------------------------------------------------------------------------
CHUNK_SIZE_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 50

# ---------------------------------------------------------------------------
# [Similarity search & top-K] [Bi-encoder vs cross-encoder]
# ---------------------------------------------------------------------------
TOP_K_CANDIDATES = 5
TOP_N_ANSWERS = 3
HYBRID_ENABLED = True
RRF_K = 60

# ---------------------------------------------------------------------------
# Relevance thresholds
# ---------------------------------------------------------------------------
MIN_RELEVANT_SCORE = 0.0
HIGH_CONFIDENCE_SCORE = 3.0

# ---------------------------------------------------------------------------
# [Embedding models (MTEB / BGE / E5)] [Static vs contextual embeddings]
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# ---------------------------------------------------------------------------
# [LLM endpoint] [Cost per token] [Context window]
# ---------------------------------------------------------------------------
LLM_PROVIDER = os.environ.get("LEGAL_RAG_LLM_PROVIDER", "google").lower()
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_MODEL = os.environ.get("LEGAL_RAG_GOOGLE_MODEL", "gemini-1.5-flash")
LLM_TEMPERATURE = float(os.environ.get("LEGAL_RAG_LLM_TEMPERATURE", "0.0"))
LLM_TIMEOUT_SECONDS = int(os.environ.get("LEGAL_RAG_LLM_TIMEOUT", "30"))
LLM_MAX_RETRIES = int(os.environ.get("LEGAL_RAG_LLM_MAX_RETRIES", "3"))

# Agent budgets
AGENT_MAX_STEPS = int(os.environ.get("LEGAL_RAG_AGENT_MAX_STEPS", "4"))
AGENT_MAX_SECONDS = float(os.environ.get("LEGAL_RAG_AGENT_MAX_SECONDS", "30"))
AGENT_MAX_TOKENS = int(os.environ.get("LEGAL_RAG_AGENT_MAX_TOKENS", "2000"))
AGENT_MAX_COST_USD = float(os.environ.get("LEGAL_RAG_AGENT_MAX_COST_USD", "0.02"))
AGENT_COST_PER_TOKEN_USD = float(os.environ.get("LEGAL_RAG_AGENT_COST_PER_TOKEN_USD", "0.000001"))

# Derived LLM aliases (for backwards compatibility across modules)
LLM_BASE_URL = ""
LLM_API_KEY = GOOGLE_API_KEY
LLM_MODEL = GOOGLE_MODEL

# API security
API_KEY = os.environ.get("LEGAL_RAG_API_KEY", "")

# ---------------------------------------------------------------------------
# Fixed answer strings — never change without updating schema validation
# ---------------------------------------------------------------------------
OUT_OF_SCOPE_ANSWER = "I don't know — this information is not in the provided documents."
GUARDRAIL_ANSWER = "I can only answer questions about the legal documents in this knowledge base."
NO_DRAFTING_ANSWER = (
    "I retrieve and explain existing contract language; "
    "I do not draft, modify, or invent contract terms."
)
_DRAFTING_ANSWER = NO_DRAFTING_ANSWER  # backwards-compat alias


def validate_llm_config():
    """Validate that the LLM backend is correctly configured at startup."""
    provider = LLM_PROVIDER.lower()

    if provider != "google":
        raise ValueError(
            f"Unsupported LLM provider: '{provider}'. "
            "This project is configured for Google Gemini only. "
            "Set LEGAL_RAG_LLM_PROVIDER=google and GOOGLE_API_KEY."
        )

    if not GOOGLE_API_KEY or GOOGLE_API_KEY.strip() == "":
        raise ValueError(
            "Google API key not configured. "
            "Set GOOGLE_API_KEY environment variable:\n"
            "  export GOOGLE_API_KEY='your-key-here'\n"
            "Get free key at: https://aistudio.google.com/app/apikey"
        )

    import sys
    print(f"[LLM Config] ✓ Google Gemini configured (model={GOOGLE_MODEL})", file=sys.stderr)
    return True


try:
    validate_llm_config()
except ValueError as e:
    import sys
    print(f"[LLM Config Error] {e}", file=sys.stderr)
    print(f"[LLM Config] Using fallback: LEGAL_RAG_LLM_PROVIDER={LLM_PROVIDER}", file=sys.stderr)
