from typing import Any

from fastapi import APIRouter

from shared.observability.metrics_gateway import metrics_gateway

router = APIRouter(tags=["observability"])


@router.get("/observability/subagents", summary="子 Agent 监控看板快照")
async def get_subagent_observability(
    tenant_id: str = "",
    parent_agent_id: str = "",
) -> dict[str, Any]:
    return metrics_gateway.snapshot(tenant_id=tenant_id, parent_agent_id=parent_agent_id)
