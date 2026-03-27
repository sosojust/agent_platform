"""
统一配置入口。
所有环境变量在此定义，通过 .env 文件或环境变量注入。
Nacos 动态参数在 nacos.py 中覆盖。
"""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    default_model: str = Field(default="openai/gpt-4o-mini", alias="LLM_DEFAULT_MODEL")
    strong_model: str = Field(default="openai/gpt-4o", alias="LLM_STRONG_MODEL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    local_model_base_url: str = Field(default="", alias="LOCAL_MODEL_BASE_URL")
    model_config = SettingsConfigDict(populate_by_name=True)


class VectorDBSettings(BaseSettings):
    milvus_host: str = Field(default="localhost", alias="MILVUS_HOST")
    milvus_port: int = Field(default=19530, alias="MILVUS_PORT")
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    backend: str = Field(default="milvus", alias="VECTOR_DB_BACKEND")
    model_config = SettingsConfigDict(populate_by_name=True)


class EmbeddingSettings(BaseSettings):
    embedding_model: str = Field(default="BAAI/bge-m3", alias="EMBEDDING_MODEL")
    rerank_model: str = Field(default="BAAI/bge-reranker-v2-m3", alias="RERANK_MODEL")
    device: str = Field(default="cpu", alias="EMBEDDING_DEVICE")
    model_config = SettingsConfigDict(populate_by_name=True)


class RedisSettings(BaseSettings):
    url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    checkpoint_ttl: int = Field(default=86400, alias="CHECKPOINT_TTL")
    model_config = SettingsConfigDict(populate_by_name=True)


class GatewaySettings(BaseSettings):
    internal_url: str = Field(
        default="http://internal-gateway:8080", alias="INTERNAL_GATEWAY_URL"
    )
    timeout: float = Field(default=30.0, alias="GATEWAY_TIMEOUT")
    model_config = SettingsConfigDict(populate_by_name=True)


class NacosSettings(BaseSettings):
    # 留空则跳过 Nacos，降级为纯 .env
    server_addr: str = Field(default="", alias="NACOS_SERVER_ADDR")
    namespace: str = Field(default="agent-platform", alias="NACOS_NAMESPACE")
    group: str = Field(default="DEFAULT_GROUP", alias="NACOS_GROUP")
    data_id: str = Field(default="agent-platform.json", alias="NACOS_DATA_ID")
    model_config = SettingsConfigDict(populate_by_name=True)


class ObservabilitySettings(BaseSettings):
    langfuse_host: str = Field(default="http://localhost:3000", alias="LANGFUSE_HOST")
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    otel_endpoint: str = Field(
        default="http://localhost:4317", alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    model_config = SettingsConfigDict(populate_by_name=True)


class AppSettings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    checkpoint_backend: str = Field(default="memory", alias="CHECKPOINT_BACKEND")
    orch_default_mode: str = Field(default="command", alias="ORCH_DEFAULT_MODE")
    orch_max_steps: int = Field(default=12, alias="ORCH_MAX_STEPS")
    orch_max_replans: int = Field(default=2, alias="ORCH_MAX_REPLANS")
    orch_plan_execute_agents: list[str] = Field(default_factory=list, alias="ORCH_PLAN_EXECUTE_AGENTS")
    orch_plan_execute_tenants: list[str] = Field(default_factory=list, alias="ORCH_PLAN_EXECUTE_TENANTS")
    mcp_service_url: str = "http://localhost:8004"
    internal_gateway_url: str = "http://localhost:8000"
    gateway_timeout: int = 30
    external_mcp_endpoints: list[str] = Field(default_factory=list, alias="EXTERNAL_MCP_ENDPOINTS")
    external_mcp_token: str = Field(default="", alias="EXTERNAL_MCP_TOKEN")
    tool_auth_map: dict[str, str] = Field(default_factory=dict, alias="TOOL_AUTH_MAP")

    llm: LLMSettings = Field(default_factory=LLMSettings)
    vector_db: VectorDBSettings = Field(default_factory=VectorDBSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    gateway: GatewaySettings = Field(default_factory=GatewaySettings)
    nacos: NacosSettings = Field(default_factory=NacosSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
    )


settings = AppSettings()
