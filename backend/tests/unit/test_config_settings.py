import pytest
from pydantic import ValidationError

from legal_rag.infrastructure.settings import Settings


def test_defaults_are_sensible():
    s = Settings(_env_file=None)
    assert s.chunk_size_tokens == 512
    assert s.top_k_candidates >= 1
    assert s.llm_provider == "groq"
    assert s.effective_llm_base_url == "https://api.groq.com/openai/v1"


@pytest.mark.parametrize("provider", ["google", "openai", "extractive"])
def test_removed_providers_are_rejected(provider):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_provider=provider)


def test_overlap_must_be_smaller_than_chunk():
    with pytest.raises(ValidationError):
        Settings(chunk_size_tokens=100, chunk_overlap_tokens=200)


def test_temperature_bounds_are_enforced():
    with pytest.raises(ValidationError):
        Settings(llm_temperature=3.0)


def test_explicit_groq_proxy_endpoint_is_preserved():
    s = Settings(_env_file=None, llm_base_url="https://example.test/v1")
    assert s.effective_llm_base_url == "https://example.test/v1"


def test_groq_uses_its_own_key_and_model():
    s = Settings(_env_file=None, GROQ_API_KEY="test-groq-key")
    assert s.llm_api_key == "test-groq-key"
    assert s.llm_model == "openai/gpt-oss-20b"


def test_legacy_credentials_do_not_replace_a_missing_groq_key():
    s = Settings(
        _env_file=None,
        GROQ_API_KEY=None,
        GOOGLE_API_KEY="unused-google-key",
        OPENAI_API_KEY="unused-openai-key",
    )
    assert s.llm_api_key == ""
    assert not {"google_api_key", "openai_api_key", "google_model", "openai_model"}.intersection(
        Settings.model_fields
    )
