"""LangGraph Redis Checkpoint，支持中断恢复和 Human-in-the-loop。"""
from langgraph.checkpoint.redis import AsyncRedisSaver
from config.settings import settings


async def get_checkpointer() -> AsyncRedisSaver:
    checkpointer = AsyncRedisSaver.from_conn_string(settings.redis_url)
    await checkpointer.asetup()
    return checkpointer
