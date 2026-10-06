from legal_rag.infrastructure.llm import select_llm_model


class ModelClient:
    def __init__(self, model: str, available_models: list[str]):
        self.model = model
        self._available_models = available_models

    def list_models(self) -> list[str]:
        return self._available_models


def test_keeps_configured_model_when_available():
    client = ModelClient("gemini-2.5-flash", ["gemini-2.5-flash", "gemini-2.5-pro"])

    assert select_llm_model(client) == "gemini-2.5-flash"
    assert client.model == "gemini-2.5-flash"


def test_applies_first_available_fallback():
    client = ModelClient("gemini-1.5-flash", ["models/gemini-2.5-flash"])

    assert select_llm_model(client) == "models/gemini-2.5-flash"
    assert client.model == "models/gemini-2.5-flash"


def test_returns_none_when_endpoint_has_no_models():
    client = ModelClient("gemini-1.5-flash", [])

    assert select_llm_model(client) is None
    assert client.model == "gemini-1.5-flash"
