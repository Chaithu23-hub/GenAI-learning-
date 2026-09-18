import io
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status

from legal_assistant.ingestion.vector_store import ingest_documents
from legal_assistant import config
from ..dependencies import verify_api_key
from ..models.schemas import IngestResponse

router = APIRouter(prefix="/api", tags=["ingest"])


@router.post("/ingest", response_model=IngestResponse, summary="Re-ingest all documents")
async def ingest(_: str = Depends(verify_api_key)) -> IngestResponse:
    try:
        count = ingest_documents()
        return IngestResponse(
            chunks_ingested=count,
            message=f"Successfully ingested {count} chunks from {config.DOCS_DIR}",
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion error: {exc}",
        )


@router.post("/upload", response_model=IngestResponse, summary="Upload and ingest PDF files")
async def upload_pdf(
    files: list[UploadFile] = File(...),
    auto_ingest: bool = True,
    _: str = Depends(verify_api_key),
) -> IngestResponse:
    """
    Accept one or more PDF uploads, convert them to markdown, save to data/legal/,
    and optionally trigger a re-ingest.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="pypdf is not installed. Run: pip install pypdf",
        )

    out_dir = Path(config.DOCS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0

    for upload in files:
        if not upload.filename or not upload.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{upload.filename}' is not a PDF.",
            )
        data = await upload.read()
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(pages).strip()
        stem = Path(upload.filename).stem
        md = f"# {stem}\n\n{text}\n"
        (out_dir / f"{stem}.md").write_text(md, encoding="utf-8")
        written += 1

    chunks_ingested = 0
    if auto_ingest and written:
        chunks_ingested = ingest_documents()

    return IngestResponse(
        chunks_ingested=chunks_ingested,
        message=f"Wrote {written} markdown file(s). Ingested {chunks_ingested} chunks.",
    )
