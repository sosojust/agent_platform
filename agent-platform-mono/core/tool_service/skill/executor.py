# core/tool_service/skill/executor.py
"""
Skill 执行器（LLM Agent）

负责执行 Skill 的核心逻辑：
1. 渲染 prompt 模板
2. 获取可用工具
3. 创建 LLM Agent
4. 执行 Agent
5. 返回结果
"""
from langgraph.prebuilt import create_react_agent
from core.ai_core.llm.client import llm_gateway
from shared.logging.logger import get_logger

logger = get_logger(__name__)


class SkillExecutor:
    """
    Skill 执行器（LLM Agent）。
    
    负责执行 Skill 的核心逻辑：
    1. 渲染 prompt 模板
    2. 获取可用工具
    3. 创建 LLM Agent
    4. 执行 Agent
    5. 返回结果
    """
    
    def __init__(self, tool_gateway):
        self.tool_gateway = tool_gateway
    
    async def execute(self, skill_def, arguments, context):
        """执行 Skill"""
        # 1. 渲染 prompt 模板
        prompt = self._render_prompt(skill_def.prompt_template, arguments)
        
        # 2. 获取可用工具（从 tool_gateway）
        tool_functions = []
        for tool_name in skill_def.available_tools:
            tool_entry = self.tool_gateway.get_tool_entry(tool_name)
            if tool_entry:
                tool_functions.append(self._wrap_tool_for_agent(tool_entry, context))
        
        if not tool_functions:
            raise ValueError(f"No available tools for skill: {skill_def.name}")
        
        # 3. 创建 LLM Agent
        # 注意：scene 参数应该是业务语义场景名（如 "skill_execution"），不是模型名
        # llm_config 中的 model 配置应该在 LLM Gateway 的路由层根据 scene 来决定使用哪个模型
        llm = llm_gateway.get_chat([], scene="skill_execution")
        
        agent = create_react_agent(
            model=llm,
            tools=tool_functions,
        )
        
        # 4. 执行 Agent
        logger.info(
            "skill_executing",
            skill_name=skill_def.name,
            tool_count=len(tool_functions),
            tenant_id=context.tenant_id,
        )
        
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": prompt}]
        })
        
        # 5. 提取结果
        final_message = result["messages"][-1]
        
        return {
            "skill": skill_def.name,
            "result": final_message.content,
            "tool_calls": len([m for m in result["messages"] if hasattr(m, "tool_calls")]),
        }
    
    def _render_prompt(self, template: str, arguments: dict) -> str:
        """渲染 prompt 模板"""
        try:
            return template.format(**arguments)
        except KeyError as e:
            raise ValueError(f"Prompt template missing argument: {e}")
    
    def _wrap_tool_for_agent(self, tool_entry, context):
        """将工具包装成 LangGraph Agent 可用的格式"""
        from langchain_core.tools import tool as langchain_tool
        
        async def wrapped_func(**kwargs):
            return await self.tool_gateway.invoke(
                tool_name=tool_entry.metadata.name,
                arguments=kwargs,
                context=context,
            )
        
        wrapped_func.__name__ = tool_entry.metadata.name
        wrapped_func.__doc__ = tool_entry.metadata.description
        
        return langchain_tool(wrapped_func)
