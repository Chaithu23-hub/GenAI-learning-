"""The Chroma adapter owns its local engine and never chooses an embedding model."""

import sys
from types import ModuleType, SimpleNamespace

from legal_rag.infrastructure.vector_store.chroma import ChromaVectorStore


def test_adapter_pins_embedded_settings_and_disables_implicit_embedding(monkeypatch):
    import legal_rag.infrastructure.vector_store.chroma as adapter

    settings_calls = []
    client_calls = []
    collection_calls = []
    collection = object()

    def settings(**kwargs):
        settings_calls.append(kwargs)
        return SimpleNamespace(**kwargs)

    def get_collection(**kwargs):
        collection_calls.append(kwargs)
        return collection

    def client(**kwargs):
        client_calls.append(kwargs)
        return SimpleNamespace(get_or_create_collection=get_collection)

    fake_chroma = ModuleType("chromadb")
    fake_chroma.PersistentClient = client
    fake_config = ModuleType("chromadb.config")
    fake_config.Settings = settings
    monkeypatch.setitem(sys.modules, "chromadb", fake_chroma)
    monkeypatch.setitem(sys.modules, "chromadb.config", fake_config)
    monkeypatch.setattr(adapter.Path, "mkdir", lambda *args, **kwargs: None)
    store = ChromaVectorStore("trusted-local-index")
    assert store._get_collection() is collection
    assert settings_calls == [
        {"chroma_api_impl": "chromadb.api.rust.RustBindingsAPI", "_env_file": None}
    ]
    assert client_calls[0]["settings"].chroma_api_impl == "chromadb.api.rust.RustBindingsAPI"
    assert collection_calls[0]["embedding_function"] is None
    assert store._get_collection() is collection
    assert len(client_calls) == 1
