from __future__ import annotations

from typing import Any, Mapping, Tuple

from core.agent_engine.agents.registry import AgentMeta
from core.agent_engine.mode_selector import (
    resolve_mode,
    should_force_downgrade,
    should_upgrade_to_plan_execute,
)
from core.agent_engine.workflows.plan_execute import build_plan_execute_graph


def build_orchestrator(
    meta: AgentMeta,
    tenant_id: str,
    user_input: str,
    state: Mapping[str, Any] | None = None,
) -> Tuple[Any, str]:
    mode = resolve_mode(meta, tenant_id)
    if should_upgrade_to_plan_execute(user_input):
        mode = "plan_execute"
    if mode == "plan_execute" and should_force_downgrade(
        replan_count=int((state or {}).get("replan_count", 0)),
        error_count=int((state or {}).get("error_count", 0)),
    ):
        mode = "command"
    if mode == "plan_execute":
        return build_plan_execute_graph(meta), mode
    return meta.factory(), "command"
