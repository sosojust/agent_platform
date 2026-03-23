"""理赔域注册。"""
from agents.registry import registry, AgentMeta
from workflows.base_agent import build_agent


def register(tool_schemas: list[dict]) -> None:
    registry.register(AgentMeta(
        agent_id="claim-assistant",
        name="理赔助手",
        description="处理理赔申请查询、材料核验、进度追踪、理赔历史",
        tags=["claim", "insurance"],
        tool_names=["query_claim_status", "list_claims_by_policy"],
        rag_top_k_recall=30,
        rag_top_k_rerank=8,
        rag_rerank_threshold=0.3,
        long_term_memory=True,
        factory=lambda: build_agent(
            tool_schemas=tool_schemas,
            tool_names=["query_claim_status", "list_claims_by_policy"],
            system_prompt_key="claim_agent_system",
            max_steps=15,
        ),
    ))
