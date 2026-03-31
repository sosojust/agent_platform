"""Unit tests for the four-layer aggregation param override merge logic."""
from __future__ import annotations

from typing import Any

import pytest

from core.agent_engine.agents.registry import AgentMeta
from core.agent_engine.subagent_aggregation_params import (
    resolve_scope_override,
    scoped_aggregation_params,
)


def _meta(agent_id: str = "lead-agent") -> AgentMeta:
    return AgentMeta(
        agent_id=agent_id,
        name=agent_id,
        description="test",
        factory=lambda: None,
    )


def _state(tenant_id: str = "tenant-a") -> dict[str, Any]:
    return {"tenant_id": tenant_id}


AGENTS = ["policy-assistant", "claim-assistant"]


# ── resolve_scope_override ────────────────────────────────────────────────────

def test_resolve_scope_override_returns_empty_for_none() -> None:
    assert resolve_scope_override(strategy="summary", scope_value=None) == {}


def test_resolve_scope_override_merges_all_then_strategy() -> None:
    scope = {
        "all": {"min_confidence": 0.3},
        "vote": {"min_confidence": 0.7},
    }
    result = resolve_scope_override(strategy="vote", scope_value=scope)
    # strategy-specific key wins over "all"
    assert result["min_confidence"] == 0.7


def test_resolve_scope_override_strategies_dict_wins_over_all() -> None:
    scope = {
        "all": {"min_confidence": 0.1},
        "strategies": {"confidence_rank": {"min_confidence": 0.9}},
    }
    result = resolve_scope_override(strategy="confidence_rank", scope_value=scope)
    assert result["min_confidence"] == 0.9


# ── scoped_aggregation_params layer priority ──────────────────────────────────

def test_default_layer_applied_when_no_overrides() -> None:
    result = scoped_aggregation_params(
        meta=_meta(),
        state=_state(),
        available_sub_agents=AGENTS,
        strategy="summary",
        overrides={},
    )
    assert result["preferred_agent_ids"] == AGENTS
    assert result["min_confidence"] == 0.0


def test_tenant_layer_overrides_default() -> None:
    overrides = {
        "default": {"all": {"min_confidence": 0.1}},
        "tenants": {"tenant-a": {"all": {"min_confidence": 0.5}}},
    }
    result = scoped_aggregation_params(
        meta=_meta(),
        state=_state("tenant-a"),
        available_sub_agents=AGENTS,
        strategy="summary",
        overrides=overrides,
    )
    assert result["min_confidence"] == 0.5


def test_agent_layer_overrides_tenant() -> None:
    overrides = {
        "tenants": {"tenant-a": {"all": {"min_confidence": 0.5}}},
        "agents": {"lead-agent": {"all": {"min_confidence": 0.8}}},
    }
    result = scoped_aggregation_params(
        meta=_meta("lead-agent"),
        state=_state("tenant-a"),
        available_sub_agents=AGENTS,
        strategy="summary",
        overrides=overrides,
    )
    assert result["min_confidence"] == 0.8


def test_tenant_agent_layer_wins_over_all_others() -> None:
    overrides = {
        "default": {"all": {"min_confidence": 0.1}},
        "tenants": {"tenant-a": {"all": {"min_confidence": 0.5}}},
        "agents": {"lead-agent": {"all": {"min_confidence": 0.8}}},
        "tenant_agents": {"tenant-a:lead-agent": {"all": {"min_confidence": 0.99}}},
    }
    result = scoped_aggregation_params(
        meta=_meta("lead-agent"),
        state=_state("tenant-a"),
        available_sub_agents=AGENTS,
        strategy="summary",
        overrides=overrides,
    )
    assert result["min_confidence"] == 0.99


def test_preferred_agent_ids_filtered_to_available() -> None:
    overrides = {
        "default": {"all": {"preferred_agent_ids": ["policy-assistant", "unknown-agent"]}},
    }
    result = scoped_aggregation_params(
        meta=_meta(),
        state=_state(),
        available_sub_agents=AGENTS,
        strategy="priority",
        overrides=overrides,
    )
    # "unknown-agent" is not in available_sub_agents and must be filtered out
    assert result["preferred_agent_ids"] == ["policy-assistant"]


def test_preferred_agent_ids_falls_back_to_available_when_empty() -> None:
    overrides = {
        "default": {"all": {"preferred_agent_ids": ["unknown-agent"]}},
    }
    result = scoped_aggregation_params(
        meta=_meta(),
        state=_state(),
        available_sub_agents=AGENTS,
        strategy="priority",
        overrides=overrides,
    )
    # All preferred IDs filtered out → fall back to full available list
    assert result["preferred_agent_ids"] == AGENTS


def test_strategy_specific_override_within_tenant_scope() -> None:
    overrides = {
        "tenants": {
            "tenant-a": {
                "all": {"min_confidence": 0.3},
                "vote": {"min_confidence": 0.6},
            }
        }
    }
    result = scoped_aggregation_params(
        meta=_meta(),
        state=_state("tenant-a"),
        available_sub_agents=AGENTS,
        strategy="vote",
        overrides=overrides,
    )
    assert result["min_confidence"] == 0.6


def test_no_tenant_id_uses_agent_id_as_tenant_agent_key() -> None:
    """When tenant_id is empty, tenant_agent key should be just agent_id."""
    overrides = {
        "tenant_agents": {"lead-agent": {"all": {"min_confidence": 0.77}}},
    }
    result = scoped_aggregation_params(
        meta=_meta("lead-agent"),
        state={"tenant_id": ""},
        available_sub_agents=AGENTS,
        strategy="summary",
        overrides=overrides,
    )
    assert result["min_confidence"] == 0.77
