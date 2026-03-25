"""租户上下文中间件，所有服务共用。"""
import uuid
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import structlog.contextvars

current_tenant_id: ContextVar[str] = ContextVar("tenant_id", default="unknown")
current_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
current_conversation_id: ContextVar[str] = ContextVar("conversation_id", default="")
current_thread_id: ContextVar[str] = ContextVar("thread_id", default="")
current_user_token: ContextVar[str] = ContextVar("user_token", default="")


class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        tenant_id = request.headers.get("X-Tenant-Id", "unknown")
        trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
        conversation_id = request.headers.get("X-Conversation-Id", "")
        thread_id = request.headers.get("X-Thread-Id", conversation_id or "")
        user_token = request.headers.get("X-User-Token", "")

        current_tenant_id.set(tenant_id)
        current_trace_id.set(trace_id)
        current_conversation_id.set(conversation_id)
        current_thread_id.set(thread_id)
        current_user_token.set(user_token)

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            tenant_id=tenant_id,
            trace_id=trace_id,
            conversation_id=conversation_id,
            thread_id=thread_id,
        )
        return await call_next(request)


def get_current_tenant_id() -> str:
    return current_tenant_id.get()


def get_current_trace_id() -> str:
    return current_trace_id.get()


def get_current_conversation_id() -> str:
    return current_conversation_id.get()


def get_current_thread_id() -> str:
    return current_thread_id.get()


def get_current_user_token() -> str:
    return current_user_token.get()


def set_current_conversation_id(value: str) -> None:
    current_conversation_id.set(value)


def set_current_thread_id(value: str) -> None:
    current_thread_id.set(value)
