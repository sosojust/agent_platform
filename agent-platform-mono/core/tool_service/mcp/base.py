"""MCP 客户端基类

注意：当前 agent-platform-mono 中所有工具都直接在 domain_agents 中定义，
不需要 MCP 客户端。此模块保留作为接口定义，供未来扩展使用。
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class MCPClientBase(ABC):
    """MCP 客户端抽象基类
    
    如果未来需要接入独立的 MCP 服务或外部 MCP 服务器，
    可以实现此接口。
    """
    
    @abstractmethod
    async def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有可用的工具"""
        ...

    @abstractmethod
    async def invoke(self, tool: str, arguments: Dict[str, Any]) -> Any:
        """调用指定的工具"""
        ...
