import pytest
from typing import Literal

from core.agent_engine.agents.registry import AgentMeta
from core.agent_engine import orchestrator_factory


def _meta(mode: Literal["command", "plan_execute"] = "command") -> AgentMeta:
    return AgentMeta(
        agent_id="agent-x",
        name="agent-x",
        description="desc",
        factory=lambda: "COMMAND_GRAPH",
        orchestration_mode=mode,
    )


def test_build_orchestrator_command() -> None:
    graph, mode = orchestrator_factory.build_orchestrator(
        meta=_meta("command"),
        tenant_id="t1",
        user_input="查询保单",
        state={},
    )
    assert graph == "COMMAND_GRAPH"
    assert mode == "command"


def test_build_orchestrator_plan_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_factory, "build_plan_execute_graph", lambda meta: "PLAN_GRAPH")
    graph, mode = orchestrator_factory.build_orchestrator(
        meta=_meta("plan_execute"),
        tenant_id="t1",
        user_input="分步骤处理",
        state={"replan_count": 0, "error_count": 0},
    )
    assert graph == "PLAN_GRAPH"
    assert mode == "plan_execute"


def test_build_orchestrator_force_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_factory, "build_plan_execute_graph", lambda meta: "PLAN_GRAPH")
    graph, mode = orchestrator_factory.build_orchestrator(
        meta=_meta("plan_execute"),
        tenant_id="t1",
        user_input="分步骤处理",
        state={"replan_count": 99, "error_count": 0},
    )
    assert graph == "COMMAND_GRAPH"
    assert mode == "command"
