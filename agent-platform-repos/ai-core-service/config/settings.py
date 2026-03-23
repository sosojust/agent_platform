from pydantic import Field
from pydantic_settings import SettingsConfigDict
from agent_platform_shared.config.settings_base import BaseAppSettings


class Settings(BaseAppSettings):
    port: int = Field(default=8002, alias="PORT")

    # LLM 模型配置
    default_model: str = Field(default="openai/gpt-4o-mini", alias="LLM_DEFAULT_MODEL")
    strong_model: str = Field(default="openai/gpt-4o", alias="LLM_STRONG_MODEL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    local_model_base_url: str = Field(default="", alias="LOCAL_MODEL_BASE_URL")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", populate_by_name=True
    )


settings = Settings()
