from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.agent_engine.agents.registry import AgentMeta
from core.agent_engine.subagent_planner_provider import (
    HybridSubagentPlannerProvider,
    LLMSubagentPlannerProvider,
    RuleSubagentPlannerProvider,
)
from core.agent_engine.subagent_planner_provider_protocols import (
    SubagentPlannerDecision,
    SubagentPlannerProvider,
)
from shared.config.settings import settings


class SubagentPlannerGateway:
    def __init__(self) -> None:
        self._providers: dict[str, SubagentPlannerProvider] = {
            "rule": RuleSubagentPlannerProvider(),
            "llm": LLMSubagentPlannerProvider(),
            "hybrid": HybridSubagentPlannerProvider(),
        }

    async def resolve(
        self,
        *,
        meta: AgentMeta,
        user_input: str,
        state: Mapping[str, Any],
        available_sub_agents: Sequence[str],
        provider_name: str | None = None,
    ) -> SubagentPlannerDecision:
        resolved_name = str(
            provider_name
            or settings.get(
                "orch_subagent_planner_provider",
                getattr(settings, "orch_subagent_planner_provider", "rule"),
            )
        ).lower()
        provider = self._providers.get(resolved_name, self._providers["rule"])
        return await provider.resolve(
            meta=meta,
            user_input=user_input,
            state=state,
            available_sub_agents=available_sub_agents,
        )


subagent_planner_gateway = SubagentPlannerGateway()
