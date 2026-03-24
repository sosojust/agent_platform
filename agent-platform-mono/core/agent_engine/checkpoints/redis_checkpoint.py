"""LangGraph Redis Checkpoint，支持中断恢复和 Human-in-the-loop。"""
from langgraph.checkpoint.memory import MemorySaver

async def get_checkpointer() -> MemorySaver:
    # 临时使用 MemorySaver 替代 RedisSaver
    checkpointer = MemorySaver()
    return checkpointer
