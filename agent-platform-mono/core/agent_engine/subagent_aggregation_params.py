"""
Aggregation parameter resolution for subagent planner.

Extracted from subagent_planner_provider to allow independent unit testing of the
four-layer override merge logic (default → tenant → agent → tenant_agent).
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from core.agent_engine.agents.registry import AgentMeta
from core.agent_engine.subagent_planner_provider_protocols import SubagentAggregationStrategy
from shared.config.settings import settings


def _to_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_str_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return list(fallback)


def load_aggregation_overrides() -> dict[str, Any]:
    """Load the raw aggregation override config from settings."""
    raw = settings.get(
        "orch_subagent_aggregation_overrides",
        getattr(settings, "orch_subagent_aggregation_overrides", {}),
    )
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        except Exception:
            return {}
    return {}


def resolve_scope_override(
    *,
    strategy: SubagentAggregationStrategy,
    scope_value: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Merge strategy-specific overrides from a single scope block."""
    if not scope_value:
        return {}
    merged: dict[str, Any] = {}
    merged.update(_to_dict(scope_value.get("all")))
    strategies = _to_mapping(scope_value.get("strategies"))
    merged.update(_to_dict(strategies.get(strategy)))
    merged.update(_to_dict(scope_value.get(strategy)))
    return merged


def scoped_aggregation_params(
    *,
    meta: AgentMeta,
    state: Mapping[str, Any],
    available_sub_agents: list[str],
    strategy: SubagentAggregationStrategy,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve aggregation params by merging four override layers:
    default → tenant → agent → tenant_agent (later layers win).

    Priority order (highest wins):
      tenant_agents[{tenant_id}:{agent_id}] > agents[agent_id] > tenants[tenant_id] > default

    Args:
        meta: The parent AgentMeta whose agent_id is used for agent-scoped overrides.
        state: Current orchestrator state; must contain ``tenant_id``.
        available_sub_agents: Fallback list when preferred_agent_ids is not configured.
        strategy: The aggregation strategy being resolved.
        overrides: Optional pre-loaded override dict (useful in tests to avoid settings I/O).
    """
    tenant_id = str(state.get("tenant_id", ""))
    defaults: dict[str, Any] = {
        "preferred_agent_ids": list(
            settings.get("orch_subagent_priority_order", getattr(settings, "orch_subagent_priority_order", []))
            or available_sub_agents
        ),
        "min_confidence": float(
            settings.get("orch_subagent_min_confidence", getattr(settings, "orch_subagent_min_confidence", 0.0))
        ),
        "conflict_resolution_template": str(
            settings.get(
                "orch_subagent_conflict_resolution_template",
                getattr(
                    settings,
                    "orch_subagent_conflict_resolution_template",
                    (
                        "检测到子 Agent 结论存在冲突，已按置信度排序给出建议：\n"
                        "{ranked_candidates}\n"
                        "建议采用 {selected_agent_id} 的结果（confidence={selected_confidence:.2f}）"
                    ),
                ),
            )
        ),
    }
    raw_overrides = overrides if overrides is not None else load_aggregation_overrides()
    merged = dict(defaults)
    # Layer 1: default scope
    merged.update(resolve_scope_override(strategy=strategy, scope_value=_to_mapping(raw_overrides.get("default"))))
    # Layer 2: tenant scope
    merged.update(
        resolve_scope_override(
            strategy=strategy,
            scope_value=_to_mapping(_to_mapping(raw_overrides.get("tenants")).get(tenant_id)),
        )
    )
    # Layer 3: agent scope
    merged.update(
        resolve_scope_override(
            strategy=strategy,
            scope_value=_to_mapping(_to_mapping(raw_overrides.get("agents")).get(meta.agent_id)),
        )
    )
    # Layer 4: tenant+agent scope (highest priority)
    tenant_agent_key = f"{tenant_id}:{meta.agent_id}" if tenant_id else meta.agent_id
    merged.update(
        resolve_scope_override(
            strategy=strategy,
            scope_value=_to_mapping(_to_mapping(raw_overrides.get("tenant_agents")).get(tenant_agent_key)),
        )
    )
    preferred = _as_str_list(merged.get("preferred_agent_ids"), available_sub_agents)
    merged["preferred_agent_ids"] = [a for a in preferred if a in available_sub_agents]
    if not merged["preferred_agent_ids"]:
        merged["preferred_agent_ids"] = list(available_sub_agents)
    merged["min_confidence"] = _to_float(merged.get("min_confidence"), 0.0)
    merged["conflict_resolution_template"] = str(merged.get("conflict_resolution_template", ""))
    return merged
