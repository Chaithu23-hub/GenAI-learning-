import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from legal_rag.infrastructure.observability.langfuse import (
    LangfuseMonitoring,
    MonitoredLLMClient,
    from_settings,
)
from legal_rag.infrastructure.settings import Settings
from legal_rag.interfaces.http.app import create_app
from tests.fakes.fake_llm import FakeLLMClient


@pytest.mark.parametrize("capture", [False, True])
def test_http_generations_export_to_real_sdk_with_internal_parentage(
    monkeypatch, container, capture
):
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    sdk = Langfuse(
        public_key="synthetic-" + uuid4().hex,
        secret_key="synthetic-private",
        base_url="http://127.0.0.1:9",
        tracer_provider=TracerProvider(),
        span_exporter=exporter,
        environment="test",
        debug=False,
    )
    monitor = LangfuseMonitoring(sdk, capture_content=capture)
    container.__dict__["monitoring"] = monitor
    inner = FakeLLMClient(
        responses=[
            {"content": '{"route":"social"}'},
            {"content": '{"answer":"Synthetic greeting response."}'},
        ]
    )
    monkeypatch.setattr(
        type(container),
        "llm_client",
        property(lambda _: MonitoredLLMClient(inner, monitor, "synthetic-model")),
    )
    app = create_app(container.settings)
    try:
        with TestClient(app) as http:
            app.state.container = container
            result = http.post(
                "/api/ask",
                json={"question": "Synthetic hello input"},
                headers={"X-Request-ID": "client-controlled-private-value"},
            )
            assert result.status_code == 200
            assert result.json()["answer"] == "Synthetic greeting response."
            sdk.flush()
            spans = exporter.get_finished_spans()
            assert len(spans) == 3
            roots = [span for span in spans if span.parent is None]
            assert len(roots) == 1
            root = roots[0]
            assert root.name == "answer-question"
            generations = [span for span in spans if span is not root]
            assert all(span.parent.span_id == root.context.span_id for span in generations)
            assert all(span.context.trace_id == root.context.trace_id for span in spans)
            assert all(not span.events for span in spans)
            data = json.dumps([dict(span.attributes) for span in spans])
            assert "client-controlled-private-value" not in data
            if capture:
                assert "Synthetic hello input" in data
                assert "Synthetic greeting response." in data
            else:
                assert "Synthetic hello input" not in data
                assert "Synthetic greeting response." not in data
    finally:
        monitor.close()


def test_real_sdk_debug_setting_cannot_print_captured_content(monkeypatch, capsys, caplog):
    import logging

    import langfuse
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    real_client = langfuse.Langfuse
    exporter = InMemorySpanExporter()
    clients = []

    def isolated_client(**kwargs):
        client = real_client(span_exporter=exporter, **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(langfuse, "Langfuse", isolated_client)
    monkeypatch.setenv("LANGFUSE_DEBUG", "true")
    settings = Settings(
        _env_file=None,
        langfuse_enabled=True,
        langfuse_capture_content=True,
        langfuse_base_url="http://127.0.0.1:9",
        langfuse_public_key="synthetic-" + uuid4().hex,
        langfuse_secret_key="synthetic-private",
    )
    root = logging.getLogger()
    original_level = root.level
    root.setLevel(logging.DEBUG)
    monitoring = from_settings(settings)
    try:
        monitoring.generation(
            lambda: {"content": "CANARY_CONFIDENTIAL_RESPONSE"},
            model="synthetic-model",
            messages=[{"role": "user", "content": "CANARY_CONFIDENTIAL_PROMPT"}],
            tools=None,
            temperature=0,
        )
        assert clients
        clients[0].flush()
        assert exporter.get_finished_spans()
        captured = capsys.readouterr()
        diagnostics = captured.out + captured.err + caplog.text
        assert "CANARY_CONFIDENTIAL" not in diagnostics
    finally:
        monitoring.close()
        root.setLevel(original_level)
