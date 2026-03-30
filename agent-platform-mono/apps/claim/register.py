"""理赔域注册入口。"""
from core.agent_engine.agents.registry import agent_gateway, AgentMeta
from apps.claim.claim_agent import build_claim_agent
from apps.claim.memory_config import CLAIM_MEMORY_CONFIG
from apps.claim.tools.claim_tools import claim_tools


def register() -> None:
    agent_gateway.register(AgentMeta(
        agent_id="claim-assistant",
        name="理赔助手",
        description="处理理赔申请查询、材料核验、进度追踪、理赔历史",
        tags=["claim", "insurance"],
        version="1.0.0",
        memory_config=CLAIM_MEMORY_CONFIG,
        tools=[t.name for t in claim_tools],
        # 理赔域有自定义节点，使用自己的 build_claim_agent
        factory=build_claim_agent,
    ))
