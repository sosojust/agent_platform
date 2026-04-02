# core/tool_service/types.py
"""
Tool Service 通用类型定义

包含所有工具类型的通用字段和类型特定的 Metadata 子类。
"""
from dataclasses import dataclass, field
from typing import Any, Callable
from enum import Enum


class ToolType(str, Enum):
    """工具类型"""
    TOOL = "tool"          # 确定性工具
    SKILL = "skill"        # LLM 驱动的 Skill


class AdapterType(str, Enum):
    """适配器类型"""
    EXTERNAL_MCP = "external_mcp"    # 外部 MCP Server
    INTERNAL_MCP = "internal_mcp"    # 内部 MCP（微服务）
    SKILL = "skill"                  # Skill（LLM 驱动）
    FUNCTION = "function"            # Python 函数


class PermissionStrategy(str, Enum):
    """权限检查策略"""
    LOCAL_ONLY = "local_only"              # 仅本地检查（默认）
    REMOTE_ONLY = "remote_only"            # 仅远程检查
    LOCAL_AND_REMOTE = "local_and_remote"  # 双重检查
    LOCAL_OR_REMOTE = "local_or_remote"    # 任一通过


@dataclass
class ToolMetadata:
    """
    工具元数据基类。
    
    包含所有工具类型的通用字段。
    不同类型的工具应该使用对应的子类。
    """
    name: str
    description: str
    type: ToolType                    # tool 或 skill
    adapter_type: AdapterType         # 适配器类型
    category: str
    
    # Schema
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    
    # 权限控制
    allowed_tenants: list[str] | None = None
    allowed_channels: list[str] | None = None
    allowed_users: list[str] | None = None
    allowed_tenant_types: list[str] | None = None
    permission_strategy: PermissionStrategy = PermissionStrategy.LOCAL_ONLY  # 默认本地检查
    
    # 其他元数据
    tags: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    source_module: str | None = None
    source_domain: str | None = None


@dataclass
class ExternalMCPToolMetadata(ToolMetadata):
    """
    外部 MCP 工具元数据。
    
    额外字段：
    - mcp_server_name: MCP Server 名称
    - original_tool_name: 原始工具名（去掉前缀）
    """
    mcp_server_name: str = ""
    original_tool_name: str = ""
    
    def __post_init__(self):
        """确保 adapter_type 正确"""
        self.adapter_type = AdapterType.EXTERNAL_MCP


@dataclass
class InternalMCPToolMetadata(ToolMetadata):
    """
    内部 MCP 工具元数据。
    
    额外字段：
    - base_url: 服务基础 URL
    - endpoint: API 端点
    - method: HTTP 方法
    - service_name: 服务名称
    """
    base_url: str = ""
    endpoint: str = ""
    method: str = "POST"
    service_name: str = ""
    
    def __post_init__(self):
        """确保 adapter_type 正确"""
        self.adapter_type = AdapterType.INTERNAL_MCP


@dataclass
class SkillToolMetadata(ToolMetadata):
    """
    Skill 工具元数据。
    
    额外字段：
    - prompt_template: Prompt 模板
    - available_tools: 可用工具列表
    - llm_config: LLM 配置
    """
    prompt_template: str = ""
    available_tools: list[str] = field(default_factory=list)
    llm_config: dict[str, Any] = field(default_factory=lambda: {"model": "gpt-4", "temperature": 0.3})
    
    def __post_init__(self):
        """确保 type 和 adapter_type 正确"""
        self.type = ToolType.SKILL
        self.adapter_type = AdapterType.SKILL


@dataclass
class FunctionToolMetadata(ToolMetadata):
    """
    Function 工具元数据。
    
    额外字段：
    - function_ref: 函数引用
    """
    function_ref: Callable | None = None
    
    def __post_init__(self):
        """确保 adapter_type 正确"""
        self.adapter_type = AdapterType.FUNCTION


@dataclass
class ToolContext:
    """工具调用上下文（完整版）"""
    # 身份信息
    tenant_id: str
    channel_id: str | None = None
    user_id: str | None = None
    tenant_type: str | None = None
    
    # 会话信息
    conversation_id: str | None = None
    thread_id: str | None = None
    session_id: str | None = None
    
    # 审计信息
    request_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    
    # 其他
    language: str = "zh-CN"
    timezone: str = "Asia/Shanghai"
