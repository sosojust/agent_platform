from pydantic import Field
from pydantic_settings import SettingsConfigDict
from agent_platform_shared.config.settings_base import BaseAppSettings


class Settings(BaseAppSettings):
    port: int = Field(default=8004, alias="PORT")
    internal_gateway_url: str = Field(
        default="http://internal-gateway:8080", alias="INTERNAL_GATEWAY_URL"
    )
    gateway_timeout: float = Field(default=30.0, alias="GATEWAY_TIMEOUT")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", populate_by_name=True
    )


settings = Settings()
