"""通用 HTTP 客户端，用于调用内部服务 API。"""
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from shared.config.settings import settings
from shared.logging.logger import get_logger
from shared.middleware.tenant import (
    get_current_tenant_id,
    get_current_trace_id,
    get_current_conversation_id,
    get_current_thread_id,
    get_current_user_token,
    get_current_user_id,
    get_current_auth_token,
    get_current_channel_id,
    get_current_tenant_type,
    get_current_locale,
    get_current_timezone,
)

logger = get_logger(__name__)


def build_context_headers() -> dict:
    """构建请求头，透传所有上下文字段"""
    h = {
        "X-Tenant-Id": get_current_tenant_id(),
        "X-Trace-Id": get_current_trace_id(),
        "X-Conversation-Id": get_current_conversation_id(),
        "X-Thread-Id": get_current_thread_id() or get_current_conversation_id(),
        "X-Source": "agent",
        "Content-Type": "application/json",
    }
    
    if token := get_current_user_token():
        h["X-User-Token"] = token
    
    if user_id := get_current_user_id():
        h["X-User-Id"] = user_id
    
    if auth_token := get_current_auth_token():
        h["Authorization"] = f"Bearer {auth_token}"
    
    if channel_id := get_current_channel_id():
        h["X-Channel-Id"] = channel_id
    
    if tenant_type := get_current_tenant_type():
        h["X-Tenant-Type"] = tenant_type
    
    if timezone := get_current_timezone():
        h["X-Timezone"] = timezone
    
    h["Accept-Language"] = get_current_locale() or "zh-CN"
    
    return h


class InternalAPIClient:
    """内部服务 API 客户端，用于 MCP 工具调用后端服务"""
    
    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        self._base_url = base_url or settings.internal_gateway_url
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type(httpx.TransportError),
        reraise=True
    )
    async def get(self, path: str, params: dict | None = None) -> dict:
        client = await self._get_client()
        resp = await client.get(path, params=params, headers=build_context_headers())
        resp.raise_for_status()
        logger.info("internal_api_get", path=path, status=resp.status_code)
        return resp.json()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type(httpx.TransportError),
        reraise=True
    )
    async def post(self, path: str, body: dict) -> dict:
        client = await self._get_client()
        resp = await client.post(path, json=body, headers=build_context_headers())
        resp.raise_for_status()
        logger.info("internal_api_post", path=path, status=resp.status_code)
        return resp.json()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# 全局单例
_internal_api_client: InternalAPIClient | None = None


def get_internal_api_client() -> InternalAPIClient:
    """获取内部 API 客户端单例"""
    global _internal_api_client
    if _internal_api_client is None:
        _internal_api_client = InternalAPIClient()
    return _internal_api_client
