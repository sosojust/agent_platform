# core/tool_service/external_mcp/__init__.py
"""
External MCP Adapter - 对接外部 MCP Server

用于对接第三方 MCP 服务器（如天气、日历等）。
"""
from .adapter import ExternalMCPAdapter
from .validator import ExternalMCPValidator

__all__ = [
    "ExternalMCPAdapter",
    "ExternalMCPValidator",
]
