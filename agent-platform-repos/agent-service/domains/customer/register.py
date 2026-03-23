"""客服域注册。"""
from agents.registry import registry, AgentMeta
from workflows.base_agent import build_agent


def register(tool_schemas: list[dict]) -> None:
    registry.register(AgentMeta(
        agent_id="customer-assistant",
        name="客服助手",
        description="处理客户咨询、FAQ 查询、客户信息查询，必要时转接人工",
        tags=["customer", "faq", "service"],
        tool_names=["query_customer_info", "search_faq", "transfer_to_human"],
        rag_top_k_recall=15,
        rag_top_k_rerank=5,
        rag_rerank_threshold=0.35,
        long_term_memory=True,
        factory=lambda: build_agent(
            tool_schemas=tool_schemas,
            tool_names=["query_customer_info", "search_faq", "transfer_to_human"],
            system_prompt_key="customer_agent_system",
            max_steps=10,
        ),
    ))
