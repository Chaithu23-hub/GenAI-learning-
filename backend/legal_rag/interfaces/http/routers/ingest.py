"""POST /api/ingest and POST /api/upload"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from legal_rag.application.workflows import IngestionService
from legal_rag.composition import Container
from legal_rag.infrastructure.errors import PdfExtractionError
from legal_rag.interfaces.http.dependencies import (
    get_container,
    get_ingestion_service,
    verify_admin_api_key,
)
from legal_rag.interfaces.http.schemas import IngestResponse

router = APIRouter(prefix="/api", tags=["ingest"])


@router.post("/ingest", response_model=IngestResponse, summary="Re-ingest all documents")
async def ingest(
    _: Annotated[str, Depends(verify_admin_api_key)],
    ingestion: Annotated[IngestionService, Depends(get_ingestion_service)],
    container: Annotated[Container, Depends(get_container)],
) -> IngestResponse:
    count = await container.work_executor.run(
        ingestion.ingest,
        exclusive=True,
        operation_name="ingest-documents",
        observation_type="chain",
    )
    return IngestResponse(
        chunks_ingested=count,
        message=f"Successfully ingested {count} chunks from {container.settings.docs_dir}",
    )


@router.post("/upload", response_model=IngestResponse, summary="Upload and ingest PDF files")
async def upload_pdf(
    files: Annotated[list[UploadFile], File(...)],
    _: Annotated[str, Depends(verify_admin_api_key)],
    ingestion: Annotated[IngestionService, Depends(get_ingestion_service)],
    container: Annotated[Container, Depends(get_container)],
    auto_ingest: bool = True,
) -> IngestResponse:
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files supplied.",
        )
    settings = container.settings
    if len(files) > settings.upload_max_files:
        raise HTTPException(413, "Too many files in one upload.")
    documents = []
    for upload in files:
        filename = upload.filename or ""
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{filename}' is not a PDF.",
            )
        # Read no more than the limit plus one byte, including for direct callers.
        data = await upload.read(settings.upload_max_file_bytes + 1)
        if len(data) > settings.upload_max_file_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File '{filename}' exceeds the upload size limit.",
            )
        stem = Path(filename).stem
        documents.append((stem, data))

    def process_upload():
        # Validate every PDF before changing the corpus. Only one mutation runs at a time.
        parsed = [(stem, container.pdf_extractor.extract(data)) for stem, data in documents]
        if any(not text.strip() for _, text in parsed):
            raise PdfExtractionError("PDF contains no extractable text.")
        container.upload_document_source.write_documents(
            [(f"{stem}.md", f"# {stem}\n\n{text}\n") for stem, text in parsed]
        )
        return ingestion.ingest() if (auto_ingest and parsed) else 0

    chunks_ingested = await container.work_executor.run(
        process_upload,
        exclusive=True,
        operation_name="upload-documents",
        observation_type="chain",
    )
    return IngestResponse(
        chunks_ingested=chunks_ingested,
        message=f"Wrote {len(documents)} markdown file(s). Ingested {chunks_ingested} chunks.",
    )
