from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from core.agent_engine.agents.registry import AgentMeta
from core.agent_engine.subagent_gateway import SubagentResult
from core.agent_engine.workflows.state import make_initial_state
from core.agent_engine.workflows import plan_execute


class FakeChatModel:
    def __init__(self, content: str) -> None:
        self._content = content

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        return AIMessage(content=self._content)


def _meta(*, sub_agents: list[str] | None = None) -> AgentMeta:
    return AgentMeta(
        agent_id="lead-agent",
        name="Lead Agent",
        description="desc",
        factory=lambda: None,
        orchestration_mode="plan_execute",
        sub_agents=list(sub_agents or []),
    )


async def _noop_node(_: dict[str, Any]) -> dict[str, Any]:
    return {}


async def test_plan_execute_uses_subagent_batch_for_parallel_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        plan_execute,
        "make_retrieve_memory_node",
        lambda cfg: (lambda state: {"memory_context": "用户最近咨询过保单状态"}),
    )
    monkeypatch.setattr(
        plan_execute,
        "make_retrieve_rag_node",
        lambda cfg: (lambda state: {"rag_context": "知识库提供了理赔进度定义"}),
    )
    monkeypatch.setattr(plan_execute, "make_update_memory_node", lambda cfg: _noop_node)
    monkeypatch.setattr(
        "core.agent_engine.workflows.plan_execute.llm_gateway.get_chat",
        lambda tools, scene: FakeChatModel("最终汇总"),
    )

    async def fake_run_batch(
        tasks: list[Any],
        *,
        tenant_id: str,
        parent_conversation_id: str,
        parent_agent_id: str = "",
        shared_context: str = "",
        **_: Any,
    ) -> list[SubagentResult]:
        captured["tasks"] = tasks
        captured["tenant_id"] = tenant_id
        captured["parent_conversation_id"] = parent_conversation_id
        captured["parent_agent_id"] = parent_agent_id
        captured["shared_context"] = shared_context
        return [
            SubagentResult(
                task_id="policy-assistant",
                agent_id="policy-assistant",
                conversation_id="conv-1:policy-assistant",
                status="success",
                output="保单状态正常",
                step_count=2,
                mode="command",
            ),
            SubagentResult(
                task_id="claim-assistant",
                agent_id="claim-assistant",
                conversation_id="conv-1:claim-assistant",
                status="success",
                output="理赔处理中",
                step_count=2,
                mode="command",
            ),
        ]

    monkeypatch.setattr("core.agent_engine.workflows.plan_execute.subagent_gateway.run_batch", fake_run_batch)
    monkeypatch.setattr(
        "core.agent_engine.workflows.plan_execute.agent_gateway.get",
        lambda agent_id: AgentMeta(
            agent_id=agent_id,
            name=f"{agent_id}-name",
            description="child",
            factory=lambda: None,
        ),
    )

    graph = plan_execute.build_plan_execute_graph(_meta(sub_agents=["policy-assistant", "claim-assistant"]))
    initial_state = make_initial_state(
        [HumanMessage(content="请并行查询保单和理赔信息，并汇总告诉我")],
        "conv-1",
        "tenant-a",
    )

    result = await graph.ainvoke(initial_state)

    assert result["messages"][-1].content == "最终汇总"
    assert result["route_decision"]["executor"] == "subagents"
    assert result["route_decision"]["aggregation_strategy"] == "summary"
    assert len(result["subagent_results"]) == 2
    assert result["subagent_aggregation"]["strategy"] == "summary"
    assert result["subagent_aggregation"]["success_count"] == 2
    assert result["subagent_metrics"]["strategy"] == "summary"
    assert result["subagent_metrics"]["task_count"] == 2
    assert result["past_steps"][0]["subagent_results"][0]["agent_id"] == "policy-assistant"
    assert result["past_steps"][0]["subagent_aggregation"]["selected_agent_ids"] == [
        "policy-assistant",
        "claim-assistant",
    ]
    assert captured["tenant_id"] == "tenant-a"
    assert captured["parent_conversation_id"] == "conv-1"
    assert captured["parent_agent_id"] == "lead-agent"
    assert "用户最近咨询过保单状态" in captured["shared_context"]
    assert "知识库提供了理赔进度定义" in captured["shared_context"]
    assert len(captured["tasks"]) == 2


async def test_plan_execute_falls_back_to_llm_executor_without_subagents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plan_execute, "make_retrieve_memory_node", lambda cfg: _noop_node)
    monkeypatch.setattr(plan_execute, "make_retrieve_rag_node", lambda cfg: _noop_node)
    monkeypatch.setattr(plan_execute, "make_update_memory_node", lambda cfg: _noop_node)

    calls: list[str] = []

    def fake_get_chat(tools: list[Any], scene: str) -> FakeChatModel:
        calls.append(scene)
        if scene == "plan_execute_step":
            return FakeChatModel("步骤结果")
        return FakeChatModel("最终总结")

    monkeypatch.setattr("core.agent_engine.workflows.plan_execute.llm_gateway.get_chat", fake_get_chat)

    graph = plan_execute.build_plan_execute_graph(_meta())
    initial_state = make_initial_state(
        [HumanMessage(content="先查保单，再总结")],
        "conv-2",
        "tenant-b",
    )

    result = await graph.ainvoke(initial_state)

    assert result["messages"][-1].content == "最终总结"
    assert result["route_decision"]["executor"] == "llm"
    assert calls == ["plan_execute_step", "plan_execute_step", "plan_execute_summary"]


async def test_plan_execute_uses_explicit_vote_strategy_and_emits_custom_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plan_execute, "make_retrieve_memory_node", lambda cfg: _noop_node)
    monkeypatch.setattr(plan_execute, "make_retrieve_rag_node", lambda cfg: _noop_node)
    monkeypatch.setattr(plan_execute, "make_update_memory_node", lambda cfg: _noop_node)
    monkeypatch.setattr(
        "core.agent_engine.workflows.plan_execute.llm_gateway.get_chat",
        lambda tools, scene: FakeChatModel("最终汇总"),
    )

    async def fake_run_batch(
        tasks: list[Any],
        *,
        tenant_id: str,
        parent_conversation_id: str,
        parent_agent_id: str = "",
        shared_context: str = "",
        **_: Any,
    ) -> list[SubagentResult]:
        return [
            SubagentResult(
                task_id="policy-assistant",
                agent_id="policy-assistant",
                conversation_id="conv-3:policy-assistant",
                status="success",
                output="建议通过",
                step_count=2,
                mode="command",
            ),
            SubagentResult(
                task_id="claim-assistant",
                agent_id="claim-assistant",
                conversation_id="conv-3:claim-assistant",
                status="success",
                output="建议通过",
                step_count=2,
                mode="command",
            ),
            SubagentResult(
                task_id="risk-assistant",
                agent_id="risk-assistant",
                conversation_id="conv-3:risk-assistant",
                status="success",
                output="建议拒绝",
                step_count=2,
                mode="command",
            ),
        ]

    monkeypatch.setattr("core.agent_engine.workflows.plan_execute.subagent_gateway.run_batch", fake_run_batch)
    monkeypatch.setattr(
        "core.agent_engine.workflows.plan_execute.agent_gateway.get",
        lambda agent_id: AgentMeta(
            agent_id=agent_id,
            name=f"{agent_id}-name",
            description="child",
            factory=lambda: None,
        ),
    )

    graph = plan_execute.build_plan_execute_graph(
        _meta(sub_agents=["policy-assistant", "claim-assistant", "risk-assistant"])
    )
    initial_state = make_initial_state(
        [HumanMessage(content="请并行分析这三个结论，并按投票方式决定最终结果")],
        "conv-3",
        "tenant-c",
    )

    custom_event_names: list[str] = []
    async for event in graph.astream_events(initial_state, version="v2"):
        if event["event"] == "on_custom_event":
            custom_event_names.append(str(event["name"]))

    result = await graph.ainvoke(initial_state)

    assert result["route_decision"]["aggregation_strategy"] == "vote"
    assert result["subagent_aggregation"]["strategy"] == "vote"
    assert result["subagent_aggregation"]["selected_agent_ids"] == [
        "policy-assistant",
        "claim-assistant",
    ]
    assert result["subagent_metrics"]["strategy"] == "vote"
    assert "subagent.planner.decision" in custom_event_names
    assert "subagent.execution.started" in custom_event_names
    assert "subagent.aggregation.completed" in custom_event_names
    assert "subagent.metrics" in custom_event_names
