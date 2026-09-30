"""PDF → text helper for the upload endpoint."""
from __future__ import annotations

import io

from legal_rag.infrastructure.errors import DocumentSourceError


def extract_pdf_text(pdf_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentSourceError("pypdf not installed") from exc
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()
