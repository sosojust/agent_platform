"""MCP 模块

当前 agent-platform-mono 中所有工具都直接在 domain_agents 中定义（使用 FastMCP），
不需要 MCP 客户端。

此模块保留 base.py 作为接口定义，供未来扩展使用（如接入外部 MCP 服务器）。
"""
from .base import MCPClientBase

__all__ = [
    "MCPClientBase",
]

