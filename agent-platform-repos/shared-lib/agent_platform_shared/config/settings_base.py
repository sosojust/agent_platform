"""
各服务继承的基础 Settings。
公共字段定义在此，各服务在自己的 config/settings.py 中追加专属字段。
"""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class NacosSettings(BaseSettings):
    server_addr: str = Field(default="", alias="NACOS_SERVER_ADDR")
    namespace: str = Field(default="agent-platform", alias="NACOS_NAMESPACE")
    group: str = Field(default="DEFAULT_GROUP", alias="NACOS_GROUP")
    data_id: str = Field(default="agent-platform.json", alias="NACOS_DATA_ID")
    model_config = SettingsConfigDict(populate_by_name=True)


class ObservabilitySettings(BaseSettings):
    langfuse_host: str = Field(default="http://localhost:3000", alias="LANGFUSE_HOST")
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    otel_endpoint: str = Field(default="http://localhost:4317",
                               alias="OTEL_EXPORTER_OTLP_ENDPOINT")
    model_config = SettingsConfigDict(populate_by_name=True)


class BaseAppSettings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    nacos: NacosSettings = Field(default_factory=NacosSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", populate_by_name=True
    )
