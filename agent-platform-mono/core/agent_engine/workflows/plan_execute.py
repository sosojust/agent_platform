from __future__ import annotations

from time import perf_counter
from typing import Any, Literal

from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables.config import RunnableConfig
from langgraph.graph import END, START, StateGraph

from core.agent_engine.agents.registry import AgentMeta, agent_gateway
from core.agent_engine.subagent_aggregator import aggregate_subagent_results
from core.agent_engine.subagent_gateway import SubagentTask, subagent_gateway
from core.agent_engine.subagent_planner_gateway import subagent_planner_gateway
from core.agent_engine.subagent_planner_provider_protocols import SubagentPlannerDecision
from core.agent_engine.workflows.base_agent import (
    make_retrieve_memory_node,
    make_retrieve_rag_node,
    make_update_memory_node,
)
from core.agent_engine.workflows.state import OrchestratorState
from core.ai_core.llm.client import llm_gateway
from core.memory_rag.memory.config import DEFAULT_MEMORY_CONFIG
from shared.config.settings import settings
from shared.logging.logger import get_logger
from shared.observability.metrics_gateway import metrics_gateway

ResolvedAggregationStrategy = Literal[
    "summary",
    "priority",
    "vote",
    "confidence_rank",
    "conflict_resolution",
]

logger = get_logger(__name__)


def _last_human_input(messages: list[Any]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return str(msg.content)
    return ""


def _build_plan_from_text(text: str) -> list[dict[str, Any]]:
    parts = [x.strip() for x in str(text).replace("。", "，").split("，") if x.strip()]
    if not parts:
        return [{"step_id": "step_1", "goal": str(text), "status": "pending"}]
    if len(parts) == 1:
        return [{"step_id": "step_1", "goal": parts[0], "status": "pending"}]
    return [
        {"step_id": f"step_{idx + 1}", "goal": part, "status": "pending"}
        for idx, part in enumerate(parts[:5])
    ]


def _build_parallel_subagent_step(text: str, decision: SubagentPlannerDecision) -> list[dict[str, Any]]:
    return [
        {
            "step_id": "subagents_parallel_1",
            "goal": str(text),
            "status": "pending",
            "executor": "subagents",
            "sub_agents": list(decision.get("sub_agents", [])),
            "aggregation_strategy": str(decision.get("aggregation_strategy", "summary")),
            "preferred_agent_ids": list(decision.get("preferred_agent_ids", [])),
            "aggregation_params": dict(decision.get("aggregation_params", {})),
            "decision_source": str(decision.get("decision_source", "planner_rule_router")),
        }
    ]


def _build_shared_context(state: OrchestratorState) -> str:
    parts = [str(state.get("memory_context", "")).strip(), str(state.get("rag_context", "")).strip()]
    return "\n\n".join(part for part in parts if part)


def _build_subagent_tasks(step: dict[str, Any], goal: str) -> list[SubagentTask]:
    tasks: list[SubagentTask] = []
    for agent_id in step.get("sub_agents", []):
        child_meta = agent_gateway.get(str(agent_id))
        child_name = child_meta.name if child_meta is not None else str(agent_id)
        tasks.append(
            SubagentTask(
                agent_id=str(agent_id),
                task_id=str(agent_id),
                user_input=f"请从{child_name}视角处理以下任务，并输出可汇总的关键结论：{goal}",
                metadata={"delegated_agent_name": child_name},
            )
        )
    return tasks


def _resolve_aggregation_strategy(value: Any) -> ResolvedAggregationStrategy:
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


async def _emit_custom_event(
    name: str,
    data: dict[str, Any],
    config: RunnableConfig | None,
) -> None:
    try:
        await adispatch_custom_event(name, data, config=config)
    except RuntimeError:
        return


def build_plan_execute_graph(meta: AgentMeta) -> Any:
    cfg = meta.memory_config or DEFAULT_MEMORY_CONFIG
    max_replans = max(int(meta.max_replans), int(settings.orch_max_replans))

    async def planner(state: OrchestratorState, config: RunnableConfig | None = None) -> dict[str, Any]:
        if state.get("plan"):
            return {}
        user_input = _last_human_input(state["messages"])
        decision = await subagent_planner_gateway.resolve(
            meta=meta,
            user_input=user_input,
            state=state,
            available_sub_agents=meta.sub_agents,
        )
        route_decision = {
            "executor": decision["executor"],
            "reason": decision["reason"],
            "decision_source": decision["decision_source"],
            "aggregation_strategy": decision["aggregation_strategy"],
            "sub_agents": list(decision.get("sub_agents", [])),
            "aggregation_params": dict(decision.get("aggregation_params", {})),
            "confidence_score": float(decision.get("confidence_score", 0.0)),
            "merge_debug": dict(decision.get("merge_debug", {})),
        }
        await _emit_custom_event(
            "subagent.planner.decision",
            {
                "conversation_id": state["conversation_id"],
                "tenant_id": state["tenant_id"],
                **route_decision,
            },
            config,
        )
        if decision["executor"] == "subagents":
            return {
                "plan": _build_parallel_subagent_step(user_input, decision),
                "route_decision": route_decision,
            }
        return {"plan": _build_plan_from_text(user_input), "route_decision": route_decision}

    async def executor(state: OrchestratorState, config: RunnableConfig | None = None) -> dict[str, Any]:
        plan = list(state.get("plan", []))
        if not plan:
            return {}
        step = plan.pop(0)
        goal = str(step.get("goal", ""))
        if step.get("executor") == "subagents":
            batch_started_at = perf_counter()
            aggregation_strategy = _resolve_aggregation_strategy(step.get("aggregation_strategy", "summary"))
            await _emit_custom_event(
                "subagent.execution.started",
                {
                    "conversation_id": state["conversation_id"],
                    "tenant_id": state["tenant_id"],
                    "parent_agent_id": meta.agent_id,
                    "aggregation_strategy": aggregation_strategy,
                    "task_count": len(step.get("sub_agents", [])),
                },
                config,
            )
            results = await subagent_gateway.run_batch(
                _build_subagent_tasks(step, goal),
                tenant_id=state["tenant_id"],
                parent_conversation_id=state["conversation_id"],
                parent_agent_id=meta.agent_id,
                shared_context=_build_shared_context(state),
                event_config=config,
            )
            batch_duration_ms = int((perf_counter() - batch_started_at) * 1000)
            serialized_results = [result.as_dict() for result in results]
            aggregation_started_at = perf_counter()
            aggregated = aggregate_subagent_results(
                serialized_results,
                strategy=aggregation_strategy,
                preferred_agent_ids=step.get("preferred_agent_ids", []),
                min_confidence=float((step.get("aggregation_params") or {}).get("min_confidence", 0.0)),
                conflict_resolution_template=str(
                    (step.get("aggregation_params") or {}).get("conflict_resolution_template", "")
                ),
            )
            aggregation_duration_ms = int((perf_counter() - aggregation_started_at) * 1000)
            aggregation_payload = aggregated.as_dict()
            metrics_payload = {
                "task_count": len(serialized_results),
                "success_count": aggregated.success_count,
                "error_count": aggregated.error_count,
                "batch_duration_ms": batch_duration_ms,
                "aggregation_duration_ms": aggregation_duration_ms,
                "strategy": aggregation_strategy,
            }
            logger_payload = {
                "conversation_id": state["conversation_id"],
                "tenant_id": state["tenant_id"],
                "parent_agent_id": meta.agent_id,
                **metrics_payload,
            }
            metrics_gateway.record_aggregation(logger_payload)
            await _emit_custom_event(
                "subagent.aggregation.completed",
                {
                    **logger_payload,
                    "selected_agent_ids": aggregation_payload.get("selected_agent_ids", []),
                    "conflict_detected": aggregation_payload.get("conflict_detected", False),
                },
                config,
            )
            await _emit_custom_event("subagent.metrics", logger_payload, config)
            response = AIMessage(content=aggregated.final_output)
            logger.info("subagent_aggregation_completed", **logger_payload)
            executed = {
                "step_id": step.get("step_id", ""),
                "goal": goal,
                "result": aggregated.final_output,
                "subagent_results": serialized_results,
                "subagent_aggregation": aggregation_payload,
                "subagent_metrics": metrics_payload,
            }
            return {
                "messages": [response],
                "plan": plan,
                "past_steps": [executed],
                "subagent_results": serialized_results,
                "subagent_aggregation": aggregation_payload,
                "subagent_metrics": metrics_payload,
                "step_count": state.get("step_count", 0) + 1,
            }
        llm = llm_gateway.get_chat([], scene="plan_execute_step")
        messages = [
            SystemMessage(content="你是任务执行器。请执行当前步骤并给出结果，简洁准确。"),
            HumanMessage(content=goal),
        ]
        response = await llm.ainvoke(messages)
        executed = {"step_id": step.get("step_id", ""), "goal": goal, "result": str(response.content)}
        return {
            "messages": [response],
            "plan": plan,
            "past_steps": [executed],
            "step_count": state.get("step_count", 0) + 1,
        }

    def after_executor(state: OrchestratorState) -> str:
        if state.get("step_count", 0) >= settings.orch_max_steps:
            return "finalize"
        if not state.get("plan"):
            return "finalize"
        return "replanner"

    async def replanner(state: OrchestratorState) -> dict[str, Any]:
        replan_count = int(state.get("replan_count", 0)) + 1
        if replan_count >= max_replans:
            return {"replan_count": replan_count, "plan": []}
        return {"replan_count": replan_count}

    def after_replanner(state: OrchestratorState) -> str:
        if not state.get("plan"):
            return "finalize"
        return "executor"

    async def finalize(state: OrchestratorState) -> dict[str, Any]:
        if not state.get("past_steps"):
            return {}
        summary = "\n".join(
            f"{item.get('step_id')}: {item.get('result', '')}"
            for item in state.get("past_steps", [])
        )
        llm = llm_gateway.get_chat([], scene="plan_execute_summary")
        messages = [
            SystemMessage(content="你是总结助手。请基于步骤执行结果给出最终答复。"),
            HumanMessage(content=summary),
        ]
        response = await llm.ainvoke(messages)
        return {"messages": [response]}

    graph = StateGraph(OrchestratorState)
    graph.add_node("retrieve_memory", make_retrieve_memory_node(cfg))
    graph.add_node("retrieve_rag", make_retrieve_rag_node(cfg))
    graph.add_node("planner", planner)
    graph.add_node("executor", executor)
    graph.add_node("replanner", replanner)
    graph.add_node("finalize", finalize)
    graph.add_node("update_memory", make_update_memory_node(cfg))
    graph.add_edge(START, "retrieve_memory")
    graph.add_edge("retrieve_memory", "retrieve_rag")
    graph.add_edge("retrieve_rag", "planner")
    graph.add_edge("planner", "executor")
    graph.add_conditional_edges("executor", after_executor, {"replanner": "replanner", "finalize": "finalize"})
    graph.add_conditional_edges("replanner", after_replanner, {"executor": "executor", "finalize": "finalize"})
    graph.add_edge("finalize", "update_memory")
    graph.add_edge("update_memory", END)
    return graph.compile()
