from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from core.agent_engine.agents.registry import AgentMeta
from core.agent_engine.subagent_planner_provider_protocols import (
    SubagentAggregationStrategy,
    SubagentPlannerDecision,
    SubagentPlannerExecutor,
    SubagentPlannerProvider,
)
from core.ai_core.llm.client import llm_gateway
from shared.config.settings import settings

PARALLEL_SUBAGENT_KEYWORDS = (
    "并行",
    "并发",
    "同时",
    "分别",
    "汇总",
    "一起",
)

AGGREGATION_KEYWORDS: dict[SubagentAggregationStrategy, tuple[str, ...]] = {
    "summary": (),
    "vote": ("投票", "多数", "多数决", "一致性投票"),
    "confidence_rank": ("置信度", "可信度", "最可信", "最可靠"),
    "conflict_resolution": ("冲突", "矛盾", "不一致", "裁决"),
    "priority": ("优先", "为准", "主结论"),
}


def _contains_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(keyword in lowered for keyword in keywords)


def _resolve_aggregation_strategy_from_text(text: str) -> SubagentAggregationStrategy:
    if _contains_any_keyword(text, AGGREGATION_KEYWORDS["vote"]):
        return "vote"
    if _contains_any_keyword(text, AGGREGATION_KEYWORDS["confidence_rank"]):
        return "confidence_rank"
    if _contains_any_keyword(text, AGGREGATION_KEYWORDS["conflict_resolution"]):
        return "conflict_resolution"
    if _contains_any_keyword(text, AGGREGATION_KEYWORDS["priority"]):
        return "priority"
    return "summary"


def _normalize_strategy(value: Any) -> SubagentAggregationStrategy:
    raw = str(value)
    if raw == "priority":
        return "priority"
    if raw == "vote":
        return "vote"
    if raw == "confidence_rank":
        return "confidence_rank"
    if raw == "conflict_resolution":
        return "conflict_resolution"
    return "summary"


def _normalize_executor(value: Any) -> SubagentPlannerExecutor:
    return "subagents" if str(value) == "subagents" else "llm"


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
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return list(fallback)


def _load_aggregation_overrides() -> dict[str, Any]:
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


def _resolve_scope_override(
    *,
    strategy: SubagentAggregationStrategy,
    scope_value: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not scope_value:
        return {}
    merged: dict[str, Any] = {}
    merged.update(_to_dict(scope_value.get("all")))
    strategies = _to_mapping(scope_value.get("strategies"))
    merged.update(_to_dict(strategies.get(strategy)))
    merged.update(_to_dict(scope_value.get(strategy)))
    return merged


def _scoped_aggregation_params(
    *,
    meta: AgentMeta,
    state: Mapping[str, Any],
    available_sub_agents: list[str],
    strategy: SubagentAggregationStrategy,
) -> dict[str, Any]:
    tenant_id = str(state.get("tenant_id", ""))
    defaults = {
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
                    "检测到子 Agent 结论存在冲突，已按置信度排序给出建议：\n{ranked_candidates}\n建议采用 {selected_agent_id} 的结果（confidence={selected_confidence:.2f}）",
                ),
            )
        ),
    }
    overrides = _load_aggregation_overrides()
    merged = dict(defaults)
    merged.update(_resolve_scope_override(strategy=strategy, scope_value=_to_mapping(overrides.get("default"))))
    merged.update(
        _resolve_scope_override(
            strategy=strategy,
            scope_value=_to_mapping(_to_mapping(overrides.get("tenants")).get(tenant_id)),
        )
    )
    merged.update(
        _resolve_scope_override(
            strategy=strategy,
            scope_value=_to_mapping(_to_mapping(overrides.get("agents")).get(meta.agent_id)),
        )
    )
    tenant_agent_key = f"{tenant_id}:{meta.agent_id}" if tenant_id else meta.agent_id
    merged.update(
        _resolve_scope_override(
            strategy=strategy,
            scope_value=_to_mapping(_to_mapping(overrides.get("tenant_agents")).get(tenant_agent_key)),
        )
    )
    preferred = _as_str_list(merged.get("preferred_agent_ids"), available_sub_agents)
    merged["preferred_agent_ids"] = [agent_id for agent_id in preferred if agent_id in available_sub_agents]
    if not merged["preferred_agent_ids"]:
        merged["preferred_agent_ids"] = list(available_sub_agents)
    merged["min_confidence"] = _to_float(merged.get("min_confidence"), 0.0)
    merged["conflict_resolution_template"] = str(merged.get("conflict_resolution_template", ""))
    return merged


def _build_decision(
    *,
    executor: str,
    reason: str,
    decision_source: str,
    available_sub_agents: list[str],
    selected_sub_agents: list[str] | None,
    aggregation_strategy: SubagentAggregationStrategy,
    aggregation_params: dict[str, Any] | None = None,
    confidence_score: float = 0.5,
    merge_debug: dict[str, Any] | None = None,
) -> SubagentPlannerDecision:
    sub_agents = list(selected_sub_agents or available_sub_agents)
    final_executor = _normalize_executor(executor)
    params = dict(aggregation_params or {})
    preferred_agent_ids = _as_str_list(params.get("preferred_agent_ids"), sub_agents)
    return {
        "executor": final_executor,
        "reason": reason,
        "decision_source": decision_source,
        "sub_agents": sub_agents if final_executor == "subagents" else [],
        "aggregation_strategy": aggregation_strategy if final_executor == "subagents" else "summary",
        "preferred_agent_ids": preferred_agent_ids,
        "aggregation_params": params,
        "confidence_score": max(0.0, min(1.0, confidence_score)),
        "merge_debug": dict(merge_debug or {}),
    }


def _merge_sub_agents(
    rule_sub_agents: list[str],
    llm_sub_agents: list[str],
    *,
    available_sub_agents: list[str],
    merge_mode: str,
    preferred_agent_ids: list[str],
) -> list[str]:
    if merge_mode == "rule":
        merged = list(rule_sub_agents)
    elif merge_mode == "llm":
        merged = list(llm_sub_agents)
    elif merge_mode == "intersection":
        merged = [agent_id for agent_id in rule_sub_agents if agent_id in set(llm_sub_agents)]
    else:
        merged = list(dict.fromkeys([*rule_sub_agents, *llm_sub_agents]))
    if not merged:
        merged = list(available_sub_agents)
    ordered: list[str] = []
    for agent_id in preferred_agent_ids:
        if agent_id in merged and agent_id not in ordered:
            ordered.append(agent_id)
    for agent_id in merged:
        if agent_id not in ordered:
            ordered.append(agent_id)
    return [agent_id for agent_id in ordered if agent_id in available_sub_agents]


def _choose_executor_by_weight(
    *,
    rule_decision: SubagentPlannerDecision,
    llm_decision: SubagentPlannerDecision,
    tie_breaker: str,
    rule_weight: float,
    llm_weight: float,
) -> tuple[str, dict[str, float]]:
    supports = {"subagents": 0.0, "llm": 0.0}
    supports[rule_decision["executor"]] += max(0.0, rule_weight) * _to_float(
        rule_decision.get("confidence_score"),
        0.5,
    )
    supports[llm_decision["executor"]] += max(0.0, llm_weight) * _to_float(
        llm_decision.get("confidence_score"),
        0.5,
    )
    if abs(supports["subagents"] - supports["llm"]) < 1e-9:
        if tie_breaker in ("subagents", "llm"):
            return tie_breaker, supports
        if tie_breaker == "rule":
            return rule_decision["executor"], supports
        if tie_breaker == "llm_provider":
            return llm_decision["executor"], supports
    return ("subagents" if supports["subagents"] > supports["llm"] else "llm"), supports


def _resolve_hybrid_strategy(
    *,
    rule_decision: SubagentPlannerDecision,
    llm_decision: SubagentPlannerDecision,
    strategy_merge_mode: str,
) -> SubagentAggregationStrategy:
    rule_strategy = _normalize_strategy(rule_decision.get("aggregation_strategy"))
    llm_strategy = _normalize_strategy(llm_decision.get("aggregation_strategy"))
    if rule_strategy == llm_strategy:
        return rule_strategy
    if strategy_merge_mode == "rule":
        return rule_strategy
    if strategy_merge_mode == "llm":
        return llm_strategy
    if _to_float(llm_decision.get("confidence_score"), 0.0) > _to_float(
        rule_decision.get("confidence_score"),
        0.0,
    ):
        return llm_strategy
    return rule_strategy


def _merge_aggregation_params(
    *,
    base_params: dict[str, Any],
    rule_params: Mapping[str, Any],
    llm_params: Mapping[str, Any],
    strategy: SubagentAggregationStrategy,
) -> dict[str, Any]:
    merged = dict(base_params)
    merged.update(_to_dict(rule_params))
    merged.update(_to_dict(llm_params))
    merged.update(
        _resolve_scope_override(
            strategy=strategy,
            scope_value={"all": merged},
        )
    )
    preferred = list(merged.get("preferred_agent_ids", []))
    merged["preferred_agent_ids"] = [str(agent_id) for agent_id in preferred]
    merged["min_confidence"] = _to_float(merged.get("min_confidence"), 0.0)
    merged["conflict_resolution_template"] = str(merged.get("conflict_resolution_template", ""))
    return merged


class RuleSubagentPlannerProvider(SubagentPlannerProvider):
    async def resolve(
        self,
        *,
        meta: AgentMeta,
        user_input: str,
        state: dict[str, Any] | Any,
        available_sub_agents: list[str] | Any,
    ) -> SubagentPlannerDecision:
        available = list(available_sub_agents)
        aggregation_strategy = _resolve_aggregation_strategy_from_text(user_input)
        parallel_requested = _contains_any_keyword(user_input, PARALLEL_SUBAGENT_KEYWORDS)
        aggregation_requested = aggregation_strategy != "summary"
        scoped_params = _scoped_aggregation_params(
            meta=meta,
            state=_to_mapping(state),
            available_sub_agents=available,
            strategy=aggregation_strategy,
        )
        if available and (parallel_requested or aggregation_requested):
            return _build_decision(
                executor="subagents",
                reason="planner_rule_router_matched",
                decision_source="planner_rule_router",
                available_sub_agents=available,
                selected_sub_agents=available,
                aggregation_strategy=aggregation_strategy,
                aggregation_params=scoped_params,
                confidence_score=0.85,
            )
        return _build_decision(
            executor="llm",
            reason="planner_default_llm",
            decision_source="planner_rule_router",
            available_sub_agents=available,
            selected_sub_agents=[],
            aggregation_strategy="summary",
            aggregation_params=_scoped_aggregation_params(
                meta=meta,
                state=_to_mapping(state),
                available_sub_agents=available,
                strategy="summary",
            ),
            confidence_score=0.6,
        )


class LLMSubagentPlannerProvider(SubagentPlannerProvider):
    async def resolve(
        self,
        *,
        meta: AgentMeta,
        user_input: str,
        state: dict[str, Any] | Any,
        available_sub_agents: list[str] | Any,
    ) -> SubagentPlannerDecision:
        available = list(available_sub_agents)
        fallback = await RuleSubagentPlannerProvider().resolve(
            meta=meta,
            user_input=user_input,
            state=state,
            available_sub_agents=available,
        )
        if not available:
            return fallback
        llm = llm_gateway.get_chat([], scene="subagent_planner")
        messages = [
            SystemMessage(
                content=(
                    "你是子 Agent 编排决策器。"
                    "请只输出 JSON，字段包含 executor、aggregation_strategy、reason、confidence、sub_agents、aggregation_params。"
                    "executor 只能是 llm 或 subagents。"
                    "aggregation_strategy 只能是 summary、priority、vote、confidence_rank、conflict_resolution。"
                    "如果需要并发多个子 Agent，则 executor 设为 subagents。"
                )
            ),
            HumanMessage(
                content=json.dumps(
                    {
                        "agent_id": meta.agent_id,
                        "user_input": user_input,
                        "available_sub_agents": available,
                        "memory_context": str((state or {}).get("memory_context", "")),
                        "rag_context": str((state or {}).get("rag_context", "")),
                    },
                    ensure_ascii=False,
                )
            ),
        ]
        try:
            response = await llm.ainvoke(messages)
            payload = json.loads(str(response.content))
        except Exception:
            return fallback
        executor = "subagents" if str(payload.get("executor", "")) == "subagents" and available else "llm"
        aggregation_strategy = _normalize_strategy(payload.get("aggregation_strategy", "summary"))
        if executor != "subagents":
            aggregation_strategy = "summary"
        requested_sub_agents = list(payload.get("sub_agents", available) or available)
        selected_sub_agents = [agent_id for agent_id in requested_sub_agents if agent_id in available] or available
        scoped_params = _scoped_aggregation_params(
            meta=meta,
            state=_to_mapping(state),
            available_sub_agents=selected_sub_agents,
            strategy=aggregation_strategy,
        )
        llm_params = _to_dict(payload.get("aggregation_params"))
        scoped_params.update(llm_params)
        return _build_decision(
            executor=executor,
            reason=str(payload.get("reason", "planner_llm_router")),
            decision_source="planner_llm_router",
            available_sub_agents=available,
            selected_sub_agents=selected_sub_agents,
            aggregation_strategy=aggregation_strategy,
            aggregation_params=scoped_params,
            confidence_score=_to_float(payload.get("confidence"), 0.78 if executor == "subagents" else 0.55),
        )


class HybridSubagentPlannerProvider(SubagentPlannerProvider):
    async def resolve(
        self,
        *,
        meta: AgentMeta,
        user_input: str,
        state: dict[str, Any] | Any,
        available_sub_agents: list[str] | Any,
    ) -> SubagentPlannerDecision:
        available = list(available_sub_agents)
        rule_decision = await RuleSubagentPlannerProvider().resolve(
            meta=meta,
            user_input=user_input,
            state=state,
            available_sub_agents=available,
        )
        llm_decision = await LLMSubagentPlannerProvider().resolve(
            meta=meta,
            user_input=user_input,
            state=state,
            available_sub_agents=available,
        )
        merge_mode = str(
            settings.get(
                "orch_subagent_hybrid_merge_mode",
                getattr(settings, "orch_subagent_hybrid_merge_mode", "consensus_weighted"),
            )
        ).lower()
        if merge_mode == "rule_first":
            return {
                **rule_decision,
                "decision_source": "planner_hybrid_rule_first",
                "merge_debug": {"merge_mode": merge_mode},
            }
        if merge_mode == "llm_first":
            return {
                **llm_decision,
                "decision_source": "planner_hybrid_llm_first",
                "merge_debug": {"merge_mode": merge_mode},
            }

        tie_breaker = str(
            settings.get(
                "orch_subagent_hybrid_tie_breaker",
                getattr(settings, "orch_subagent_hybrid_tie_breaker", "rule"),
            )
        ).lower()
        rule_weight = _to_float(
            settings.get(
                "orch_subagent_hybrid_rule_weight",
                getattr(settings, "orch_subagent_hybrid_rule_weight", 0.6),
            ),
            0.6,
        )
        llm_weight = _to_float(
            settings.get(
                "orch_subagent_hybrid_llm_weight",
                getattr(settings, "orch_subagent_hybrid_llm_weight", 0.4),
            ),
            0.4,
        )
        final_executor, supports = _choose_executor_by_weight(
            rule_decision=rule_decision,
            llm_decision=llm_decision,
            tie_breaker=tie_breaker,
            rule_weight=rule_weight,
            llm_weight=llm_weight,
        )
        if merge_mode == "strict_consensus" and rule_decision["executor"] != llm_decision["executor"]:
            final_executor = "llm"

        strategy_merge_mode = str(
            settings.get(
                "orch_subagent_hybrid_strategy_merge_mode",
                getattr(settings, "orch_subagent_hybrid_strategy_merge_mode", "higher_confidence"),
            )
        ).lower()
        subagent_merge_mode = str(
            settings.get(
                "orch_subagent_hybrid_subagent_merge_mode",
                getattr(settings, "orch_subagent_hybrid_subagent_merge_mode", "union"),
            )
        ).lower()
        merged_strategy = _resolve_hybrid_strategy(
            rule_decision=rule_decision,
            llm_decision=llm_decision,
            strategy_merge_mode=strategy_merge_mode,
        )
        scoped_params = _scoped_aggregation_params(
            meta=meta,
            state=_to_mapping(state),
            available_sub_agents=available,
            strategy=merged_strategy,
        )
        merged_params = _merge_aggregation_params(
            base_params=scoped_params,
            rule_params=rule_decision.get("aggregation_params", {}),
            llm_params=llm_decision.get("aggregation_params", {}),
            strategy=merged_strategy,
        )
        merged_sub_agents = _merge_sub_agents(
            list(rule_decision.get("sub_agents", [])),
            list(llm_decision.get("sub_agents", [])),
            available_sub_agents=available,
            merge_mode=subagent_merge_mode,
            preferred_agent_ids=list(merged_params.get("preferred_agent_ids", [])),
        )
        selected_reason = (
            f"planner_hybrid_merged mode={merge_mode} "
            f"support_subagents={supports['subagents']:.2f} support_llm={supports['llm']:.2f}"
        )
        return _build_decision(
            executor=final_executor,
            reason=selected_reason,
            decision_source="planner_hybrid_merged",
            available_sub_agents=available,
            selected_sub_agents=merged_sub_agents if final_executor == "subagents" else [],
            aggregation_strategy=merged_strategy if final_executor == "subagents" else "summary",
            aggregation_params=merged_params,
            confidence_score=max(supports["subagents"], supports["llm"]),
            merge_debug={
                "merge_mode": merge_mode,
                "supports": supports,
                "rule_executor": rule_decision["executor"],
                "llm_executor": llm_decision["executor"],
                "rule_strategy": rule_decision["aggregation_strategy"],
                "llm_strategy": llm_decision["aggregation_strategy"],
            },
        )
