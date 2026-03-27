from typing import Literal

import pytest

from core.agent_engine.agents.registry import AgentMeta
from core.agent_engine import mode_selector
from shared.config.settings import settings


def _meta(mode: Literal["command", "plan_execute"] = "command") -> AgentMeta:
    return AgentMeta(
        agent_id="a1",
        name="a1",
        description="d",
        factory=lambda: None,
        orchestration_mode=mode,
    )


def test_resolve_mode_default_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "orch_plan_execute_tenants", [])
    monkeypatch.setattr(settings, "orch_plan_execute_agents", [])
    assert mode_selector.resolve_mode(_meta("command"), "t1") == "command"


def test_resolve_mode_allowlist_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "orch_plan_execute_tenants", ["t1"])
    monkeypatch.setattr(settings, "orch_plan_execute_agents", [])
    assert mode_selector.resolve_mode(_meta("command"), "t1") == "plan_execute"


def test_should_upgrade_to_plan_execute() -> None:
    assert mode_selector.should_upgrade_to_plan_execute("请分步骤处理这个任务")
    assert not mode_selector.should_upgrade_to_plan_execute("查询保单状态")


def test_should_force_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "orch_max_replans", 2)
    assert mode_selector.should_force_downgrade(replan_count=2, error_count=0)
    assert mode_selector.should_force_downgrade(replan_count=0, error_count=1)
