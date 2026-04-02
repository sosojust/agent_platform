# core/tool_service/internal_mcp/adapter.py
"""
内部 MCP 适配器

用于对接内部微服务（Spring Boot 等）。
本质是 HTTP Adapter 的 MCP 协议封装。

特点：
- 透传上下文信息（tenant_id, user_id 等）
- 使用内部网络
- 支持服务发现
- 委托给 InternalHTTPClient 执行（代码复用）
"""
from typing import Any, Dict, List
import httpx
from shared.logging.logger import get_logger
from ..base.adapter import ToolAdapter
from ..types import ToolMetadata, ToolContext, ToolType, AdapterType, InternalMCPToolMetadata
from .client import InternalHTTPClient

logger = get_logger(__name__)


class InternalMCPAdapter(ToolAdapter):
    """
    内部 MCP 适配器。
    
    用于对接内部微服务（Spring Boot 等）。
    本质是 HTTP Adapter 的 MCP 协议封装。
    
    特点：
    - 透传上下文信息（tenant_id, user_id 等）
    - 使用内部网络
    - 支持服务发现
    - 委托给 InternalHTTPClient 执行（代码复用）
    """
    
    def __init__(self, domain: str, service_name: str, base_url: str):
        """
        Args:
            domain: 域名（policy, claim, customer）
            service_name: 服务名称（policy-service, claim-service）
            base_url: 服务基础 URL
        """
        self.domain = domain
        self.service_name = service_name
        self.client = InternalHTTPClient(base_url)  # 使用 InternalHTTPClient
        self._tools: Dict[str, dict] = {}
    
    def register_tool(
        self,
        name: str,
        description: str,
        endpoint: str,
        method: str = "POST",
        input_schema: dict | None = None,
    ):
        """
        注册一个内部服务的工具。
        
        Args:
            name: 工具名称
            description: 工具描述
            endpoint: API 端点（相对路径）
            method: HTTP 方法
            input_schema: 输入 schema
        """
        self._tools[name] = {
            "description": description,
            "endpoint": endpoint,
            "method": method.upper(),
            "input_schema": input_schema or {},
        }
    
    async def load_tools(self) -> List[ToolMetadata]:
        """加载所有已注册的工具"""
        tools = []
        
        for name, tool_info in self._tools.items():
            metadata = InternalMCPToolMetadata(
                name=name,
                description=tool_info["description"],
                type=ToolType.TOOL,
                category=self.domain,
                input_schema=tool_info["input_schema"],
                source_domain=self.domain,
                tags=["internal", "mcp", self.domain],
                # Internal MCP 特定字段
                base_url=self.client.base_url,
                endpoint=tool_info["endpoint"],
                method=tool_info["method"],
                service_name=self.service_name,
            )
            tools.append(metadata)
        
        logger.info(
            "internal_mcp_tools_loaded",
            domain=self.domain,
            service=self.service_name,
            count=len(tools),
        )
        
        return tools
    
    async def validate_tool(self, metadata: ToolMetadata) -> tuple[bool, list[str]]:
        """验证内部 MCP 工具（使用 InternalMCPValidator）"""
        from .validator import InternalMCPValidator
        validator = InternalMCPValidator()
        return await validator.validate(metadata)
    
    async def invoke_tool(
        self,
        metadata: ToolMetadata,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Any:
        """
        调用内部服务的工具。
        
        委托给 InternalHTTPClient 执行（代码复用）。
        """
        tool_info = self._tools.get(metadata.name)
        if not tool_info:
            raise ValueError(f"Tool not found: {metadata.name}")
        
        try:
            # 委托给 InternalHTTPClient（避免重复实现）
            return await self.client.call(
                endpoint=tool_info["endpoint"],
                method=tool_info["method"],
                data=arguments,
                context=context,
            )
        
        except httpx.HTTPStatusError as e:
            logger.error(
                "internal_mcp_invoke_failed",
                tool_name=metadata.name,
                service=self.service_name,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise
        except Exception as e:
            logger.error(
                "internal_mcp_error",
                tool_name=metadata.name,
                service=self.service_name,
                error=str(e),
            )
            raise
    
    def get_adapter_type(self) -> str:
        return AdapterType.INTERNAL_MCP.value
    
    async def close(self):
        """关闭客户端"""
        await self.client.close()
