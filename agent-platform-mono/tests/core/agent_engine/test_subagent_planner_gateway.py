from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage

from core.agent_engine.agents.registry import AgentMeta
from core.agent_engine.subagent_planner_gateway import subagent_planner_gateway
from shared.config.settings import settings


class FakeChatModel:
    def __init__(self, content: str) -> None:
        self._content = content

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        return AIMessage(content=self._content)


def _meta() -> AgentMeta:
    return AgentMeta(
        agent_id="lead-agent",
        name="Lead Agent",
        description="desc",
        factory=lambda: None,
        orchestration_mode="plan_execute",
        sub_agents=["policy-assistant", "claim-assistant"],
    )


async def test_subagent_planner_gateway_rule_provider() -> None:
    settings._static.orch_subagent_planner_provider = "rule"
    decision = await subagent_planner_gateway.resolve(
        meta=_meta(),
        user_input="请并行处理，并按投票策略输出",
        state={"memory_context": "", "rag_context": ""},
        available_sub_agents=["policy-assistant", "claim-assistant"],
    )

    assert decision["executor"] == "subagents"
    assert decision["aggregation_strategy"] == "vote"
    assert decision["decision_source"] == "planner_rule_router"


async def test_subagent_planner_gateway_llm_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    settings._static.orch_subagent_planner_provider = "llm"
    monkeypatch.setattr(
        "core.agent_engine.subagent_planner_provider.llm_gateway.get_chat",
        lambda tools, scene: FakeChatModel(
            '{"executor":"subagents","aggregation_strategy":"confidence_rank","reason":"llm_selected"}'
        ),
    )

    decision = await subagent_planner_gateway.resolve(
        meta=_meta(),
        user_input="请综合判断谁更可信",
        state={"memory_context": "memory", "rag_context": "rag"},
        available_sub_agents=["policy-assistant", "claim-assistant"],
    )

    assert decision["executor"] == "subagents"
    assert decision["aggregation_strategy"] == "confidence_rank"
    assert decision["decision_source"] == "planner_llm_router"


async def test_subagent_planner_gateway_hybrid_provider_falls_back_to_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings._static.orch_subagent_planner_provider = "hybrid"
    settings._static.orch_subagent_hybrid_merge_mode = "consensus_weighted"
    settings._static.orch_subagent_hybrid_rule_weight = 0.1
    settings._static.orch_subagent_hybrid_llm_weight = 0.9
    monkeypatch.setattr(
        "core.agent_engine.subagent_planner_provider.llm_gateway.get_chat",
        lambda tools, scene: FakeChatModel(
            '{"executor":"subagents","aggregation_strategy":"conflict_resolution","reason":"llm_conflict"}'
        ),
    )

    decision = await subagent_planner_gateway.resolve(
        meta=_meta(),
        user_input="请综合这些结论给出判断",
        state={"memory_context": "", "rag_context": ""},
        available_sub_agents=["policy-assistant", "claim-assistant"],
    )

    assert decision["executor"] == "subagents"
    assert decision["aggregation_strategy"] == "conflict_resolution"
    assert decision["decision_source"] == "planner_hybrid_merged"
    assert decision["merge_debug"]["merge_mode"] == "consensus_weighted"


async def test_subagent_planner_gateway_supports_scoped_aggregation_overrides() -> None:
    settings._nacos_cache["orch_subagent_aggregation_overrides"] = {
        "tenants": {
            "tenant-a": {
                "all": {"min_confidence": 0.75},
                "strategies": {"confidence_rank": {"min_confidence": 0.8}},
            }
        },
        "agents": {
            "lead-agent": {
                "all": {"preferred_agent_ids": ["claim-assistant", "policy-assistant"]},
            }
        },
        "tenant_agents": {
            "tenant-a:lead-agent": {
                "strategies": {"confidence_rank": {"min_confidence": 0.92}},
            }
        },
    }
    settings._static.orch_subagent_planner_provider = "rule"
    decision = await subagent_planner_gateway.resolve(
        meta=_meta(),
        user_input="请并行执行，并按最可信结果输出",
        state={"tenant_id": "tenant-a", "memory_context": "", "rag_context": ""},
        available_sub_agents=["policy-assistant", "claim-assistant"],
    )
    settings._nacos_cache.pop("orch_subagent_aggregation_overrides", None)

    assert decision["executor"] == "subagents"
    assert decision["aggregation_strategy"] == "confidence_rank"
    assert decision["aggregation_params"]["min_confidence"] == 0.92
    assert decision["preferred_agent_ids"] == ["claim-assistant", "policy-assistant"]
