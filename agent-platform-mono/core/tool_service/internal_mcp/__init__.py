# core/tool_service/internal_mcp/__init__.py
"""
Internal MCP Adapter - 对接内部微服务

用于对接内部微服务（Spring Boot 等）。
本质是 HTTP Adapter 的 MCP 协议封装。
"""
from .adapter import InternalMCPAdapter
from .validator import InternalMCPValidator
from .client import InternalHTTPClient

__all__ = [
    "InternalMCPAdapter",
    "InternalMCPValidator",
    "InternalHTTPClient",
]
