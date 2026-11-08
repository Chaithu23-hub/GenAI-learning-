"""Bounded, isolated PDF extraction for the upload endpoint."""

from __future__ import annotations

import json
import subprocess
import sys

from legal_rag.infrastructure.errors import PdfExtractionError, PdfTimeoutError


class IsolatedPDFTextExtractor:
    """Parse uploads in a child process that can be killed and memory-limited."""

    def __init__(
        self,
        *,
        max_pages: int,
        max_characters: int,
        timeout_seconds: float,
        memory_mb: int,
        max_input_bytes: int,
    ):
        self._max_input_bytes = max_input_bytes
        self._timeout = timeout_seconds
        self._limits = [max_pages, max_characters, memory_mb, max_input_bytes]

    def extract(self, pdf_bytes: bytes) -> str:
        if len(pdf_bytes) > self._max_input_bytes:
            raise PdfExtractionError("PDF input limit exceeded.")
        command = [
            sys.executable,
            "-m",
            "legal_rag.infrastructure.documents.pdf_worker",
            *(str(limit) for limit in self._limits),
        ]
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise PdfExtractionError("Unable to start isolated PDF parser.") from exc
        try:
            output, _ = process.communicate(input=pdf_bytes, timeout=self._timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.communicate()
            raise PdfTimeoutError("PDF processing deadline exceeded.") from exc
        except BaseException:
            process.kill()
            process.communicate()
            raise
        try:
            payload = json.loads(output)
        except (ValueError, UnicodeError) as exc:
            raise PdfExtractionError("PDF parser failed within its resource budget.") from exc
        if process.returncode or "error" in payload:
            raise PdfExtractionError(payload.get("error", "PDF parser failed."))
        text = payload.get("text")
        if not isinstance(text, str) or len(text) > self._limits[1]:
            raise PdfExtractionError("PDF output limit exceeded.")
        return text
