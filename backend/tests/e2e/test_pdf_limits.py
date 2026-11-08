"""Real isolated parser tests may create child processes and temporary PDFs."""

import io
from pathlib import Path

import pytest
from pypdf import PdfWriter

from legal_rag.infrastructure.documents import pdf_loader
from legal_rag.infrastructure.errors import PdfExtractionError, PdfTimeoutError


def blank_pdf(pages=1):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=100, height=100)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_isolated_parser_rejects_excess_pages():
    parser = pdf_loader.IsolatedPDFTextExtractor(
        max_pages=1, max_characters=1000, timeout_seconds=10, memory_mb=512, max_input_bytes=10000
    )
    with pytest.raises(PdfExtractionError, match="page limit"):
        parser.extract(blank_pdf(2))


def test_isolated_parser_accepts_small_pdf_and_rejects_invalid_content():
    parser = pdf_loader.IsolatedPDFTextExtractor(
        max_pages=2, max_characters=1000, timeout_seconds=10, memory_mb=512, max_input_bytes=10000
    )
    assert parser.extract(blank_pdf()) == ""
    with pytest.raises(PdfExtractionError):
        parser.extract(b"not a pdf")


def test_isolated_parser_input_limit_applies_to_non_http_callers():
    parser = pdf_loader.IsolatedPDFTextExtractor(
        max_pages=2, max_characters=1000, timeout_seconds=10, memory_mb=512, max_input_bytes=8
    )
    with pytest.raises(PdfExtractionError, match="input limit"):
        parser.extract(b"x" * 9)


def test_isolated_parser_bounds_extracted_text():
    pdf = (
        Path(__file__).resolve().parents[2]
        / "data/shared-corpus/contracts-pdf/MSA-2026-014_Northwind_Master_Services_Agreement.pdf"
    )
    parser = pdf_loader.IsolatedPDFTextExtractor(
        max_pages=100,
        max_characters=10,
        timeout_seconds=10,
        memory_mb=512,
        max_input_bytes=25 * 1024 * 1024,
    )
    with pytest.raises(PdfExtractionError, match="output limit"):
        parser.extract(pdf.read_bytes())


def test_parser_timeout_terminates_and_reaps_child(monkeypatch):
    real_popen = pdf_loader.subprocess.Popen
    processes = []

    def start(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        processes.append(child)
        return child

    monkeypatch.setattr(pdf_loader.subprocess, "Popen", start)
    parser = pdf_loader.IsolatedPDFTextExtractor(
        max_pages=100,
        max_characters=1000,
        timeout_seconds=0.000001,
        memory_mb=512,
        max_input_bytes=10000,
    )
    with pytest.raises(PdfTimeoutError):
        parser.extract(blank_pdf())
    assert len(processes) == 1
    assert processes[0].poll() is not None


def test_worker_memory_limit_is_enforced_by_the_os():
    import subprocess
    import sys

    code = (
        "from legal_rag.infrastructure.documents.process_limits import restrict_memory\n"
        "job = restrict_memory(128)\n"
        "try:\n"
        "    block = bytearray(256 * 1024 * 1024)\n"
        "except MemoryError:\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(1)\n"
    )
    completed = subprocess.run([sys.executable, "-c", code], timeout=10, capture_output=True)
    assert completed.returncode == 0
