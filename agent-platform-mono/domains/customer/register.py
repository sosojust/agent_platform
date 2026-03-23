"""客服域注册入口。"""
from agent_service.agents.registry import registry, AgentMeta
from agent_service.workflows.base_agent import build_base_agent
from domains.customer.memory_config import CUSTOMER_MEMORY_CONFIG
from domains.customer.tools.customer_tools import customer_tools


def register() -> None:
    registry.register(AgentMeta(
        agent_id="customer-assistant",
        name="客服助手",
        description="处理客户咨询、FAQ 查询、客户信息查询，必要时转接人工",
        tags=["customer", "faq", "service"],
        version="1.0.0",
        memory_config=CUSTOMER_MEMORY_CONFIG,
        tools=[t.name for t in customer_tools],
        # 客服域不需要自定义节点，直接复用 base_agent
        factory=lambda: build_base_agent(
            tools=customer_tools,
            system_prompt_key="customer_agent_system",
            memory_config=CUSTOMER_MEMORY_CONFIG,
        ),
    ))
