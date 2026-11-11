from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable
from contextvars import ContextVar
from itertools import islice
from typing import Any, Literal

from legal_rag.application.ports import LLMClient, Monitoring
from legal_rag.infrastructure.observability.logging import get_logger

log = get_logger(__name__)
_PARENT: ContextVar[tuple[Any, Any] | None] = ContextVar("langfuse_parent", default=None)
_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_.-]{1,80}$")
_SECRET_KEYS = re.compile(
    r"(api[_-]?key|secret|password|authorization|access[_-]?token|refresh[_-]?token)", re.I
)
_SECRET_PATTERNS = (
    (re.compile(r"\b(?:sk|gsk|hf)_[A-Za-z0-9_-]{8,}\b"), "[REDACTED]"),
    (re.compile(r"\bsk-[a-z]+-[A-Za-z0-9_-]{8,}\b", re.I), "[REDACTED]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "[REDACTED]"),
    (re.compile(r"\bxai-[A-Za-z0-9_-]{12,}\b"), "[REDACTED]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)(token|api[_-]?key|secret|password)\s*[:=]\s*([^\s,;&]+)"), r"\1=[REDACTED]"),
)


class _DropSdkDiagnostics(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not (
            record.name == "langfuse"
            or record.name.startswith("langfuse.")
            or record.name == "opentelemetry"
            or record.name.startswith("opentelemetry.")
        )


_SDK_LOG_FILTER = _DropSdkDiagnostics()


def _suppress_sdk_diagnostics() -> None:
    for logger_name in ("langfuse", "opentelemetry"):
        namespace_logger = logging.getLogger(logger_name)
        namespace_logger.addFilter(_SDK_LOG_FILTER)
        namespace_logger.addHandler(logging.NullHandler())
        namespace_logger.propagate = False
    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(_SDK_LOG_FILTER)


def _safe_event() -> None:
    log.warning("monitoring.failure", extra={"monitoring_event": "telemetry_failure"})


def _name(value: str) -> str:
    return value if _SAFE_NAME.fullmatch(value) else "operation"


class NoopMonitoring:
    def run[T](
        self,
        name: str,
        operation: Callable[[], T],
        *,
        as_type: Literal["span", "chain", "agent", "tool", "retriever"] = "span",
    ) -> T:
        return operation()

    def generation(
        self,
        operation: Callable[[], dict[str, Any]],
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
    ) -> dict[str, Any]:
        return operation()

    def close(self) -> None:
        return None


class MonitoredLLMClient:
    """LLMClient decorator that records one generation without changing its result."""

    def __init__(self, inner: LLMClient, monitoring: Monitoring, model: str):
        self._inner = inner
        self._monitoring = monitoring
        self._model = model

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        return self._monitoring.generation(
            lambda: self._inner.chat(messages=messages, tools=tools, temperature=temperature),
            model=self._model,
            messages=messages,
            tools=tools,
            temperature=temperature,
        )


class LangfuseMonitoring:
    def __init__(
        self,
        client: Any,
        *,
        capture_content: bool = False,
        max_content_chars: int = 12000,
        redact_values: tuple[str, ...] = (),
        shutdown_timeout_seconds: float = 3,
    ):
        self._client = client
        self._capture = capture_content
        self._max_chars = max(1, max_content_chars)
        self._redact_values = tuple(value for value in redact_values if value)
        self._shutdown_timeout = max(0, shutdown_timeout_seconds)
        self._closed = False
        self._close_lock = threading.Lock()

    @classmethod
    def from_settings(cls, settings: Any) -> Monitoring:
        if not settings.langfuse_enabled:
            return NoopMonitoring()
        try:
            _suppress_sdk_diagnostics()
            from langfuse import Langfuse
            from opentelemetry.sdk.trace import TracerProvider

            provider = TracerProvider(shutdown_on_exit=False)
            client = Langfuse(
                public_key=settings.langfuse_public_key.get_secret_value(),
                secret_key=settings.langfuse_secret_key.get_secret_value(),
                base_url=settings.langfuse_base_url,
                timeout=settings.langfuse_timeout_seconds,
                environment=settings.langfuse_environment,
                debug=False,
                tracer_provider=provider,
            )
            _suppress_sdk_diagnostics()
            secrets = []
            for field in (
                "langfuse_public_key",
                "langfuse_secret_key",
                "api_key",
                "admin_api_key",
                "groq_api_key",
            ):
                credential = getattr(settings, field, None)
                if credential is not None:
                    value = (
                        credential.get_secret_value()
                        if hasattr(credential, "get_secret_value")
                        else str(credential)
                    )
                    if value:
                        secrets.append(value)
            return cls(
                client,
                capture_content=settings.langfuse_capture_content,
                max_content_chars=settings.langfuse_max_content_chars,
                redact_values=tuple(secrets),
                shutdown_timeout_seconds=settings.langfuse_shutdown_timeout_seconds,
            )
        except Exception:
            _safe_event()
            return NoopMonitoring()

    def run[T](
        self,
        name: str,
        operation: Callable[[], T],
        *,
        as_type: Literal["span", "chain", "agent", "tool", "retriever"] = "span",
    ) -> T:
        return self._observe(
            name, as_type, operation, model=None, temperature=None, messages=None, tools=None
        )

    def generation(
        self,
        operation: Callable[[], dict[str, Any]],
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float,
    ) -> dict[str, Any]:
        return self._observe(
            "llm.generation",
            "generation",
            operation,
            model=model,
            temperature=temperature,
            messages=messages,
            tools=tools,
        )

    def _observe(
        self,
        name: str,
        as_type: str,
        operation: Callable[[], Any],
        *,
        model: str | None,
        temperature: float | None,
        messages: Any,
        tools: Any,
    ) -> Any:
        parent = _PARENT.get()
        parent_observation = parent[1] if parent and parent[0] is self else None
        payload: dict[str, Any] = {
            "name": _name(name),
            "as_type": as_type,
            "metadata": {"environment": "application"},
        }
        if model is not None:
            payload["model"] = model[:120]
            payload["model_parameters"] = {"temperature": temperature}
        if self._capture and as_type == "generation":
            payload["input"] = self._bounded({"messages": messages, "tools": tools})
        observation = None
        try:
            if parent_observation is not None:
                observation = parent_observation.start_observation(**payload)
            else:
                from opentelemetry import context as otel_context

                clean_context = otel_context.attach(otel_context.Context())
                try:
                    observation = self._client.start_observation(**payload)
                finally:
                    otel_context.detach(clean_context)
        except Exception:
            _safe_event()
        token = _PARENT.set((self, observation)) if observation is not None else None
        started = time.monotonic()
        try:
            result = operation()
        except BaseException:
            self._finish(observation, name, "error", started, None)
            raise
        else:
            self._finish(
                observation,
                name,
                "success",
                started,
                result,
                capture_output=as_type == "generation",
            )
            return result
        finally:
            if token is not None:
                _PARENT.reset(token)

    def _finish(
        self,
        observation: Any,
        name: str,
        outcome: str,
        started: float,
        result: Any,
        *,
        capture_output: bool = False,
    ) -> None:
        if not observation:
            return
        try:
            metadata: dict[str, Any] = {
                "outcome": outcome,
                "duration_ms": round((time.monotonic() - started) * 1000),
            }
            update: dict[str, Any] = {"metadata": metadata}
            if outcome == "error":
                update["level"] = "ERROR"
                update["status_message"] = "operation_failed"
            elif isinstance(result, dict):
                usage = result.get("usage")
                if isinstance(usage, dict):
                    usage_keys = {
                        "prompt_tokens": "input",
                        "completion_tokens": "output",
                        "total_tokens": "total",
                    }
                    update["usage_details"] = {
                        usage_keys[key]: usage[key]
                        for key in usage_keys
                        if isinstance(usage.get(key), int) and usage[key] >= 0
                    }
                if self._capture and capture_output:
                    update["output"] = self._bounded(result)
            observation.update(**update)
        except Exception:
            _safe_event()
        try:
            observation.end()
        except Exception:
            _safe_event()

    def _bounded(self, value: Any) -> str:
        node_budget = [500]
        seen: set[int] = set()

        def redact(text: str, *, clip: bool = True) -> str:
            for secret in self._redact_values:
                text = text.replace(secret, "[REDACTED]")
            for pattern, replacement in _SECRET_PATTERNS:
                text = pattern.sub(replacement, text)
            if clip and len(text) > self._max_chars:
                return text[: self._max_chars] + "[TRUNCATED]"
            return text

        def clean(item: Any, depth: int = 0) -> Any:
            node_budget[0] -= 1
            if node_budget[0] < 0 or depth > 10:
                return "[TRUNCATED]"
            if isinstance(item, str):
                return redact(item)
            if isinstance(item, dict):
                identity = id(item)
                if identity in seen:
                    return "[CYCLE]"
                seen.add(identity)
                result = {}
                for key, val in islice(item.items(), 100):
                    safe_key = redact(str(key))
                    result[safe_key] = (
                        "[REDACTED]" if _SECRET_KEYS.search(str(key)) else clean(val, depth + 1)
                    )
                if len(item) > 100:
                    result["[TRUNCATED]"] = f"{len(item) - 100} items omitted"
                seen.remove(identity)
                return result
            if isinstance(item, (list, tuple)):
                identity = id(item)
                if identity in seen:
                    return "[CYCLE]"
                seen.add(identity)
                result = [clean(part, depth + 1) for part in item[:100]]
                if len(item) > 100:
                    result.append("[TRUNCATED]")
                seen.remove(identity)
                return result
            if item is None or isinstance(item, (bool, int, float)):
                return item
            return redact(str(item))

        try:
            serialized = json.dumps(clean(value), ensure_ascii=False, separators=(",", ":"))
        except Exception:
            serialized = json.dumps("[UNAVAILABLE]")
        if len(serialized) > self._max_chars:
            return serialized[: self._max_chars] + "[TRUNCATED]"
        return serialized

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True

        def shutdown() -> None:
            try:
                self._client.shutdown()
            except Exception:
                _safe_event()

        worker = threading.Thread(target=shutdown, name="langfuse-shutdown", daemon=True)
        worker.start()
        worker.join(self._shutdown_timeout)


def from_settings(settings: Any) -> Monitoring:
    """Build monitoring lazily from validated application settings."""
    return LangfuseMonitoring.from_settings(settings)
