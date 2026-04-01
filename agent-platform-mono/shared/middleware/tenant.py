"""
租户上下文中间件。
从 HTTP Headers 提取租户、用户、渠道等上下文信息，写入 contextvars。
所有下游代码通过 get_current_xxx() 读取，无需手动传参。
"""
import uuid
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import structlog.contextvars

# 已有字段
current_tenant_id: ContextVar[str] = ContextVar("tenant_id", default="unknown")
current_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
current_conversation_id: ContextVar[str] = ContextVar("conversation_id", default="")
current_thread_id: ContextVar[str] = ContextVar("thread_id", default="")
current_user_token: ContextVar[str] = ContextVar("user_token", default="")

# 新增字段 (Task 1.1)
current_user_id: ContextVar[str] = ContextVar("user_id", default="")
current_auth_token: ContextVar[str] = ContextVar("auth_token", default="")
current_channel_id: ContextVar[str] = ContextVar("channel_id", default="")
current_tenant_type: ContextVar[str] = ContextVar("tenant_type", default="")
current_locale: ContextVar[str] = ContextVar("locale", default="zh-CN")
current_timezone: ContextVar[str] = ContextVar("timezone", default="Asia/Shanghai")


class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # 已有字段
        tenant_id = request.headers.get("X-Tenant-Id", "unknown")
        trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
        conversation_id = request.headers.get("X-Conversation-Id", "")
        thread_id = request.headers.get("X-Thread-Id", conversation_id or "")
        user_token = request.headers.get("X-User-Token", "")

        # 新增字段 (Task 1.1)
        user_id = request.headers.get("X-User-Id", "")
        channel_id = request.headers.get("X-Channel-Id", "")
        tenant_type = request.headers.get("X-Tenant-Type", "")
        locale = request.headers.get("X-Locale", "zh-CN")
        timezone = request.headers.get("X-Timezone", "Asia/Shanghai")
        
        # Authorization: Bearer {token} 解析
        auth_header = request.headers.get("Authorization", "")
        auth_token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else ""

        # 设置 ContextVar
        current_tenant_id.set(tenant_id)
        current_trace_id.set(trace_id)
        current_conversation_id.set(conversation_id)
        current_thread_id.set(thread_id)
        current_user_token.set(user_token)
        
        current_user_id.set(user_id)
        current_auth_token.set(auth_token)
        current_channel_id.set(channel_id)
        current_tenant_type.set(tenant_type)
        current_locale.set(locale)
        current_timezone.set(timezone)

        # structlog 绑定（包含新增字段）
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            tenant_id=tenant_id,
            trace_id=trace_id,
            conversation_id=conversation_id,
            thread_id=thread_id,
            user_id=user_id,
            channel_id=channel_id,
            locale=locale,
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


# 新增 getter/setter (Task 1.1)
def get_current_user_id() -> str:
    return current_user_id.get()


def set_current_user_id(value: str) -> None:
    current_user_id.set(value)
    structlog.contextvars.bind_contextvars(user_id=value)


def get_current_auth_token() -> str:
    return current_auth_token.get()


def set_current_auth_token(value: str) -> None:
    current_auth_token.set(value)


def get_current_channel_id() -> str:
    return current_channel_id.get()


def set_current_channel_id(value: str) -> None:
    current_channel_id.set(value)
    structlog.contextvars.bind_contextvars(channel_id=value)


def get_current_tenant_type() -> str:
    return current_tenant_type.get()


def set_current_tenant_type(value: str) -> None:
    current_tenant_type.set(value)


def get_current_locale() -> str:
    return current_locale.get()


def set_current_locale(value: str) -> None:
    current_locale.set(value)
    structlog.contextvars.bind_contextvars(locale=value)


def get_current_timezone() -> str:
    return current_timezone.get()


def set_current_timezone(value: str) -> None:
    current_timezone.set(value)


def set_current_conversation_id(value: str) -> None:
    current_conversation_id.set(value)
    structlog.contextvars.bind_contextvars(conversation_id=value)


def set_current_thread_id(value: str) -> None:
    current_thread_id.set(value)
    structlog.contextvars.bind_contextvars(thread_id=value)


def set_current_user_token(value: str) -> None:
    current_user_token.set(value)
