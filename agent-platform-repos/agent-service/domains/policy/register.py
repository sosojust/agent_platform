"""
保单域注册。
tool_schemas 在 main.py lifespan 中从 mcp-service 拉取后传入。
"""
from agents.registry import registry, AgentMeta
from workflows.base_agent import build_agent


def register(tool_schemas: list[dict]) -> None:
    registry.register(AgentMeta(
        agent_id="policy-assistant",
        name="保单助手",
        description="处理保单查询、保单状态、承保信息、保单列表",
        tags=["policy", "insurance"],
        tool_names=["query_policy_basic", "list_policies_by_company"],
        rag_top_k_recall=10,
        rag_top_k_rerank=3,
        rag_rerank_threshold=0.5,
        long_term_memory=False,
        factory=lambda: build_agent(
            tool_schemas=tool_schemas,
            tool_names=["query_policy_basic", "list_policies_by_company"],
            system_prompt_key="policy_agent_system",
            max_steps=8,
        ),
    ))
