from fastapi import APIRouter, Depends, HTTPException, status

from legal_assistant.generation.pipeline import answer_question, inspect_question
from ..dependencies import verify_api_key
from ..models.schemas import AskRequest, AnswerResponse, InspectResponse, RetrievedChunkResponse

router = APIRouter(prefix="/api", tags=["qa"])


@router.post("/ask", response_model=AnswerResponse, summary="Answer a legal question")
async def ask(request: AskRequest, _: str = Depends(verify_api_key)) -> AnswerResponse:
    try:
        result = answer_question(
            request.question,
            document_type=request.document_type,
        )
        return AnswerResponse(**result)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline error: {exc}",
        )


@router.post("/inspect", response_model=InspectResponse, summary="Inspect retrieval and answer")
async def inspect(request: AskRequest, _: str = Depends(verify_api_key)) -> InspectResponse:
    try:
        result = inspect_question(
            request.question,
            document_type=request.document_type,
        )
        retrieved = [
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
        ]
        return InspectResponse(
            question=result["question"],
            retrieved=retrieved,
            answer=AnswerResponse(**result["answer"]),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inspection error: {exc}",
        )
