"""
基础 LangGraph Agent Graph。

与单体版本的核心区别：
  - 不再直接 import ai_core / memory_rag 模块
  - 所有跨服务调用通过 clients/ 下的 HTTP 客户端完成
  - LLM 推理走 ai_core_client.stream()，全链路流式不断流

Graph 结构：
  START → retrieve_memory → retrieve_rag → llm_reason ⇄ tools → update_memory → END
"""
from typing import Annotated, TypedDict, Any
import operator

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool as lc_tool

from config.settings import settings
from clients.ai_core_client import ai_core_client
from clients.memory_rag_client import memory_rag_client
from clients.mcp_client import mcp_client
from agent_platform_shared.logging.logger import get_logger
from agent_platform_shared.middleware.tenant import get_current_tenant_id

logger = get_logger(__name__)


class BaseAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    conversation_id: str
    tenant_id: str
    memory_context: str
    rag_context: str
    step_count: int
    system_prompt_key: str
    # RAG 参数（由各域 register.py 的 AgentMeta 传入）
    rag_top_k_recall: int
    rag_top_k_rerank: int


def _build_remote_tools(tool_schemas: list[dict], tool_names: list[str]) -> list:
    """
    将 mcp-service 返回的 tool schema 转换为 LangChain tool 对象。
    实际执行时通过 mcp_client.call_tool() 转发给 mcp-service。
    """
    remote_tools = []
    filtered = [s for s in tool_schemas if s["name"] in tool_names] if tool_names else tool_schemas

    for schema in filtered:
        tool_name = schema["name"]
        tool_desc = schema["description"]

        # 动态创建 LangChain tool，执行时转发到 mcp-service
        async def _fn(_tool_name=tool_name, **kwargs) -> Any:
            return await mcp_client.call_tool(_tool_name, kwargs)

        _fn.__name__ = tool_name
        _fn.__doc__ = tool_desc
        remote_tools.append(lc_tool(_fn))

    return remote_tools


def build_agent(
    tool_schemas: list[dict],
    tool_names: list[str],
    system_prompt_key: str = "agent_system",
    max_steps: int = 10,
    state_schema: type = BaseAgentState,
):
    """
    构建并编译 LangGraph Agent。

    tool_schemas: 从 mcp-service /tools/list 拉取的 schema 列表
    tool_names:   该 agent 允许使用的 tool 名称子集（空列表 = 全部）
    system_prompt_key: ai-core-service 中的 prompt 名称
    max_steps:    防止无限循环的最大步骤数
    state_schema: 域可扩展的 State TypedDict
    """
    tools = _build_remote_tools(tool_schemas, tool_names)
    llm = ChatOpenAI(
        model=settings.strong_model,
        api_key=settings.openai_api_key,
        streaming=True,
    ).bind_tools(tools)

    # ── 节点定义 ────────────────────────────────────────────

    async def retrieve_memory(state: BaseAgentState) -> dict:
        last_input = next(
            (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
        )
        context = await memory_rag_client.get_memory_context(
            conversation_id=state["conversation_id"],
            query=str(last_input),
            tenant_id=state["tenant_id"],
        )
        return {"memory_context": context}

    async def retrieve_rag(state: BaseAgentState) -> dict:
        last_input = next(
            (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
        )
        docs = await memory_rag_client.retrieve(
            query=str(last_input),
            tenant_id=state["tenant_id"],
            top_k_recall=state.get("rag_top_k_recall", 20),
            top_k_rerank=state.get("rag_top_k_rerank", 5),
        )
        return {"rag_context": "\n\n".join(docs)}

    async def llm_reason(state: BaseAgentState) -> dict:
        if state["step_count"] >= max_steps:
            logger.warning("max_steps_reached", conversation_id=state["conversation_id"])
            return {"messages": [], "step_count": state["step_count"]}

        # 拉取 system prompt（从 ai-core-service）
        system_text = await ai_core_client.get_prompt(
            state.get("system_prompt_key", system_prompt_key),
            tenant_id=state["tenant_id"],
        )
        parts = [system_text]
        if state.get("memory_context"):
            parts.append(f"\n{state['memory_context']}")
        if state.get("rag_context"):
            parts.append(f"\n【参考资料】\n{state['rag_context']}")

        msgs = [SystemMessage(content="\n".join(parts))] + state["messages"]
        response = await llm.ainvoke(msgs)
        return {"messages": [response], "step_count": state["step_count"] + 1}

    async def update_memory(state: BaseAgentState) -> dict:
        """写回本轮对话到 memory-rag-service（fire-and-forget）。"""
        for msg in state["messages"][-2:]:
            role = "user" if isinstance(msg, HumanMessage) else "assistant"
            await memory_rag_client.append_memory(
                conversation_id=state["conversation_id"],
                role=role,
                content=str(msg.content),
                tenant_id=state["tenant_id"],
            )
        return {}

    def should_continue(state: BaseAgentState) -> str:
        if state["step_count"] >= max_steps:
            return "update_memory"
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return "update_memory"

    # ── Graph 构建 ──────────────────────────────────────────
    graph = StateGraph(state_schema)
    graph.add_node("retrieve_memory", retrieve_memory)
    graph.add_node("retrieve_rag", retrieve_rag)
    graph.add_node("llm_reason", llm_reason)
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("update_memory", update_memory)

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
