"""
理赔域自定义 Agent Workflow。
理赔场景比保单复杂，需要额外的材料核验节点，因此不直接使用 base_agent，
而是在 base_agent 基础上扩展一个 doc_verify 节点。

扩展的 Graph 结构：
  START
    → retrieve_memory
    → retrieve_rag
    → llm_reason         （决策：是否需要材料核验）
    → doc_verify         （条件节点：理赔材料完整性检查）
    → tools              （调用 MCP tools）
    → llm_reason         （循环）
    → update_memory
  END
"""
from typing import Annotated, TypedDict
import operator

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.agent_engine.workflows.base_agent import (
    make_retrieve_memory_node,
    make_retrieve_rag_node,
    make_llm_reason_node,
    make_update_memory_node,
)
from domain_agents.claim.memory_config import CLAIM_MEMORY_CONFIG
from domain_agents.claim.tools.claim_tools import claim_tools
from shared.config.settings import settings
from shared.logging.logger import get_logger

logger = get_logger(__name__)


class ClaimAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    conversation_id: str
    tenant_id: str
    memory_context: str
    rag_context: str
    step_count: int
    # 理赔域扩展字段
    doc_verified: bool          # 材料是否已核验通过
    missing_docs: list[str]     # 缺失的材料列表


async def doc_verify(state: ClaimAgentState) -> dict:
    """
    理赔材料核验节点。
    检查用户提供的材料是否完整，缺失则引导补充。
    """
    last_msg = state["messages"][-1]
    content = str(last_msg.content) if hasattr(last_msg, "content") else ""

    required_docs = ["病历", "发票", "诊断证明"]
    missing = [doc for doc in required_docs if doc not in content]

    if missing:
        logger.info("doc_verify_missing", missing=missing, conversation_id=state["conversation_id"])
        return {"doc_verified": False, "missing_docs": missing}

    return {"doc_verified": True, "missing_docs": []}


def build_claim_agent():
    cfg = CLAIM_MEMORY_CONFIG
    tool_node = ToolNode(claim_tools)

    def should_continue(state: ClaimAgentState) -> str:
        if state["step_count"] >= cfg.max_steps:
            return "update_memory"
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return "update_memory"

    graph = StateGraph(ClaimAgentState)
    graph.add_node("retrieve_memory", make_retrieve_memory_node(cfg))
    graph.add_node("retrieve_rag", make_retrieve_rag_node(cfg))
    graph.add_node("llm_reason", make_llm_reason_node(claim_tools, "claim_agent_system", cfg))
    graph.add_node("doc_verify", doc_verify)   # 理赔专属节点
    graph.add_node("tools", tool_node)
    graph.add_node("update_memory", make_update_memory_node(cfg))

    graph.add_edge(START, "retrieve_memory")
    graph.add_edge("retrieve_memory", "retrieve_rag")
    graph.add_edge("retrieve_rag", "doc_verify")   # 先做材料核验
    graph.add_edge("doc_verify", "llm_reason")
    graph.add_conditional_edges(
        "llm_reason", should_continue,
        {"tools": "tools", "update_memory": "update_memory"},
    )
    graph.add_edge("tools", "llm_reason")
    graph.add_edge("update_memory", END)

    return graph.compile()
