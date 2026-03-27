from __future__ import annotations

from core.agent_engine.agents.registry import AgentMeta
from shared.config.settings import settings


def _in_allow_list(values: list[str], target: str) -> bool:
    return bool(values) and target in values


def resolve_mode(meta: AgentMeta, tenant_id: str) -> str:
    agent_id = str(getattr(meta, "agent_id", ""))
    if _in_allow_list(settings.orch_plan_execute_tenants, tenant_id):
        return "plan_execute"
    if _in_allow_list(settings.orch_plan_execute_agents, agent_id):
        return "plan_execute"
    mode = str(getattr(meta, "orchestration_mode", "") or settings.orch_default_mode)
    return "plan_execute" if mode == "plan_execute" else "command"


def should_upgrade_to_plan_execute(user_input: str) -> bool:
    text = (user_input or "").lower()
    keywords = [
        "分步骤",
        "一步一步",
        "逐步",
        "plan",
        "规划",
        "执行计划",
        "先做",
        "再做",
        "然后",
    ]
    return any(k in text for k in keywords)


def should_force_downgrade(replan_count: int, error_count: int) -> bool:
    if replan_count >= settings.orch_max_replans:
        return True
    return error_count > 0
