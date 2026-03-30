"""
保单域注册入口。
main.py lifespan 自动调用此文件的 register() 函数。
"""
from core.agent_engine.agents.registry import agent_gateway, AgentMeta
from core.agent_engine.workflows.base_agent import build_base_agent
from domain_agents.policy.memory_config import POLICY_MEMORY_CONFIG
from domain_agents.policy.tools.policy_tools import policy_tools


def register() -> None:
    agent_gateway.register(AgentMeta(
        agent_id="policy-assistant",
        name="保单助手",
        description="处理保单查询、保单状态、承保信息、保单列表等业务",
        tags=["policy", "insurance"],
        version="1.0.0",
        memory_config=POLICY_MEMORY_CONFIG,
        tools=[t.name for t in policy_tools],
        # 工厂函数：build_base_agent 接收域专属 tools 和 memory_config
        # 保单域不需要自定义节点，直接复用 base_agent
        factory=lambda: build_base_agent(
            tools=policy_tools,
            system_prompt_key="policy_agent_system",
            memory_config=POLICY_MEMORY_CONFIG,
        ),
    ))
