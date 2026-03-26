from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class MCPClientBase(ABC):
    @abstractmethod
    async def list_tools(self) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    async def invoke(self, tool: str, arguments: Dict[str, Any]) -> Any:
        ...
