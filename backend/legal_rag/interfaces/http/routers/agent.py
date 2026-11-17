"""POST /api/agent"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from legal_rag.application.agents.legal_agent import compare_strategies
from legal_rag.composition import Container
from legal_rag.interfaces.http.dependencies import (
    get_agent_factory,
    get_container,
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
    _: Annotated[str, Depends(verify_api_key)],
    agent_factory: Annotated[Any, Depends(get_agent_factory)],
    fixed_factory: Annotated[Any, Depends(get_fixed_factory)],
    container: Annotated[Container, Depends(get_container)],
) -> AgentResponse | AgentComparisonResponse:
    if request.strategy == "agent":
        report = await container.work_executor.run(
            lambda: agent_factory().run(request.question),
            operation_name="run-legal-agent",
            observation_type="agent",
        )
        return AgentResponse.model_validate(report)
    if request.strategy == "fixed":
        report = await container.work_executor.run(
            lambda: fixed_factory().run(request.question),
            operation_name="run-fixed-workflow",
            observation_type="chain",
        )
        return AgentResponse.model_validate(report)
    report = await container.work_executor.run(
        lambda: compare_strategies(
            request.question,
            agent_factory=agent_factory,
            fixed_factory=fixed_factory,
            runs=request.runs,
        ),
        operation_name="compare-agent-strategies",
        observation_type="chain",
    )
    return AgentComparisonResponse.model_validate(report)
