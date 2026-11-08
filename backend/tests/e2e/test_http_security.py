"""Access controls reject requests before expensive adapter construction."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from legal_rag.composition import Container
from legal_rag.infrastructure.settings import Settings
from legal_rag.interfaces.http.app import create_app


def security_settings(**overrides):
    return Settings(_env_file=None, api_key=None, admin_api_key=None, **overrides)


@pytest.mark.parametrize(
    "reader,admin",
    [(None, None), ("reader", None), (None, "admin"), ("same", "same"), (" ", "admin")],
)
def test_production_app_rejects_missing_or_shared_credentials(reader, admin):
    settings = Settings(_env_file=None, api_key=reader, admin_api_key=admin)
    with pytest.raises(ValueError, match="HTTP"):
        create_app(settings)


class UninitializedContainer:
    def __init__(self, settings):
        self.settings = settings

    def __getattr__(self, name):
        raise AssertionError(f"Unauthorized request initialized {name}")


def client_for(settings):
    app = create_app(settings)
    app.state.container = UninitializedContainer(settings)
    return TestClient(app)


def test_explicit_development_mode_allows_anonymous_reads_only():
    client = client_for(security_settings(development_mode=True))
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/ingest").status_code == 401
    assert (
        client.post(
            "/api/upload", files={"files": ("x.pdf", b"pdf", "application/pdf")}
        ).status_code
        == 401
    )


@pytest.mark.parametrize("key", [None, "wrong", "reader"])
@pytest.mark.parametrize("route", ["/api/ingest", "/api/upload"])
def test_admin_routes_reject_without_initializing_adapters(route, key):
    settings = Settings(_env_file=None, api_key="reader", admin_api_key="admin")
    client = client_for(settings)
    headers = {"X-API-Key": key} if key else {}
    files = {"files": ("x.pdf", b"pdf", "application/pdf")} if route.endswith("upload") else None
    assert client.post(route, headers=headers, files=files).status_code == 401


def test_admin_key_in_query_does_not_authorize_writes():
    client = client_for(Settings(_env_file=None, api_key="reader", admin_api_key="admin"))
    assert client.post("/api/ingest?api_key=admin").status_code == 401


@pytest.mark.parametrize("key", [None, "wrong", b"\xe9-invalid"])
def test_qa_rejects_before_model_initialization(key):
    client = client_for(Settings(_env_file=None, api_key="reader", admin_api_key="admin"))
    headers = {"X-API-Key": key} if key else {}
    assert (
        client.post("/api/ask", json={"question": "Payment terms?"}, headers=headers).status_code
        == 401
    )


@pytest.mark.parametrize("key", ["reader", "admin"])
def test_both_roles_can_read_health(key):
    client = client_for(Settings(_env_file=None, api_key="reader", admin_api_key="admin"))
    assert client.get("/api/health", headers={"X-API-Key": key}).status_code == 200
    assert client.get("/api/health").status_code == 401


def test_admin_can_ingest():
    settings = Settings(_env_file=None, api_key="reader", admin_api_key="admin")
    client = client_for(settings)
    container = Container(settings)
    container.ingestion_service = SimpleNamespace(ingest=lambda: 7)
    client.app.state.container = container
    try:
        response = client.post("/api/ingest", headers={"X-API-Key": "admin"})
        assert response.status_code == 200
        assert response.json()["chunks_ingested"] == 7
    finally:
        container.work_executor.close()


def test_liveness_is_public_and_does_not_disclose_configuration():
    client = client_for(Settings(_env_file=None, api_key="reader", admin_api_key="admin"))
    assert client.get("/api/live").json() == {"status": "ok"}


def test_deferred_module_app_validates_at_startup(monkeypatch):
    import importlib

    app_module = importlib.import_module("legal_rag.interfaces.http.app")
    monkeypatch.setattr(
        app_module,
        "get_settings",
        lambda: Settings(_env_file=None, api_key=None, admin_api_key=None),
    )
    # The ASGI entrypoint can be imported by CLI tooling, but cannot start insecurely.
    app = app_module.create_app(_defer_security_validation=True)
    with pytest.raises(ValueError, match="HTTP"), TestClient(app):
        pass
