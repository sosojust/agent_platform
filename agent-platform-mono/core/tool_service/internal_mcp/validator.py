# core/tool_service/internal_mcp/validator.py
"""
内部 MCP 工具验证器

继承 BaseValidator，只需实现特定验证逻辑。
"""
from ..base.validator import BaseValidator
from ..types import InternalMCPToolMetadata


class InternalMCPValidator(BaseValidator):
    """
    内部 MCP 工具验证器。
    
    继承 BaseValidator，只需实现特定验证逻辑。
    """
    
    async def _validate_specific(self, metadata: InternalMCPToolMetadata) -> list[str]:
        """内部 MCP 特定验证"""
        errors = []
        
        # 类型检查
        if not isinstance(metadata, InternalMCPToolMetadata):
            errors.append(f"内部 MCP 工具必须使用 InternalMCPToolMetadata，当前类型: {type(metadata).__name__}")
            return errors  # 类型错误，后续检查无意义
        
        # 检查 base_url
        if not metadata.base_url:
            errors.append("内部 MCP 工具必须配置 base_url")
        
        # 检查 endpoint
        if not metadata.endpoint:
            errors.append("内部 MCP 工具必须配置 endpoint")
        
        # 检查 method
        valid_methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
        if metadata.method.upper() not in valid_methods:
            errors.append(f"HTTP 方法必须是 {valid_methods} 之一，当前: {metadata.method}")
        
        # 检查 service_name
        if not metadata.service_name:
            errors.append("内部 MCP 工具必须配置 service_name")
        
        return errors
