"""内网 Spring Cloud Gateway HTTP 客户端，统一注入 tenant header + 重试。"""
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
    # 新增导入 (Task 1.1)
    get_current_user_id,
    get_current_auth_token,
    get_current_channel_id,
    get_current_tenant_type,
    get_current_locale,
    get_current_timezone,
)

logger = get_logger(__name__)


def _headers() -> dict:
    """构建请求头，透传所有上下文字段"""
    h = {
        "X-Tenant-Id": get_current_tenant_id(),
        "X-Trace-Id": get_current_trace_id(),
        "X-Conversation-Id": get_current_conversation_id(),
        "X-Thread-Id": get_current_thread_id() or get_current_conversation_id(),
        "X-Source": "agent",
        "Content-Type": "application/json",
    }
    
    # 已有字段
    token = get_current_user_token()
    if token:
        h["X-User-Token"] = token
    
    # 新增字段透传 (Task 1.1)
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
    
    # Accept-Language 使用 locale
    h["Accept-Language"] = get_current_locale() or "zh-CN"
    
    return h


class GatewayProvider:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.internal_gateway_url,
            timeout=settings.gateway_timeout,
        )

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(min=1, max=10),
           retry=retry_if_exception_type(httpx.TransportError),
           reraise=True)
    async def get(self, path: str, params: dict | None = None) -> dict:
        resp = await self._client.get(path, params=params, headers=_headers())
        resp.raise_for_status()
        logger.info("gateway_get", path=path, status=resp.status_code)
        return resp.json()

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(min=1, max=10),
           retry=retry_if_exception_type(httpx.TransportError),
           reraise=True)
    async def post(self, path: str, body: dict) -> dict:
        resp = await self._client.post(path, json=body, headers=_headers())
        resp.raise_for_status()
        logger.info("gateway_post", path=path, status=resp.status_code)
        return resp.json()

    async def close(self) -> None:
        await self._client.aclose()


internal_gateway = GatewayProvider()
