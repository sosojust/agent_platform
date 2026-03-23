"""
FastAPI 公共工具包。
各服务只需从这里 import，不需要了解内部模块结构。
"""
from agent_platform_shared.fastapi_utils.app_factory import create_app
from agent_platform_shared.fastapi_utils.health import ReadinessRegistry, make_health_router
from agent_platform_shared.fastapi_utils.error_handlers import register_error_handlers
from agent_platform_shared.fastapi_utils.dependencies import (
    require_tenant_id,
    get_tenant_id,
    get_trace_id,
)

__all__ = [
    "create_app",
    "ReadinessRegistry",
    "make_health_router",
    "register_error_handlers",
    "require_tenant_id",
    "get_tenant_id",
    "get_trace_id",
]
