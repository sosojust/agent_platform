"""
统一配置入口。
所有环境变量在此定义，通过 .env 文件或环境变量注入。
Nacos 动态参数在 nacos.py 中覆盖。
"""
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    default_model: str = Field(default="openai/gpt-4o-mini", alias="LLM_DEFAULT_MODEL")
    strong_model: str = Field(default="openai/gpt-4o", alias="LLM_STRONG_MODEL")
    medium_model: str = Field(default="openai/gpt-4o-mini", alias="LLM_MEDIUM_MODEL")
    nano_model: str = Field(default="openai/gpt-4o-mini", alias="LLM_NANO_MODEL")
    local_model: str = Field(default="ollama/qwen2.5", alias="LLM_LOCAL_MODEL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    local_model_base_url: str = Field(default="", alias="LOCAL_MODEL_BASE_URL")
    request_timeout_seconds: float = Field(default=60.0, alias="LLM_REQUEST_TIMEOUT_SECONDS")
    max_retries: int = Field(default=1, alias="LLM_MAX_RETRIES")
    router_deployments: str = Field(default="", alias="LLM_ROUTER_DEPLOYMENTS")
    router_cooldown_seconds: int = Field(default=30, alias="LLM_ROUTER_COOLDOWN_SECONDS")
    router_max_attempts: int = Field(default=3, alias="LLM_ROUTER_MAX_ATTEMPTS")
    cache_enabled: bool = Field(default=True, alias="LLM_CACHE_ENABLED")
    cache_default_ttl_seconds: int = Field(default=0, alias="LLM_CACHE_DEFAULT_TTL_SECONDS")
    cache_scene_ttl: str = Field(default="", alias="LLM_CACHE_SCENE_TTL")
    cache_task_ttl: str = Field(default="", alias="LLM_CACHE_TASK_TTL")
    cache_max_entries: int = Field(default=512, alias="LLM_CACHE_MAX_ENTRIES")
    tenant_token_budget: int = Field(default=0, alias="LLM_TENANT_TOKEN_BUDGET")
    conversation_token_budget: int = Field(default=0, alias="LLM_CONVERSATION_TOKEN_BUDGET")
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
    orch_subagent_max_concurrency: int = Field(default=3, alias="ORCH_SUBAGENT_MAX_CONCURRENCY")
    orch_subagent_timeout_seconds: float = Field(default=45.0, alias="ORCH_SUBAGENT_TIMEOUT_SECONDS")
    orch_subagent_planner_provider: str = Field(default="rule", alias="ORCH_SUBAGENT_PLANNER_PROVIDER")
    orch_subagent_priority_order: list[str] = Field(default_factory=list, alias="ORCH_SUBAGENT_PRIORITY_ORDER")
    orch_subagent_min_confidence: float = Field(default=0.0, alias="ORCH_SUBAGENT_MIN_CONFIDENCE")
    orch_subagent_conflict_resolution_template: str = Field(
        default="检测到子 Agent 结论存在冲突，已按置信度排序给出建议：\n{ranked_candidates}\n建议采用 {selected_agent_id} 的结果（confidence={selected_confidence:.2f}）",
        alias="ORCH_SUBAGENT_CONFLICT_RESOLUTION_TEMPLATE",
    )
    orch_subagent_hybrid_merge_mode: str = Field(
        default="consensus_weighted",
        alias="ORCH_SUBAGENT_HYBRID_MERGE_MODE",
    )
    orch_subagent_hybrid_rule_weight: float = Field(
        default=0.6,
        alias="ORCH_SUBAGENT_HYBRID_RULE_WEIGHT",
    )
    orch_subagent_hybrid_llm_weight: float = Field(
        default=0.4,
        alias="ORCH_SUBAGENT_HYBRID_LLM_WEIGHT",
    )
    orch_subagent_hybrid_tie_breaker: str = Field(
        default="rule",
        alias="ORCH_SUBAGENT_HYBRID_TIE_BREAKER",
    )
    orch_subagent_hybrid_strategy_merge_mode: str = Field(
        default="higher_confidence",
        alias="ORCH_SUBAGENT_HYBRID_STRATEGY_MERGE_MODE",
    )
    orch_subagent_hybrid_subagent_merge_mode: str = Field(
        default="union",
        alias="ORCH_SUBAGENT_HYBRID_SUBAGENT_MERGE_MODE",
    )
    orch_subagent_aggregation_overrides: dict[str, Any] = Field(
        default_factory=dict,
        alias="ORCH_SUBAGENT_AGGREGATION_OVERRIDES",
    )
    observability_subagent_backend: str = Field(
        default="memory",
        alias="OBS_SUBAGENT_BACKEND",
    )
    observability_subagent_redis_prefix: str = Field(
        default="agent_platform:subagent_metrics",
        alias="OBS_SUBAGENT_REDIS_PREFIX",
    )
    observability_subagent_recent_limit: int = Field(
        default=20,
        alias="OBS_SUBAGENT_RECENT_LIMIT",
    )
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


class DynamicSettings:
    def __init__(self, static_settings: AppSettings):
        self._static = static_settings
        self._nacos_cache: dict[str, Any] = {}
        self.config_version: int = 0

    def get(self, key: str, fallback: Any = None) -> Any:
        """优先 Nacos 动态值，未命中则回退到 pydantic 静态值"""
        if key in self._nacos_cache:
            return self._nacos_cache[key]
        return getattr(self._static, key, fallback)

    def update_dynamic(self, config: dict[str, Any]) -> None:
        """更新 Nacos 动态配置并自增版本号"""
        self._nacos_cache.update(config)
        self.config_version += 1

    def __getattr__(self, item: str) -> Any:
        """透明代理到静态配置"""
        return getattr(self._static, item)


settings = DynamicSettings(AppSettings())
