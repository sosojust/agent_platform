from __future__ import annotations
from typing import Any, Dict, List, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from shared.config.settings import settings
from shared.middleware.tenant import get_current_tenant_id, get_current_trace_id


class MCPServiceProvider:
    def __init__(self, base_url: Optional[str] = None, timeout: int | float = 30) -> None:
        self._base_url = base_url or settings.mcp_service_url
        self._timeout = timeout

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {}
        tid = get_current_tenant_id()
        rid = get_current_trace_id()
        if tid:
            h["X-Tenant-Id"] = tid
        if rid:
            h["X-Trace-Id"] = rid
        return h

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4), retry=retry_if_exception_type(httpx.HTTPError))
    async def list_tools(self) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout, headers=self._headers()) as c:
            r = await c.get("/tools")
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and "tools" in data:
                return data["tools"] or []
            if isinstance(data, list):
                return data
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4), retry=retry_if_exception_type(httpx.HTTPError))
    async def invoke(self, tool: str, arguments: Dict[str, Any]) -> Any:
        payload = {"tool": tool, "arguments": arguments}
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout, headers=self._headers()) as c:
            r = await c.post("/invoke", json=payload)
            r.raise_for_status()
            return r.json()
