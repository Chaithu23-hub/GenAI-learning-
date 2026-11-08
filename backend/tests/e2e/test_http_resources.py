"""Resource limits exercised at the HTTP boundary, with no real model calls."""

import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from io import BytesIO
from threading import Event

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
from pydantic import SecretStr

from legal_rag.infrastructure.errors import PdfExtractionError
from legal_rag.interfaces.http.app import create_app
from legal_rag.interfaces.http.middleware import RequestBodyLimitMiddleware
from legal_rag.interfaces.http.routers.ingest import upload_pdf
from tests.fakes.documents import FakePDFTextExtractor, MemoryDocumentSource


def make_client(container, **overrides):
    container._settings = container.settings.model_copy(update=overrides)
    app = create_app(container.settings)
    app.state.container = container
    return TestClient(app)


def test_blocking_answer_does_not_stall_health(container):
    entered, release = Event(), Event()

    class SlowQa:
        def answer(self, *args, **kwargs):
            entered.set()
            release.wait(3)
            return {
                "answer": "Ready",
                "reasoning": "Test",
                "sources": [],
                "confidence": "low",
                "out_of_scope": False,
            }

    container.qa_service = SlowQa()
    # A persistent TestClient portal models the single server event loop.
    app = create_app(container.settings)
    with TestClient(app) as client, ThreadPoolExecutor(2) as callers:
        app.state.container = container
        pending = callers.submit(client.post, "/api/ask", json={"question": "payment"})
        assert entered.wait(2)
        health = callers.submit(client.get, "/api/health")
        try:
            response = health.result(timeout=0.5)
            assert response.status_code == 200
        except TimeoutError:
            pytest.fail("A blocking answer stalled the API event loop")
        finally:
            release.set()
            pending.result(timeout=3)


def test_content_length_rejected_before_parsing(container):
    client = make_client(container, http_max_body_bytes=1024)
    response = client.post(
        "/api/ask", content=b"x" * 1025, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413


def test_streamed_body_is_also_limited(container):
    client = make_client(container, http_max_body_bytes=1024)
    response = client.post(
        "/api/ask",
        content=iter([b"x" * 800, b"x" * 800]),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_oversized_file_is_read_with_a_bound(container):
    class ObservedUpload(UploadFile):
        bytes_read = 0

        async def read(self, size=-1):
            result = await super().read(size)
            self.bytes_read += len(result)
            return result

    container._settings = container.settings.model_copy(update={"upload_max_file_bytes": 8})
    upload = ObservedUpload(file=BytesIO(b"x" * 1000), filename="large.pdf")
    with pytest.raises(HTTPException) as error:
        await upload_pdf(
            files=[upload],
            _="admin",
            ingestion=container.ingestion_service,
            container=container,
            auto_ingest=False,
        )
    assert error.value.status_code == 413
    assert upload.bytes_read <= 9


def test_upload_file_count_is_limited_before_parsing(container):
    client = make_client(container, upload_max_files=1, admin_api_key=SecretStr("admin-test-key"))
    response = client.post(
        "/api/upload",
        headers={"X-API-Key": "admin-test-key"},
        files=[
            ("files", ("one.pdf", b"not a PDF", "application/pdf")),
            ("files", ("two.pdf", b"not a PDF", "application/pdf")),
        ],
    )
    assert response.status_code == 413


def test_failed_pdf_is_never_persisted(container):
    container.pdf_extractor = FakePDFTextExtractor(error=PdfExtractionError("Invalid PDF"))
    source = MemoryDocumentSource()
    container.upload_document_source = source
    client = make_client(container)
    response = client.post(
        "/api/upload?auto_ingest=false",
        headers={"X-API-Key": "test-admin-key"},
        files={"files": ("one.pdf", b"bad pdf", "application/pdf")},
    )
    assert response.status_code == 422
    assert source.documents == {}


def test_existing_document_cannot_be_overwritten(container):
    original = (container.settings.docs_dir / "master_services_agreement.md").read_text(
        encoding="utf-8"
    )
    container.pdf_extractor = FakePDFTextExtractor(text="Changed contract")
    client = make_client(container)
    response = client.post(
        "/api/upload?auto_ingest=false",
        headers={"X-API-Key": "test-admin-key"},
        files={"files": ("master_services_agreement.pdf", b"pdf", "application/pdf")},
    )
    assert response.status_code == 409
    assert (container.settings.docs_dir / "master_services_agreement.md").read_text(
        encoding="utf-8"
    ) == original


def test_http_timeout_retains_capacity_and_liveness(container):
    entered, release = Event(), Event()

    class SlowQa:
        def answer(self, *args, **kwargs):
            entered.set()
            release.wait(3)
            return {}

    container.qa_service = SlowQa()
    client = make_client(container, http_max_concurrent_jobs=1, http_request_timeout_seconds=0.05)
    try:
        first = client.post("/api/ask", json={"question": "payment"})
        assert entered.is_set()
        assert first.status_code == 504
        second = client.post("/api/ask", json={"question": "payment"})
        assert second.status_code == 503
        assert client.get("/api/live").status_code == 200
    finally:
        release.set()
        container.work_executor.close()


@pytest.mark.asyncio
async def test_slow_body_has_a_total_transfer_deadline(container):
    container._settings = container.settings.model_copy(update={"http_body_timeout_seconds": 0.01})
    app = create_app(container.settings)
    app.state.container = container
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "path": "/api/ask",
        "raw_path": b"/api/ask",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 123),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    messages = []

    async def receive():
        await asyncio.sleep(0.1)
        return {"type": "http.request", "body": b"{}", "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    assert (
        next(message["status"] for message in messages if message["type"] == "http.response.start")
        == 408
    )


@pytest.mark.asyncio
async def test_body_deadline_is_absolute_across_frames(container):
    container._settings = container.settings.model_copy(update={"http_body_timeout_seconds": 0.05})
    app = create_app(container.settings)
    app.state.container = container
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "path": "/api/ask",
        "raw_path": b"/api/ask",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 123),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    messages = []
    frames = iter((b'{"question":', b'"payment"', b"}"))

    async def receive():
        await asyncio.sleep(0.025)
        try:
            body = next(frames)
        except StopIteration:
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.request", "body": body, "more_body": True}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    assert (
        next(message["status"] for message in messages if message["type"] == "http.response.start")
        == 408
    )


@pytest.mark.asyncio
async def test_timed_out_body_releases_slot_for_healthy_transfer():
    async def app(scope, receive, send):
        message = await receive()
        assert message["body"] == b"ok"
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = RequestBodyLimitMiddleware(
        app,
        max_bytes=1024,
        max_requests=1,
        timeout_seconds=0.01,
    )
    scope = {"type": "http", "method": "POST", "headers": []}
    first_messages = []

    async def slow_receive():
        await asyncio.sleep(0.1)
        return {"type": "http.request", "body": b"ok", "more_body": False}

    async def first_send(message):
        first_messages.append(message)

    await middleware(scope, slow_receive, first_send)
    assert next(m["status"] for m in first_messages if m["type"] == "http.response.start") == 408

    second_messages = []

    async def healthy_receive():
        return {"type": "http.request", "body": b"ok", "more_body": False}

    async def second_send(message):
        second_messages.append(message)

    await middleware(scope, healthy_receive, second_send)
    assert next(m["status"] for m in second_messages if m["type"] == "http.response.start") == 204
