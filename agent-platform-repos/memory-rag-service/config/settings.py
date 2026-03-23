from pydantic import Field
from pydantic_settings import SettingsConfigDict
from agent_platform_shared.config.settings_base import BaseAppSettings


class Settings(BaseAppSettings):
    port: int = Field(default=8003, alias="PORT")

    # 向量库
    milvus_host: str = Field(default="localhost", alias="MILVUS_HOST")
    milvus_port: int = Field(default=19530, alias="MILVUS_PORT")
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")

    # 本地模型
    embedding_model: str = Field(default="BAAI/bge-m3", alias="EMBEDDING_MODEL")
    rerank_model: str = Field(default="BAAI/bge-reranker-v2-m3", alias="RERANK_MODEL")
    embedding_device: str = Field(default="cpu", alias="EMBEDDING_DEVICE")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    checkpoint_ttl: int = Field(default=86400, alias="CHECKPOINT_TTL")

    # 内部调用 ai-core-service（查询改写用）
    ai_core_url: str = Field(default="http://ai-core-service:8002", alias="AI_CORE_URL")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", populate_by_name=True
    )


settings = Settings()
