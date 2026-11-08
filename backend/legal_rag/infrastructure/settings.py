"""12-factor configuration via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ``backend/`` — resolved from this file's location.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_DATA_ROOT = _BACKEND_ROOT / "data"


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
    docs_dir: Path = Field(default=_PROJECT_DATA_ROOT / "shared-corpus" / "contracts")
    chroma_dir: Path = Field(default=_BACKEND_ROOT / "data" / "chroma")
    mcp_config_path: Path = Field(default=_BACKEND_ROOT / "mcp_servers.json")
    evaluation_labels_path: Path = Field(
        default=_BACKEND_ROOT / "data" / "evaluation" / "labels.json"
    )
    evaluation_artifact_dir: Path = Field(
        default=_BACKEND_ROOT / "data" / "evaluation" / "generated"
    )

    # ── Chunking ─────────────────────────────────────────────────────────
    chunk_size_tokens: int = Field(default=512, ge=64, le=4096)
    chunk_overlap_tokens: int = Field(default=50, ge=0, le=1024)

    # ── Retrieval ────────────────────────────────────────────────────────
    top_k_candidates: int = Field(default=20, ge=1, le=50)
    top_n_answers: int = Field(default=8, ge=1, le=20)
    hybrid_enabled: bool = Field(default=True)
    rrf_k: int = Field(default=60, ge=1)
    min_relevant_score: float = Field(default=-6.5)

    # ── Models ───────────────────────────────────────────────────────────
    embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    rerank_model: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2")

    # ── LLM backend ──────────────────────────────────────────────────────
    llm_provider: Literal["groq"] = Field(default="groq")
    groq_api_key: SecretStr | None = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="openai/gpt-oss-20b")
    llm_base_url: str = Field(default="https://api.groq.com/openai/v1")
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    greeting_temperature: float = Field(default=0.8, gt=0.0, le=2.0)
    unsupported_response_temperature: float = Field(default=0.7, gt=0.0, le=2.0)
    llm_timeout_seconds: int = Field(default=30, ge=1, le=300)
    llm_max_retries: int = Field(default=3, ge=0, le=10)
    mcp_timeout_seconds: float = Field(default=30.0, gt=0.0, le=300.0)

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
    admin_api_key: SecretStr | None = Field(default=None)
    development_mode: bool = Field(default=False)

    # Resource budgets apply before parsing and while executing blocking work.
    http_max_body_bytes: int = Field(default=26 * 1024 * 1024, ge=1024)
    http_max_concurrent_jobs: int = Field(default=4, ge=1, le=32)
    http_request_timeout_seconds: float = Field(default=120, gt=0, le=600)
    http_body_timeout_seconds: float = Field(default=30, gt=0, le=600)
    upload_max_file_bytes: int = Field(default=25 * 1024 * 1024, ge=1)
    upload_max_files: int = Field(default=4, ge=1, le=16)
    pdf_max_pages: int = Field(default=100, ge=1, le=10000)
    pdf_max_characters: int = Field(default=1_000_000, ge=1)
    pdf_timeout_seconds: float = Field(default=20, gt=0, le=120)
    pdf_memory_mb: int = Field(default=512, ge=128, le=4096)

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
    def api_key_value(self) -> str:
        return self.api_key.get_secret_value() if self.api_key else ""

    @property
    def admin_api_key_value(self) -> str:
        return self.admin_api_key.get_secret_value() if self.admin_api_key else ""

    def validate_http_security(self) -> None:
        """Validate HTTP credentials without restricting CLI configuration."""
        reader, admin = self.api_key_value, self.admin_api_key_value
        if not self.development_mode and (not reader.strip() or not admin.strip()):
            raise ValueError(
                "HTTP requires distinct reader and admin API keys; anonymous reads require explicit development_mode."
            )
        if (reader and not reader.strip()) or (admin and not admin.strip()):
            raise ValueError("HTTP API keys cannot contain only whitespace.")
        if reader and admin and reader == admin:
            raise ValueError("HTTP reader and admin API keys must be distinct.")

    @property
    def llm_api_key(self) -> str:
        """Credential for Groq."""
        return self.groq_api_key.get_secret_value() if self.groq_api_key else ""

    @property
    def llm_model(self) -> str:
        """Configured Groq model."""
        return self.groq_model

    @property
    def effective_llm_base_url(self) -> str:
        return self.llm_base_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
