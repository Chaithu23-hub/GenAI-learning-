import pytest

from legal_rag.composition import Container
from legal_rag.infrastructure.errors import PermanentLLMError
from legal_rag.infrastructure.settings import Settings


def test_missing_provider_key_raises_instead_of_selecting_offline_generator():
    container = Container(Settings(
        _env_file=None, GROQ_API_KEY=None,
    ))
    with pytest.raises(PermanentLLMError, match="API key is required"):
        _ = container.llm_client
