# core/tool_service/internal_mcp/client.py
"""
内部 HTTP 客户端封装

职责：
- 封装 HTTP 调用逻辑
- 透传上下文信息（tenant_id, user_id 等）
- 统一错误处理
- 支持多种 HTTP 方法

被 InternalMCPAdapter 使用（代码复用）。
"""
import httpx
from typing import Any, Dict
from ..types import ToolContext


class InternalHTTPClient:
    """
    内部 HTTP 客户端封装。
    
    职责：
    - 封装 HTTP 调用逻辑
    - 透传上下文信息（tenant_id, user_id 等）
    - 统一错误处理
    - 支持多种 HTTP 方法
    
    被 InternalMCPAdapter 使用（代码复用）。
    """
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=30)
    
    async def call(
        self,
        endpoint: str,
        method: str,
        data: Dict[str, Any],
        context: ToolContext,
    ) -> Any:
        """
        调用内部服务（透传上下文）。
        
        Args:
            endpoint: API 端点（相对路径）
            method: HTTP 方法（GET/POST/PUT/DELETE）
            data: 请求数据
            context: 工具上下文（用于透传）
        
        Returns:
            响应 JSON 数据
        
        Raises:
            httpx.HTTPStatusError: HTTP 错误
            ValueError: 不支持的 HTTP 方法
        """
        url = f"{self.base_url}{endpoint}"
        
        # 透传上下文信息
        headers = {
            "Content-Type": "application/json",
            "X-Tenant-ID": context.tenant_id,
            "X-User-ID": context.user_id or "",
            "X-Channel-ID": context.channel_id or "",
            "X-Request-ID": context.request_id or "",
            "X-Conversation-ID": context.conversation_id or "",
        }
        
        # 根据 HTTP 方法调用
        if method == "GET":
            response = await self._client.get(url, params=data, headers=headers)
        elif method == "POST":
            response = await self._client.post(url, json=data, headers=headers)
        elif method == "PUT":
            response = await self._client.put(url, json=data, headers=headers)
        elif method == "DELETE":
            response = await self._client.delete(url, params=data, headers=headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        """关闭客户端"""
        await self._client.aclose()
