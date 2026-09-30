"""POST /api/agent"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from legal_rag.application.agents.legal_agent import FixedWorkflow, LegalAgent, compare_strategies
from legal_rag.interfaces.http.dependencies import (
    get_agent_factory,
    get_fixed_factory,
    verify_api_key,
)
from legal_rag.interfaces.http.schemas import (
    AgentComparisonResponse,
    AgentRequest,
    AgentResponse,
)

router = APIRouter(prefix="/api", tags=["agent"])


@router.post(
    "/agent",
    response_model=AgentResponse | AgentComparisonResponse,
    summary="Run the legal agent or compare strategies",
)
async def run_agent(
    request: AgentRequest,
    _: str = Depends(verify_api_key),
    agent_factory=Depends(get_agent_factory),
    fixed_factory=Depends(get_fixed_factory),
) -> AgentResponse | AgentComparisonResponse:
    if request.strategy == "agent":
        report = agent_factory().run(request.question)
        return AgentResponse.model_validate(report)
    if request.strategy == "fixed":
        report = fixed_factory().run(request.question)
        return AgentResponse.model_validate(report)
    report = compare_strategies(
        request.question,
        agent_factory=agent_factory, fixed_factory=fixed_factory, runs=request.runs,
    )
    return AgentComparisonResponse.model_validate(report)
