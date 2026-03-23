from pydantic import Field
from pydantic_settings import SettingsConfigDict
from agent_platform_shared.config.settings_base import BaseAppSettings


class Settings(BaseAppSettings):
    port: int = Field(default=8001, alias="PORT")

    # 下游服务地址
    ai_core_url: str = Field(default="http://ai-core-service:8002", alias="AI_CORE_URL")
    memory_rag_url: str = Field(default="http://memory-rag-service:8003", alias="MEMORY_RAG_URL")
    mcp_url: str = Field(default="http://mcp-service:8004", alias="MCP_URL")

    # LangGraph Checkpoint
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    checkpoint_ttl: int = Field(default=86400, alias="CHECKPOINT_TTL")

    # LLM（agent-service 直接持有 key，用于 LangGraph tool_calls 解析）
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    strong_model: str = Field(default="gpt-4o", alias="LLM_STRONG_MODEL")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", populate_by_name=True
    )


settings = Settings()
