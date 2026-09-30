"""POST /api/ingest and POST /api/upload"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from legal_rag.application.workflows import IngestionService
from legal_rag.composition import Container
from legal_rag.infrastructure.documents.markdown_loader import MarkdownDocumentSource
from legal_rag.infrastructure.documents.pdf_loader import extract_pdf_text
from legal_rag.interfaces.http.dependencies import (
    get_container,
    get_ingestion_service,
    verify_api_key,
)
from legal_rag.interfaces.http.schemas import IngestResponse

router = APIRouter(prefix="/api", tags=["ingest"])

_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB per file


@router.post("/ingest", response_model=IngestResponse, summary="Re-ingest all documents")
async def ingest(
    _: str = Depends(verify_api_key),
    ingestion: IngestionService = Depends(get_ingestion_service),
    container: Container = Depends(get_container),
) -> IngestResponse:
    count = ingestion.ingest()
    return IngestResponse(
        chunks_ingested=count,
        message=f"Successfully ingested {count} chunks from {container.settings.docs_dir}",
    )


@router.post("/upload", response_model=IngestResponse, summary="Upload and ingest PDF files")
async def upload_pdf(
    files: list[UploadFile] = File(...),
    auto_ingest: bool = True,
    _: str = Depends(verify_api_key),
    ingestion: IngestionService = Depends(get_ingestion_service),
    container: Container = Depends(get_container),
) -> IngestResponse:
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No files supplied.",
        )
    source = MarkdownDocumentSource(container.settings.docs_dir)
    written = 0
    for upload in files:
        filename = upload.filename or ""
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{filename}' is not a PDF.",
            )
        data = await upload.read()
        if len(data) > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File '{filename}' exceeds {_MAX_UPLOAD_BYTES // (1024*1024)} MB.",
            )
        text = extract_pdf_text(data)
        stem = Path(filename).stem
        source.write_document(f"{stem}.md", f"# {stem}\n\n{text}\n")
        written += 1

    chunks_ingested = ingestion.ingest() if (auto_ingest and written) else 0
    return IngestResponse(
        chunks_ingested=chunks_ingested,
        message=f"Wrote {written} markdown file(s). Ingested {chunks_ingested} chunks.",
    )
