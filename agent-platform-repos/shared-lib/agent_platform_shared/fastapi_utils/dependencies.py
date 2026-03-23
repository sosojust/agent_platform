"""
公用 FastAPI Depends 依赖项。
各服务直接从这里 import，不需要重复定义。
"""
from fastapi import Header, HTTPException
from agent_platform_shared.middleware.tenant import get_current_tenant_id, get_current_trace_id


async def require_tenant_id(x_tenant_id: str = Header(default="")) -> str:
    """
    强制要求 X-Tenant-Id Header，缺少时返回 400。
    对需要严格租户隔离的接口使用：
        @app.post("/agent/run")
        async def run(tenant_id: str = Depends(require_tenant_id)):
    """
    tenant_id = x_tenant_id or get_current_tenant_id()
    if not tenant_id or tenant_id == "unknown":
        raise HTTPException(status_code=400, detail="X-Tenant-Id header is required")
    return tenant_id


async def get_tenant_id() -> str:
    """
    获取当前请求的 tenant_id（不强制，unknown 时不报错）。
    对不要求租户隔离的接口使用（如 /health）。
    """
    return get_current_tenant_id()


async def get_trace_id() -> str:
    """获取当前请求的 trace_id。"""
    return get_current_trace_id()
