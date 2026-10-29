"""12-factor configuration via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ``backend/`` — resolved from this file's location.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Every field overridable via the ``LEGAL_RAG_`` env prefix."""

    model_config = SettingsConfigDict(
        env_prefix="LEGAL_RAG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Paths ────────────────────────────────────────────────────────────
    project_root: Path = Field(default=_BACKEND_ROOT, description="Backend root")
    docs_dir: Path = Field(default=_BACKEND_ROOT / "data" / "legal")
    chroma_dir: Path = Field(default=_BACKEND_ROOT / "data" / "chroma")
    mcp_config_path: Path = Field(default=_BACKEND_ROOT / "mcp_servers.json")
    evaluation_labels_path: Path = Field(default=_BACKEND_ROOT / "data" / "evaluation" / "labels.json")
    evaluation_artifact_dir: Path = Field(default=_BACKEND_ROOT / "data" / "evaluation" / "generated")

    # ── Chunking ─────────────────────────────────────────────────────────
    chunk_size_tokens: int = Field(default=512, ge=64, le=4096)
    chunk_overlap_tokens: int = Field(default=50, ge=0, le=1024)

    # ── Retrieval ────────────────────────────────────────────────────────
    top_k_candidates: int = Field(default=5, ge=1, le=50)
    top_n_answers: int = Field(default=3, ge=1, le=20)
    hybrid_enabled: bool = Field(default=True)
    rrf_k: int = Field(default=60, ge=1)
    min_relevant_score: float = Field(default=0.0)
    high_confidence_score: float = Field(default=3.0)

    # ── Models ───────────────────────────────────────────────────────────
    embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    rerank_model: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2")

    # ── LLM backend ──────────────────────────────────────────────────────
    llm_provider: Literal["google", "openai", "groq", "extractive"] = Field(default="google")
    google_api_key: SecretStr | None = Field(default=None, alias="GOOGLE_API_KEY")
    google_model: str = Field(default="gemini-1.5-flash")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-6-luna")
    groq_api_key: SecretStr | None = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="openai/gpt-oss-20b")
    openai_reasoning_effort: Literal["none", "low", "medium", "high"] = Field(default="none")
    llm_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_timeout_seconds: int = Field(default=30, ge=1, le=300)
    llm_max_retries: int = Field(default=3, ge=0, le=10)

    # ── Agent budgets ────────────────────────────────────────────────────
    agent_max_steps: int = Field(default=4, ge=1, le=50)
    agent_max_seconds: float = Field(default=30.0, gt=0.0)
    agent_max_tokens: int = Field(default=2000, ge=1)
    agent_max_cost_usd: float = Field(default=0.02, gt=0.0)
    agent_cost_per_token_usd: float = Field(default=0.000001, ge=0.0)

    # ── Multi-agent ──────────────────────────────────────────────────────
    chars_per_token: int = Field(default=4, ge=1)
    orchestrator_worker_retries: int = Field(default=1, ge=0, le=10)

    # ── Security ─────────────────────────────────────────────────────────
    api_key: SecretStr | None = Field(default=None)

    # ── HTTP ─────────────────────────────────────────────────────────────
    cors_origins: list[str] = Field(
        default=[
            "http://localhost",
            "http://localhost:5173",
            "http://localhost:4200",
            "http://localhost:3000",
            "http://frontend:80",
        ]
    )

    # ── Observability ────────────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    log_format: Literal["json", "text"] = Field(default="json")

    # ── Fixed answer strings — must not diverge from RESPONSE_SCHEMA ─────
    out_of_scope_answer: str = Field(
        default="I don't know — this information is not in the provided documents."
    )
    guardrail_answer: str = Field(
        default="I can only answer questions about the legal documents in this knowledge base."
    )
    no_drafting_answer: str = Field(
        default=(
            "I retrieve and explain existing contract language; "
            "I do not draft, modify, or invent contract terms."
        )
    )
    greeting_answer: str = Field(
        default=(
            "Hi! I'm here and ready to help. How can I help you today?"
        )
    )

    # ── Validators ───────────────────────────────────────────────────────
    @field_validator("chunk_overlap_tokens")
    @classmethod
    def _overlap_less_than_chunk(cls, v: int, info) -> int:
        chunk = info.data.get("chunk_size_tokens", 512)
        if v >= chunk:
            raise ValueError("chunk_overlap_tokens must be < chunk_size_tokens")
        return v

    # ── Convenience ──────────────────────────────────────────────────────
    @property
    def google_api_key_value(self) -> str:
        return self.google_api_key.get_secret_value() if self.google_api_key else ""

    @property
    def api_key_value(self) -> str:
        return self.api_key.get_secret_value() if self.api_key else ""

    @property
    def llm_api_key(self) -> str:
        """Credential for the selected provider."""
        if self.llm_provider == "openai":
            return self.openai_api_key.get_secret_value() if self.openai_api_key else ""
        if self.llm_provider == "groq":
            return self.groq_api_key.get_secret_value() if self.groq_api_key else ""
        return self.google_api_key_value

    @property
    def llm_model(self) -> str:
        """Model for the selected provider."""
        if self.llm_provider == "openai":
            return self.openai_model
        if self.llm_provider == "groq":
            return self.groq_model
        return self.google_model

    @property
    def effective_llm_base_url(self) -> str:
        if self.llm_provider == "groq" and "llm_base_url" not in self.model_fields_set:
            return "https://api.groq.com/openai/v1"
        if self.llm_provider == "openai" and "llm_base_url" not in self.model_fields_set:
            return "https://api.openai.com/v1"
        return self.llm_base_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
