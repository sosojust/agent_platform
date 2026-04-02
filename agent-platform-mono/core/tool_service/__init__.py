# core/tool_service/__init__.py
"""
Tool Service - 统一的工具管理服务

提供：
- 统一的工具注册和管理
- 多种 Adapter 支持（External MCP, Internal MCP, Skill, Function）
- 智能工具路由
- 权限控制
- 审计日志
"""
from .types import (
    ToolType,
    AdapterType,
    PermissionStrategy,
    ToolMetadata,
    ExternalMCPToolMetadata,
    InternalMCPToolMetadata,
    SkillToolMetadata,
    FunctionToolMetadata,
    ToolContext,
)
from .registry import ToolGateway, tool_gateway
from .router import ToolRouter, MatchStrategy, init_tool_router
from .base import ToolAdapter, BaseValidator, BasePermissionChecker

# Adapters
from .external_mcp import ExternalMCPAdapter, ExternalMCPValidator
from .internal_mcp import InternalMCPAdapter, InternalMCPValidator, InternalHTTPClient
from .skill import SkillAdapter, SkillDefinition, SkillValidator, SkillExecutor
from .function import FunctionAdapter, FunctionValidator

__all__ = [
    # Types
    "ToolType",
    "AdapterType",
    "PermissionStrategy",
    "ToolMetadata",
    "ExternalMCPToolMetadata",
    "InternalMCPToolMetadata",
    "SkillToolMetadata",
    "FunctionToolMetadata",
    "ToolContext",
    # Core
    "ToolGateway",
    "tool_gateway",
    "ToolRouter",
    "MatchStrategy",
    "init_tool_router",
    # Base
    "ToolAdapter",
    "BaseValidator",
    "BasePermissionChecker",
    # External MCP
    "ExternalMCPAdapter",
    "ExternalMCPValidator",
    # Internal MCP
    "InternalMCPAdapter",
    "InternalMCPValidator",
    "InternalHTTPClient",
    # Skill
    "SkillAdapter",
    "SkillDefinition",
    "SkillValidator",
    "SkillExecutor",
    # Function
    "FunctionAdapter",
    "FunctionValidator",
]
