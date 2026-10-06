"""POST /api/ask and POST /api/inspect"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from legal_rag.application.workflows import QaService
from legal_rag.interfaces.http.dependencies import get_qa_service, verify_api_key
from legal_rag.interfaces.http.schemas import (
    AnswerResponse,
    AskRequest,
    InspectResponse,
    RetrievedChunkResponse,
)

router = APIRouter(prefix="/api", tags=["qa"])


@router.post("/ask", response_model=AnswerResponse, summary="Answer a legal question")
async def ask(
    request: AskRequest,
    _: Annotated[str, Depends(verify_api_key)],
    qa: Annotated[QaService, Depends(get_qa_service)],
) -> AnswerResponse:
    payload = qa.answer(request.question, document_type=request.document_type)
    return AnswerResponse(**payload)


@router.post("/inspect", response_model=InspectResponse, summary="Inspect retrieval + answer")
async def inspect(
    request: AskRequest,
    _: Annotated[str, Depends(verify_api_key)],
    qa: Annotated[QaService, Depends(get_qa_service)],
) -> InspectResponse:
    result = qa.inspect(request.question, document_type=request.document_type)
    return InspectResponse(
        question=result["question"],
        retrieved=[
            RetrievedChunkResponse(
                chunk_id=c.chunk_id,
                document=c.document,
                document_type=c.document_type,
                heading=c.heading,
                text=c.text,
                distance=c.distance,
                score=c.score,
            )
            for c in result["retrieved"]
        ],
        answer=AnswerResponse(**result["answer"]),
    )
