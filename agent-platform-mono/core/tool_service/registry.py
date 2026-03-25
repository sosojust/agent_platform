from __future__ import annotations
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol
import asyncio


class McpClient(Protocol):
    async def list_tools(self) -> List[Dict[str, Any]]: ...
    async def invoke(self, tool: str, arguments: Dict[str, Any]) -> Any: ...


class ToolEntry:
    def __init__(
        self,
        name: str,
        type_: str,
        provider: str,
        caller: Callable[[Dict[str, Any]], Awaitable[Any]],
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.name = name
        self.type = type_
        self.provider = provider
        self._caller = caller
        self.input_schema = input_schema or {}
        self.output_schema = output_schema or {}

    async def __call__(self, arguments: Dict[str, Any]) -> Any:
        res = self._caller(arguments)
        if asyncio.iscoroutine(res):
            return await res
        return res


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolEntry] = {}
        self._mcp_clients: Dict[str, McpClient] = {}

    def register_skill(
        self,
        name: str,
        func: Callable[[Dict[str, Any]], Any | Awaitable[Any]],
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        provider: str = "skill",
    ) -> None:
        async def caller(args: Dict[str, Any]) -> Any:
            res = func(args)
            if asyncio.iscoroutine(res):
                return await res
            return res

        entry = ToolEntry(
            name=name,
            type_="skill",
            provider=provider,
            caller=caller,
            input_schema=input_schema,
            output_schema=output_schema,
        )
        self._tools[name] = entry

    async def register_mcp_client(self, provider: str, client: McpClient) -> None:
        self._mcp_clients[provider] = client
        tools = await client.list_tools()
        for t in tools:
            t_name = t.get("name") or ""
            input_schema = t.get("inputSchema") or t.get("input_schema") or {}
            output_schema = t.get("outputSchema") or t.get("output_schema") or {}
            fq_name = f"{provider}:{t_name}" if provider else t_name

            async def caller(args: Dict[str, Any], _client: McpClient = client, _tool=t_name) -> Any:
                return await _client.invoke(_tool, args)

            self._tools[fq_name] = ToolEntry(
                name=fq_name,
                type_="mcp",
                provider=provider,
                caller=caller,
                input_schema=input_schema,
                output_schema=output_schema,
            )

    def list_tools(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for t in self._tools.values():
            items.append(
                {
                    "name": t.name,
                    "type": t.type,
                    "provider": t.provider,
                    "input_schema": t.input_schema,
                    "output_schema": t.output_schema,
                }
            )
        return items

    async def invoke(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        entry = self._tools.get(tool_name)
        if not entry:
            raise ValueError(f"tool_not_found: {tool_name}")
        return await entry(arguments)


registry = ToolRegistry()
