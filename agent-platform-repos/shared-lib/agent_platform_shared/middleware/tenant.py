"""租户上下文中间件，所有服务共用。"""
import uuid
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import structlog.contextvars

current_tenant_id: ContextVar[str] = ContextVar("tenant_id", default="unknown")
current_trace_id: ContextVar[str] = ContextVar("trace_id", default="")


class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        tenant_id = request.headers.get("X-Tenant-Id", "unknown")
        trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
        current_tenant_id.set(tenant_id)
        current_trace_id.set(trace_id)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(tenant_id=tenant_id, trace_id=trace_id)
        return await call_next(request)


def get_current_tenant_id() -> str:
    return current_tenant_id.get()


def get_current_trace_id() -> str:
    return current_trace_id.get()
