from typing import Any, Callable, Awaitable
from langchain_core.messages import SystemMessage

from core.ai_core.prompt.manager import prompt_gateway
from shared.logging.logger import get_logger

logger = get_logger(__name__)

NextAction = Callable[[dict], Awaitable[dict]]
Middleware = Callable[[dict, NextAction], Awaitable[dict]]

def build_middleware_pipeline(middlewares: list[Middleware], base_action: Callable[[dict], Awaitable[dict]]) -> Callable[[dict], Awaitable[dict]]:
    """构建洋葱圈模型的中间件流水线"""
    async def pipeline(state: dict) -> dict:
        async def run_middleware(index: int, current_state: dict) -> dict:
            if index < len(middlewares):
                return await middlewares[index](current_state, lambda s: run_middleware(index + 1, s))
            return await base_action(current_state)
        return await run_middleware(0, state)
    return pipeline

class MaxStepsGuard:
    def __init__(self, max_steps: int):
        self.max_steps = max_steps

    async def __call__(self, state: dict, next_action: NextAction) -> dict:
        step_count = state.get("step_count", 0)
        if step_count >= self.max_steps:
            logger.warning("max_steps_reached", conversation_id=state.get("conversation_id"))
            # 阻止向下执行，直接返回空消息以触发结束条件
            return {"messages": [], "step_count": step_count}
        
        # 继续执行并自动递增步数
        result = await next_action(state)
        if "step_count" not in result:
            result["step_count"] = step_count + 1
        return result

class ContextInjector:
    def __init__(self, system_prompt_key: str):
        self.system_prompt_key = system_prompt_key

    async def __call__(self, state: dict, next_action: NextAction) -> dict:
        system_parts = [
            prompt_gateway.get(self.system_prompt_key, variables={"tenant_id": state.get("tenant_id")}),
        ]
        
        if state.get("memory_context"):
            system_parts.append(f"\n{state['memory_context']}")
        if state.get("rag_context"):
            system_parts.append(f"\n【参考资料】\n{state['rag_context']}")

        # 构造带有 SystemMessage 的全新消息列表，传递给下一层
        injected_messages = [SystemMessage(content="\n".join(system_parts))] + state.get("messages", [])
        
        # 将注入后的 messages 临时放入 state 中供底层 LLM 使用
        state_copy = state.copy()
        state_copy["messages"] = injected_messages
        
        return await next_action(state_copy)
