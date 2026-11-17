from __future__ import annotations

import threading
import time
from itertools import count

import pytest

from legal_rag.infrastructure.observability.langfuse import (
    LangfuseMonitoring,
    MonitoredLLMClient,
    NoopMonitoring,
)

SK_LIVE = "sk-" + "live-" + "x" * 26
GITHUB_TOKEN = "ghp_" + "x" * 30


class Observation:
    def __init__(self, client, ident: str, trace_id: str, parent_id=None, fail_at=None):
        self.client = client
        self.id = ident
        self.trace_id = trace_id
        self.parent_id = parent_id
        self.updates = []
        self.ended = False
        self.fail_at = fail_at

    def start_observation(self, **kwargs):
        return self.client._make_observation(kwargs, trace_id=self.trace_id, parent_id=self.id)

    def update(self, **kwargs):
        if self.fail_at == "update":
            raise RuntimeError("private diagnostic")
        self.updates.append(kwargs)
        return self

    def end(self):
        if self.fail_at == "end":
            raise RuntimeError("private diagnostic")
        self.ended = True


class FakeClient:
    def __init__(self, fail_at=None):
        self.calls = []
        self.observations = []
        self.fail_at = fail_at

    _trace_ids = count()

    @classmethod
    def create_trace_id(cls):
        return f"{next(cls._trace_ids):032x}"

    def start_observation(self, **kwargs):
        if self.fail_at == "start":
            raise RuntimeError("private diagnostic")
        return self._make_observation(kwargs, trace_id=self.create_trace_id())

    def _make_observation(self, kwargs, *, trace_id, parent_id=None):
        self.calls.append({**kwargs, "trace_id": trace_id, "parent_span_id": parent_id})
        observation = Observation(
            self, f"span-{len(self.observations)}", trace_id, parent_id, self.fail_at
        )
        self.observations.append(observation)
        return observation

    def flush(self):
        pass

    def shutdown(self):
        pass


class Secret:
    def __init__(self, value):
        self.value = value

    def get_secret_value(self):
        return self.value


class Settings:
    langfuse_enabled = True
    langfuse_public_key = Secret("lf-public-value")
    langfuse_secret_key = Secret("lf-secret-value")
    api_key = Secret("reader-secret-value")
    admin_api_key = Secret("admin-secret-value")
    groq_api_key = Secret("groq-secret-value")
    langfuse_base_url = "https://trace.example"
    langfuse_environment = "test"
    langfuse_capture_content = False
    langfuse_max_content_chars = 12000
    langfuse_timeout_seconds = 2
    langfuse_shutdown_timeout_seconds = 3


def test_metadata_mode_records_safe_operation_metadata_and_nested_generation():
    client = FakeClient()
    monitoring = LangfuseMonitoring(client)
    llm = MonitoredLLMClient(
        type(
            "LLM",
            (),
            {
                "chat": lambda self, **kwargs: {
                    "content": "answer secret123",
                    "usage": {"prompt_tokens": 2, "completion_tokens": 5, "total_tokens": 7},
                }
            },
        )(),
        monitoring,
        "model-x",
    )
    with pytest.raises(ValueError):
        monitoring.run(
            "qa.answer",
            lambda: (
                llm.chat(messages=[{"role": "user", "content": "private question"}]),
                (_ for _ in ()).throw(ValueError("private exception")),
            )[1],
        )

    root, generation = client.observations
    assert generation.id
    assert client.calls[1]["trace_id"] == client.calls[0]["trace_id"]
    assert client.calls[1]["parent_span_id"] == root.id
    assert "input" not in client.calls[0]
    assert all(
        "private question" not in str(call) and "secret123" not in str(call)
        for call in client.calls
    )
    assert root.updates[-1]["metadata"]["outcome"] == "error"
    assert generation.updates[-1]["usage_details"] == {"input": 2, "output": 5, "total": 7}
    assert all(observation.ended for observation in client.observations)


def test_capture_is_bounded_and_redacts_configured_and_common_secrets():
    client = FakeClient()
    monitoring = LangfuseMonitoring(
        client, capture_content=True, max_content_chars=60, redact_values=("private-value",)
    )
    monitoring.generation(
        lambda: {
            "content": f"private-value {SK_LIVE} {GITHUB_TOKEN}",
            "usage": {},
        },
        model="m",
        messages=[{"role": "user", "content": "token=private-value and " + "x" * 100}],
        tools=[{"api_key": "private-value", "name": "tool"}],
        temperature=0.3,
    )
    call = client.calls[0]
    serialized_input = call["input"]
    assert isinstance(serialized_input, str)
    assert len(serialized_input) <= 76
    serialized = str(call) + str(client.observations[0].updates)
    assert "private-value" not in serialized
    assert SK_LIVE not in serialized
    assert GITHUB_TOKEN not in serialized
    assert "[REDACTED]" in serialized
    assert "[TRUNCATED]" in serialized
    output = client.observations[0].updates[-1]["output"]
    assert isinstance(output, str)
    assert "[REDACTED]" in output
    assert SK_LIVE not in output
    assert GITHUB_TOKEN not in output


def test_monitoring_failures_do_not_repeat_or_hide_llm_results():
    for fail_at in ("start", "update", "end"):
        client = FakeClient(fail_at=fail_at)
        monitoring = LangfuseMonitoring(client)

        class CountingLLM:
            calls = 0

            def chat(self, **kwargs):
                self.calls += 1
                return {"content": "ok"}

        inner = CountingLLM()
        llm = MonitoredLLMClient(inner, monitoring, "m")
        assert llm.chat(messages=[]) == {"content": "ok"}
        assert inner.calls == 1

    client = FakeClient(fail_at="update")
    monitoring = LangfuseMonitoring(client)
    failure = ValueError("provider failure")

    class FailingLLM:
        calls = 0

        def chat(self, **kwargs):
            self.calls += 1
            raise failure

    inner = FailingLLM()
    with pytest.raises(ValueError) as raised:
        MonitoredLLMClient(inner, monitoring, "m").chat(messages=[])
    assert raised.value is failure
    assert inner.calls == 1


def test_capture_budget_includes_huge_tool_keys_and_values():
    client = FakeClient()
    monitoring = LangfuseMonitoring(client, capture_content=True, max_content_chars=80)
    monitoring.generation(
        lambda: {"content": "ok", "usage": {}},
        model="m",
        messages=[],
        tools=[{"x" * 20000: "y" * 20000} for _ in range(100)],
        temperature=0,
    )
    captured = client.calls[0]["input"]
    assert isinstance(captured, str)
    assert len(captured) <= 96
    assert "[TRUNCATED]" in captured


def test_context_isolated_between_concurrent_roots():
    client = FakeClient()
    monitoring = LangfuseMonitoring(client)
    barrier = threading.Barrier(2)

    def operation():
        barrier.wait(timeout=2)
        monitoring.generation(
            lambda: {"content": "ok"}, model="m", messages=[], tools=None, temperature=0
        )

    threads = [
        threading.Thread(target=monitoring.run, args=(f"root-{i}", operation)) for i in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
    assert not any(thread.is_alive() for thread in threads)
    roots = {call["trace_id"] for call in client.calls if call["name"].startswith("root-")}
    children = [call for call in client.calls if call.get("as_type") == "generation"]
    assert len(roots) == 2
    assert {call["trace_id"] for call in children} == roots
    assert all(call["parent_span_id"] is not None for call in children)
    assert all(
        call["parent_span_id"] is None for call in client.calls if call["name"].startswith("root-")
    )
    assert NoopMonitoring().run("x", lambda: 3) == 3


def test_disabled_factory_does_not_need_credentials_or_construct_sdk():
    settings = type("Settings", (), {"langfuse_enabled": False})()
    monitoring = LangfuseMonitoring.from_settings(settings)
    assert monitoring.run("disabled", lambda: "unchanged") == "unchanged"


def test_from_settings_redacts_all_configured_credentials(monkeypatch):
    import langfuse
    import opentelemetry.sdk.trace

    client = FakeClient()
    sdk_kwargs = {}
    monkeypatch.setattr(langfuse, "Langfuse", lambda **kwargs: sdk_kwargs.update(kwargs) or client)
    tracer_settings = {}

    class Provider:
        def __init__(self, **kwargs):
            tracer_settings.update(kwargs)

    monkeypatch.setattr(opentelemetry.sdk.trace, "TracerProvider", Provider)
    monitoring = LangfuseMonitoring.from_settings(Settings())
    assert isinstance(monitoring, LangfuseMonitoring)
    assert set(monitoring._redact_values) == {
        "lf-public-value",
        "lf-secret-value",
        "reader-secret-value",
        "admin-secret-value",
        "groq-secret-value",
    }
    assert tracer_settings == {"shutdown_on_exit": False}
    assert sdk_kwargs["tracer_provider"] is not None
    capture_client = FakeClient()
    monitor = LangfuseMonitoring(
        capture_client, capture_content=True, redact_values=monitoring._redact_values
    )
    monitor.generation(
        lambda: {"content": "safe"},
        model="m",
        messages=[{"content": " ".join(monitoring._redact_values)}],
        tools=None,
        temperature=0,
    )
    assert all(
        secret not in capture_client.calls[0]["input"] for secret in monitoring._redact_values
    )


def test_sdk_constructor_failure_returns_noop(monkeypatch):
    import langfuse

    def fail(**kwargs):
        raise RuntimeError("sensitive construction detail")

    monkeypatch.setattr(langfuse, "Langfuse", fail)
    monitoring = LangfuseMonitoring.from_settings(Settings())
    assert isinstance(monitoring, NoopMonitoring)
    assert monitoring.run("operation", lambda: "result") == "result"


def test_close_is_idempotent_and_bounded():
    entered = threading.Event()
    release = threading.Event()

    class BlockingClient(FakeClient):
        def shutdown(self):
            self.shutdown_calls = getattr(self, "shutdown_calls", 0) + 1
            entered.set()
            release.wait(timeout=2)

    client = BlockingClient()
    monitoring = LangfuseMonitoring(client, shutdown_timeout_seconds=0.02)
    started = time.monotonic()
    monitoring.close()
    monitoring.close()
    assert time.monotonic() - started < 0.2
    assert entered.wait(timeout=0.2)
    assert client.shutdown_calls == 1
    release.set()


def test_sdk_debug_logs_cannot_emit_content(monkeypatch, caplog):
    import logging

    import langfuse

    client = FakeClient()
    monkeypatch.setenv("LANGFUSE_DEBUG", "true")
    monkeypatch.setattr(langfuse, "Langfuse", lambda **kwargs: client)
    root = logging.getLogger()
    prior_level = root.level
    root.setLevel(logging.DEBUG)
    try:
        LangfuseMonitoring.from_settings(Settings())
        logging.getLogger("langfuse").debug("canary private prompt")
        logging.getLogger("opentelemetry.exporter").error("canary private response")
    finally:
        root.setLevel(prior_level)
    assert "canary private prompt" not in caplog.text
    assert "canary private response" not in caplog.text


def test_bad_observation_id_does_not_break_application_result():
    client = FakeClient()

    class BadIdObservation:
        @property
        def id(self):
            raise RuntimeError("private SDK state")

        def update(self, **kwargs):
            pass

        def end(self):
            pass

    client.start_observation = lambda **kwargs: BadIdObservation()
    monitoring = LangfuseMonitoring(client)
    assert monitoring.run("root", lambda: "result") == "result"


def test_run_preserves_requested_observation_type():
    client = FakeClient()
    monitoring = LangfuseMonitoring(client)

    assert monitoring.run("retrieve-context", lambda: ["safe"], as_type="retriever") == ["safe"]
    assert client.calls[0]["as_type"] == "retriever"


def test_noop_run_accepts_observation_type():
    assert NoopMonitoring().run("retrieve-context", lambda: 7, as_type="retriever") == 7
