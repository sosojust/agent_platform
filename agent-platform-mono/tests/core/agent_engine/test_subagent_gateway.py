import asyncio
from typing import Any

from langchain_core.messages import AIMessage

from core.agent_engine.agents.registry import AgentMeta, AgentRegistry
from core.agent_engine.subagent_gateway import (
    SubagentGateway,
    SubagentTask,
    make_subagent_executor_node,
)


class FakeGraph:
    def __init__(self, name: str, calls: list[dict[str, object]], delay: float = 0.0) -> None:
        self._name = name
        self._calls = calls
        self._delay = delay

    async def ainvoke(self, state: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        self._calls.append({"state": state, "config": config})
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        return {
            "messages": [AIMessage(content=f"{self._name} 完成")],
            "step_count": 2,
        }


def _make_meta(agent_id: str, graph: FakeGraph) -> AgentMeta:
    return AgentMeta(
        agent_id=agent_id,
        name=agent_id,
        description="test",
        factory=lambda: graph,
    )


async def test_run_batch_executes_subagents_with_isolated_threads() -> None:
    calls: list[dict[str, object]] = []
    registry = AgentRegistry()
    registry.register(_make_meta("policy-assistant", FakeGraph("policy", calls)))
    registry.register(_make_meta("claim-assistant", FakeGraph("claim", calls)))
    gateway = SubagentGateway(registry)

    results = await gateway.run_batch(
        [
            SubagentTask(agent_id="policy-assistant", user_input="查询保单", task_id="policy"),
            SubagentTask(agent_id="claim-assistant", user_input="查询理赔", task_id="claim"),
        ],
        tenant_id="tenant-a",
        parent_conversation_id="conv-parent",
        parent_agent_id="lead-agent",
        shared_context="用户希望并行汇总保单和理赔结果",
        checkpointer=object(),
        max_concurrency=2,
        timeout_seconds=1.0,
    )

    assert [result.status for result in results] == ["success", "success"]
    assert [result.conversation_id for result in results] == [
        "conv-parent:policy",
        "conv-parent:claim",
    ]
    assert all(result.duration_ms >= 0 for result in results)
    assert len(calls) == 2
    first_call = calls[0]
    first_state = first_call["state"]
    assert isinstance(first_state, dict)
    assert first_state["tenant_id"] == "tenant-a"
    assert first_state["metadata"]["parent_conversation_id"] == "conv-parent"
    assert first_state["metadata"]["parent_agent_id"] == "lead-agent"
    assert "用户希望并行汇总保单和理赔结果" in first_state["messages"][0].content
    first_config = first_call["config"]
    assert isinstance(first_config, dict)
    assert first_config["configurable"]["thread_id"] == "conv-parent:policy"


async def test_run_batch_returns_error_for_missing_agent() -> None:
    gateway = SubagentGateway(AgentRegistry())

    results = await gateway.run_batch(
        [SubagentTask(agent_id="missing-agent", user_input="处理任务")],
        tenant_id="tenant-a",
        parent_conversation_id="conv-parent",
        checkpointer=object(),
        timeout_seconds=1.0,
    )

    assert len(results) == 1
    assert results[0].status == "error"
    assert "not found" in results[0].error
    assert results[0].duration_ms >= 0


async def test_make_subagent_executor_node_uses_default_shared_context() -> None:
    calls: list[dict[str, object]] = []
    registry = AgentRegistry()
    registry.register(_make_meta("policy-assistant", FakeGraph("policy", calls)))
    gateway = SubagentGateway(registry)
    node = make_subagent_executor_node(
        lambda state: [SubagentTask(agent_id="policy-assistant", user_input="整理结论")],
        gateway=gateway,
        timeout_seconds=1.0,
    )

    result = await node(
        {
            "conversation_id": "conv-parent",
            "tenant_id": "tenant-a",
            "memory_context": "用户最近咨询过保单有效期",
            "rag_context": "知识库命中保单状态解释",
            "metadata": {"agent_id": "lead-agent"},
        }
    )

    assert result["subagent_results"][0]["status"] == "success"
    assert len(calls) == 1
    state = calls[0]["state"]
    assert isinstance(state, dict)
    assert "用户最近咨询过保单有效期" in state["messages"][0].content
    assert "知识库命中保单状态解释" in state["messages"][0].content
