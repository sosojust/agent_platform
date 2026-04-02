# core/tool_service/external_mcp/adapter.py
"""
外部 MCP Server 适配器

用于对接第三方 MCP 服务器（如天气、日历等）。

特点：
- 使用 token 认证
- 不透传内部上下文（安全考虑）
- 支持重试机制
"""
from typing import Any, Dict, List
import httpx
from shared.logging.logger import get_logger
from ..base.adapter import ToolAdapter
from ..types import ToolMetadata, ToolContext, ToolType, AdapterType, ExternalMCPToolMetadata

logger = get_logger(__name__)


class ExternalMCPAdapter(ToolAdapter):
    """
    外部 MCP Server 适配器。
    
    用于对接第三方 MCP 服务器（如天气、日历等）。
    
    特点：
    - 使用 token 认证
    - 不透传内部上下文（安全考虑）
    - 支持重试机制
    """
    
    def __init__(self, name: str, endpoint: str, token: str):
        """
        Args:
            name: 服务名称（如 "weather", "calendar"）
            endpoint: MCP Server 端点
            token: 认证 token
        """
        self.name = name
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self._client = httpx.AsyncClient(timeout=30)
        self._tools_cache: Dict[str, dict] = {}
    
    async def load_tools(self) -> List[ToolMetadata]:
        """从外部 MCP Server 加载工具"""
        try:
            response = await self._client.post(
                f"{self.endpoint}/mcp/list_tools",
                headers={"Authorization": f"Bearer {self.token}"},
            )
            response.raise_for_status()
            data = response.json()
            
            tools = []
            for tool_def in data.get("tools", []):
                tool_name = f"{self.name}:{tool_def['name']}"  # 加前缀
                
                metadata = ExternalMCPToolMetadata(
                    name=tool_name,
                    description=tool_def.get("description", ""),
                    type=ToolType.TOOL,
                    category=self.name,
                    input_schema=tool_def.get("inputSchema", {}),
                    output_schema=tool_def.get("outputSchema"),
                    tags=["external", "mcp", self.name],
                    # External MCP 特定字段
                    mcp_server_name=self.name,
                    original_tool_name=tool_def['name'],
                )
                
                tools.append(metadata)
                self._tools_cache[tool_name] = tool_def
            
            logger.info(
                "external_mcp_tools_loaded",
                name=self.name,
                endpoint=self.endpoint,
                count=len(tools),
            )
            
            return tools
        
        except Exception as e:
            logger.error(
                "external_mcp_load_failed",
                name=self.name,
                endpoint=self.endpoint,
                error=str(e),
            )
            return []
    
    async def validate_tool(self, metadata: ToolMetadata) -> tuple[bool, list[str]]:
        """验证外部 MCP 工具"""
        from .validator import ExternalMCPValidator
        validator = ExternalMCPValidator()
        return await validator.validate(metadata)
    
    async def invoke_tool(
        self,
        metadata: ToolMetadata,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Any:
        """调用外部 MCP Server 的工具"""
        tool_def = self._tools_cache.get(metadata.name)
        if not tool_def:
            raise ValueError(f"Tool not found: {metadata.name}")
        
        # 提取原始工具名（去掉前缀）
        original_tool_name = tool_def["name"]
        
        try:
            response = await self._client.post(
                f"{self.endpoint}/mcp/invoke",
                headers={"Authorization": f"Bearer {self.token}"},
                json={
                    "tool": original_tool_name,
                    "arguments": arguments,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("result")
        
        except Exception as e:
            logger.error(
                "external_mcp_invoke_failed",
                tool_name=metadata.name,
                error=str(e),
            )
            raise
    
    def get_adapter_type(self) -> str:
        return AdapterType.EXTERNAL_MCP.value
    
    async def close(self):
        """关闭客户端"""
        await self._client.aclose()
