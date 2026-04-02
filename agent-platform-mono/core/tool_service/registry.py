# core/tool_service/registry.py
"""
Tool Gateway - 统一的工具网关

提供：
- 工具注册表
- 工具发现（带权限过滤）
- 工具调用（带权限检查）
- 审计日志
"""
from typing import Any, Dict, List
from dataclasses import dataclass
from shared.logging.logger import get_logger
from .types import ToolMetadata, ToolContext
from .base.adapter import ToolAdapter
from .base.permissions import BasePermissionChecker

logger = get_logger(__name__)


@dataclass
class ToolEntry:
    """工具注册条目"""
    metadata: ToolMetadata
    adapter: ToolAdapter


class ToolGateway:
    """
    工具网关 - 统一的工具管理入口。
    
    职责：
    - 工具注册和管理
    - 工具发现（带权限过滤）
    - 工具调用（带权限检查）
    - 审计日志
    """
    
    def __init__(self, permission_checker: BasePermissionChecker | None = None):
        """
        Args:
            permission_checker: 权限检查器（可选）
        """
        self._tools: Dict[str, ToolEntry] = {}
        self._adapters: List[ToolAdapter] = []
        self.permission_checker = permission_checker or BasePermissionChecker()
    
    def register_adapter(self, adapter: ToolAdapter):
        """注册一个 Adapter"""
        self._adapters.append(adapter)
        logger.info(
            "adapter_registered",
            adapter_type=adapter.get_adapter_type(),
        )
    
    async def load_tools_from_adapter(self, adapter: ToolAdapter):
        """从 Adapter 加载工具"""
        tools = await adapter.load_tools()
        
        for metadata in tools:
            # 验证工具
            is_valid, errors = await adapter.validate_tool(metadata)
            if not is_valid:
                logger.error(
                    "tool_validation_failed",
                    tool_name=metadata.name,
                    errors=errors,
                )
                continue
            
            # 注册工具
            self._tools[metadata.name] = ToolEntry(
                metadata=metadata,
                adapter=adapter,
            )
        
        logger.info(
            "tools_loaded_from_adapter",
            adapter_type=adapter.get_adapter_type(),
            count=len(tools),
        )
    
    async def list_tools(
        self,
        context: ToolContext | None = None,
        category: str | None = None,
    ) -> List[Dict[str, Any]]:
        """
        列出所有工具（带权限过滤）。
        
        Args:
            context: 工具上下文（用于权限过滤）
            category: 工具分类过滤
        
        Returns:
            工具列表（字典格式）
        """
        tools = []
        
        for tool_name, tool_entry in self._tools.items():
            metadata = tool_entry.metadata
            
            # 分类过滤
            if category and metadata.category != category:
                continue
            
            # 权限过滤（如果提供了 context）
            if context:
                has_permission, _ = await self.permission_checker.check_permission(
                    metadata, context
                )
                if not has_permission:
                    continue
            
            # 转换为字典
            tools.append({
                "name": metadata.name,
                "description": metadata.description,
                "type": metadata.type.value,
                "adapter": metadata.adapter_type.value,
                "category": metadata.category,
                "input_schema": metadata.input_schema,
                "tags": metadata.tags,
            })
        
        return tools
    
    async def invoke(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Any:
        """
        调用工具（带权限检查和审计）。
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            context: 工具上下文
        
        Returns:
            工具执行结果
        
        Raises:
            ValueError: 工具不存在
            PermissionError: 权限不足
        """
        # 1. 查找工具
        tool_entry = self._tools.get(tool_name)
        if not tool_entry:
            raise ValueError(f"Tool not found: {tool_name}")
        
        # 2. 权限检查
        has_permission, msg = await self.permission_checker.check_permission(
            tool_entry.metadata, context
        )
        if not has_permission:
            logger.warning(
                "tool_permission_denied",
                tool_name=tool_name,
                tenant_id=context.tenant_id,
                reason=msg,
            )
            raise PermissionError(f"Permission denied: {msg}")
        
        # 3. 调用工具
        logger.info(
            "tool_invoking",
            tool_name=tool_name,
            tenant_id=context.tenant_id,
            adapter_type=tool_entry.adapter.get_adapter_type(),
        )
        
        try:
            result = await tool_entry.adapter.invoke_tool(
                metadata=tool_entry.metadata,
                arguments=arguments,
                context=context,
            )
            
            logger.info(
                "tool_invoked_success",
                tool_name=tool_name,
                tenant_id=context.tenant_id,
            )
            
            return result
        
        except Exception as e:
            logger.error(
                "tool_invoked_failed",
                tool_name=tool_name,
                tenant_id=context.tenant_id,
                error=str(e),
            )
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        adapter_status = {}
        
        for adapter in self._adapters:
            adapter_type = adapter.get_adapter_type()
            is_healthy = await adapter.health_check()
            adapter_status[adapter_type] = is_healthy
        
        return {
            "healthy": all(adapter_status.values()),
            "adapters": adapter_status,
            "tool_count": len(self._tools),
        }
    
    async def close(self):
        """关闭所有 Adapter"""
        for adapter in self._adapters:
            await adapter.close()


# 全局单例
tool_gateway = ToolGateway()
