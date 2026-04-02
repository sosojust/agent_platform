# core/tool_service/external_mcp/validator.py
"""
外部 MCP 工具验证器

继承 BaseValidator，只需实现特定验证逻辑。
"""
from ..base.validator import BaseValidator
from ..types import ExternalMCPToolMetadata


class ExternalMCPValidator(BaseValidator):
    """
    外部 MCP 工具验证器。
    
    继承 BaseValidator，只需实现特定验证逻辑。
    """
    
    async def _validate_specific(self, metadata: ExternalMCPToolMetadata) -> list[str]:
        """外部 MCP 特定验证"""
        errors = []
        
        # 类型检查
        if not isinstance(metadata, ExternalMCPToolMetadata):
            errors.append(f"外部 MCP 工具必须使用 ExternalMCPToolMetadata，当前类型: {type(metadata).__name__}")
            return errors  # 类型错误，后续检查无意义
        
        # 检查 mcp_server_name
        if not metadata.mcp_server_name:
            errors.append("外部 MCP 工具必须配置 mcp_server_name")
        
        # 检查 original_tool_name
        if not metadata.original_tool_name:
            errors.append("外部 MCP 工具必须配置 original_tool_name")
        
        return errors
