from fastapi import APIRouter, Depends, HTTPException, status

from legal_assistant.agent.legal_agent import LegalAgent, run_fixed_workflow, compare_strategies
from ..dependencies import verify_api_key
from ..models.schemas import AgentComparisonResponse, AgentRequest, AgentResponse

router = APIRouter(prefix="/api", tags=["agent"])


@router.post(
    "/agent",
    response_model=AgentResponse | AgentComparisonResponse,
    summary="Run the legal agent or compare strategies",
)
async def run_agent(
    request: AgentRequest,
    _: str = Depends(verify_api_key),
) -> AgentResponse | AgentComparisonResponse:
    """Run the selected legal-agent strategy."""
    try:
        if request.strategy == "agent":
            report = LegalAgent().run(request.question)
        elif request.strategy == "fixed":
            report = run_fixed_workflow(request.question)
        else:
            report = compare_strategies(request.question, runs=request.runs)
        if request.strategy == "compare":
            return AgentComparisonResponse.model_validate(report)
        return AgentResponse.model_validate(report)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent error: {exc}",
        )
