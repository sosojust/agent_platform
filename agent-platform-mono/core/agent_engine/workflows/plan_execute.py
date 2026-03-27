from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from core.agent_engine.agents.registry import AgentMeta
from core.agent_engine.workflows.base_agent import (
    make_retrieve_memory_node,
    make_retrieve_rag_node,
    make_update_memory_node,
)
from core.agent_engine.workflows.state import OrchestratorState
from core.ai_core.llm.client import llm_client
from core.memory_rag.memory.config import DEFAULT_MEMORY_CONFIG
from shared.config.settings import settings


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


def build_plan_execute_graph(meta: AgentMeta) -> Any:
    cfg = meta.memory_config or DEFAULT_MEMORY_CONFIG
    max_replans = max(int(meta.max_replans), int(settings.orch_max_replans))

    async def planner(state: OrchestratorState) -> dict[str, Any]:
        if state.get("plan"):
            return {}
        user_input = _last_human_input(state["messages"])
        return {"plan": _build_plan_from_text(user_input)}

    async def executor(state: OrchestratorState) -> dict[str, Any]:
        plan = list(state.get("plan", []))
        if not plan:
            return {}
        step = plan.pop(0)
        goal = str(step.get("goal", ""))
        llm = llm_client.get_chat([], task_type="complex")
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
        llm = llm_client.get_chat([], task_type="simple")
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
