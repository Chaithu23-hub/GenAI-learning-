import pytest
from pydantic import ValidationError

from legal_rag.infrastructure.settings import Settings


def test_defaults_are_sensible():
    s = Settings()
    assert s.chunk_size_tokens == 512
    assert s.top_k_candidates >= 1
    assert s.llm_provider in {"google", "openai", "extractive"}


def test_overlap_must_be_smaller_than_chunk():
    with pytest.raises(ValidationError):
        Settings(chunk_size_tokens=100, chunk_overlap_tokens=200)


def test_temperature_bounds_are_enforced():
    with pytest.raises(ValidationError):
        Settings(llm_temperature=3.0)


def test_google_api_key_helper_masks_none():
    s = Settings(google_api_key=None)
    assert s.google_api_key_value == ""
