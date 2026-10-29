import pytest
from pydantic import ValidationError

from legal_rag.infrastructure.settings import Settings


def test_defaults_are_sensible():
    s = Settings()
    assert s.chunk_size_tokens == 512
    assert s.top_k_candidates >= 1
    assert s.llm_provider in {"google", "openai", "groq", "extractive"}


def test_overlap_must_be_smaller_than_chunk():
    with pytest.raises(ValidationError):
        Settings(chunk_size_tokens=100, chunk_overlap_tokens=200)


def test_temperature_bounds_are_enforced():
    with pytest.raises(ValidationError):
        Settings(llm_temperature=3.0)


def test_google_api_key_helper_masks_none():
    s = Settings(google_api_key=None)
    assert s.google_api_key_value == ""


def test_openai_uses_its_own_credentials_model_and_endpoint():
    s = Settings(
        _env_file=None, llm_provider="openai",
        OPENAI_API_KEY="test-openai-key", GOOGLE_API_KEY="test-google-key",
    )
    assert s.llm_api_key == "test-openai-key"
    assert s.llm_model == "gpt-6-luna"
    assert s.effective_llm_base_url == "https://api.openai.com/v1"
    assert s.openai_reasoning_effort == "none"


def test_openai_does_not_use_google_credentials_when_key_is_missing():
    s = Settings(
        _env_file=None, llm_provider="openai", OPENAI_API_KEY=None,
        GOOGLE_API_KEY="test-google-key",
    )
    assert s.llm_api_key == ""


def test_explicit_endpoint_is_preserved():
    s = Settings(_env_file=None, llm_provider="openai", llm_base_url="https://example.test/v1")
    assert s.effective_llm_base_url == "https://example.test/v1"


def test_google_provider_keeps_existing_configuration():
    s = Settings(_env_file=None, llm_provider="google", GOOGLE_API_KEY="test-google-key")
    assert s.llm_api_key == "test-google-key"
    assert s.llm_model == s.google_model
    assert "generativelanguage.googleapis.com" in s.effective_llm_base_url


def test_groq_uses_its_own_key_model_and_endpoint():
    s = Settings(_env_file=None, llm_provider="groq", GROQ_API_KEY="test-groq-key")
    assert s.llm_api_key == "test-groq-key"
    assert s.llm_model == "openai/gpt-oss-20b"
    assert s.effective_llm_base_url == "https://api.groq.com/openai/v1"


def test_missing_groq_key_does_not_fall_back_to_other_credentials():
    s = Settings(_env_file=None, llm_provider="groq", GROQ_API_KEY=None,
                 GOOGLE_API_KEY="test-google-key", OPENAI_API_KEY="test-openai-key")
    assert s.llm_api_key == ""
