"""
可复用的基础 LangGraph Graph。
各业务域继承此基础 Graph，通过传入域专属的 tools 和 memory_config 来定制行为。
不需要自定义节点的域直接调用 build_base_agent() 即可，无需编写 workflow 代码。
"""
from typing import Annotated, TypedDict, Any
import operator

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.memory_rag.memory.config import MemoryConfig, DEFAULT_MEMORY_CONFIG
# from core.memory_rag.memory.manager import memory_manager
# from core.memory_rag.rag.pipeline import rag_pipeline
# from core.ai_core.llm.client import llm_client
# from core.ai_core.prompt.manager import prompt_manager
from shared.config.settings import settings
from shared.logging.logger import get_logger

logger = get_logger(__name__)


# ── State ──────────────────────────────────────────────────────

class BaseAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    conversation_id: str
    tenant_id: str
    memory_context: str
    rag_context: str
    step_count: int
    # 域专属的扩展字段可在子类 State 中追加


# ── 节点工厂（接收 memory_config 参数）───────────────────────

def make_retrieve_memory_node(cfg: MemoryConfig):
    async def retrieve_memory(state: BaseAgentState) -> dict:
        last_input = next(
            (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
        )
        context = await memory_manager.build_memory_context(
            conversation_id=state["conversation_id"],
            query=str(last_input),
            tenant_id=state["tenant_id"],
            config=cfg,
        )
        return {"memory_context": context}
    return retrieve_memory


def make_retrieve_rag_node(cfg: MemoryConfig):
    async def retrieve_rag(state: BaseAgentState) -> dict:
        last_input = next(
            (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
        )
        docs = await rag_pipeline.retrieve(
            query=str(last_input),
            tenant_id=state["tenant_id"],
            collection_type=cfg.rag_collection_type,
            top_k_recall=cfg.rag_top_k_recall,
            top_k_rerank=cfg.rag_top_k_rerank,
            rewrite=cfg.rag_query_rewrite,
        )
        return {"rag_context": "\n\n".join(docs)}
    return retrieve_rag


def make_llm_reason_node(tools: list, system_prompt_key: str, cfg: MemoryConfig):
    llm = ChatOpenAI(
        model=settings.llm.strong_model.replace("openai/", ""),
        api_key=settings.llm.openai_api_key,
        streaming=True,
    ).bind_tools(tools)

    async def llm_reason(state: BaseAgentState) -> dict:
        if state["step_count"] >= cfg.max_steps:
            logger.warning("max_steps_reached", conversation_id=state["conversation_id"])
            return {"messages": [], "step_count": state["step_count"]}

        system_parts = [
            prompt_manager.get(system_prompt_key,
                               variables={"tenant_id": state["tenant_id"]}),
        ]
        if state.get("memory_context"):
            system_parts.append(f"\n{state['memory_context']}")
        if state.get("rag_context"):
            system_parts.append(f"\n【参考资料】\n{state['rag_context']}")

        messages = [SystemMessage(content="\n".join(system_parts))] + state["messages"]
        response = await llm.ainvoke(messages)
        return {"messages": [response], "step_count": state["step_count"] + 1}

    return llm_reason


def make_update_memory_node(cfg: MemoryConfig):
    async def update_memory(state: BaseAgentState) -> dict:
        for msg in state["messages"][-2:]:
            role = "user" if isinstance(msg, HumanMessage) else "assistant"
            await memory_manager.append_short_term(
                conversation_id=state["conversation_id"],
                role=role,
                content=str(msg.content),
                tenant_id=state["tenant_id"],
                config=cfg,
            )
        return {}
    return update_memory


# ── Graph 构建入口 ─────────────────────────────────────────────

def build_base_agent(
    tools: list,
    system_prompt_key: str = "agent_system",
    memory_config: MemoryConfig = DEFAULT_MEMORY_CONFIG,
    state_schema: type = BaseAgentState,
):
    """
    构建基础 Agent Graph。

    tools: MCP tool 函数列表（来自域的 tools/ 目录）
    system_prompt_key: Langfuse 中的 prompt name，各域使用不同的 system prompt
    memory_config: 域专属的记忆和 RAG 配置
    state_schema: 如果域需要扩展 state 字段，传入自定义 TypedDict

    返回编译后的 LangGraph CompiledGraph，可直接 ainvoke / astream_events。
    """
    cfg = memory_config
    tool_node = ToolNode(tools)

    def should_continue(state) -> str:
        last = state["messages"][-1]
        if state["step_count"] >= cfg.max_steps:
            return "update_memory"
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return "update_memory"

    graph = StateGraph(state_schema)
    graph.add_node("retrieve_memory", make_retrieve_memory_node(cfg))
    graph.add_node("retrieve_rag", make_retrieve_rag_node(cfg))
    graph.add_node("llm_reason", make_llm_reason_node(tools, system_prompt_key, cfg))
    graph.add_node("tools", tool_node)
    graph.add_node("update_memory", make_update_memory_node(cfg))

    graph.add_edge(START, "retrieve_memory")
    graph.add_edge("retrieve_memory", "retrieve_rag")
    graph.add_edge("retrieve_rag", "llm_reason")
    graph.add_conditional_edges(
        "llm_reason", should_continue,
        {"tools": "tools", "update_memory": "update_memory"},
    )
    graph.add_edge("tools", "llm_reason")
    graph.add_edge("update_memory", END)

    return graph.compile()
