from fastapi.testclient import TestClient

from legal_rag.composition import Container
from legal_rag.interfaces.http.app import create_app


class Monitor:
    def __init__(self):
        self.closed = 0
        self.names = []

    def run(self, name, operation):
        self.names.append(name)
        return operation()

    def close(self):
        self.closed += 1


def test_container_close_is_idempotent_and_does_not_initialize_unused_monitor(settings):
    container = Container(settings)
    container.close()
    assert "monitoring" not in vars(container)
    active = Container(settings)
    monitor = Monitor()
    active.__dict__["monitoring"] = monitor
    active.close()
    active.close()
    assert monitor.closed == 1


def test_http_shutdown_closes_active_container_monitor(settings):
    app = create_app(settings)
    with TestClient(app):
        monitor = Monitor()
        app.state.container.__dict__["monitoring"] = monitor
        assert app.state.container is not None
    assert monitor.closed == 1


def test_cli_command_traces_and_closes_its_container(monkeypatch, container):
    import importlib

    from typer.testing import CliRunner

    cli = importlib.import_module("legal_rag.interfaces.cli.app")
    monitor = Monitor()
    container.__dict__["monitoring"] = monitor
    monkeypatch.setattr(cli, "get_settings", lambda: container.settings)
    monkeypatch.setattr(cli, "Container", lambda _: container)
    result = CliRunner().invoke(cli.app, ["ingest"])
    assert result.exit_code == 0, result.output
    assert monitor.names == ["cli.ingest"]
    assert monitor.closed == 1
