# Tool Service 最终架构设计

> 版本：6.3 Final  
> 日期：2026-04-02  
> 状态：最终版本（已修复 Metadata 类型系统）

本文档是 Tool Service 的最终架构设计，整合了所有讨论和澄清。

**最新更新（v6.3）**：
1. 引入类型特定的 Metadata 子类（ExternalMCPToolMetadata, InternalMCPToolMetadata, SkillToolMetadata, FunctionToolMetadata）
2. 消除 hasattr 检查，使用 isinstance 类型检查
3. 提升类型安全和代码可维护性

**已知问题（v6.3）**：
1. health_check 实现有误导性（`len(tools) >= 0` 永远为 True）
2. External MCP 工具缓存只在内存里，服务重启后丢失
3. SkillDefinition 和 ToolMetadata 数据结构不一致，多实例部署有问题

**详细修正方案请参考**：`tool_service_architecture_fixes.md`（v6.4）

**Skill 执行边界规范**：`skill_execution_boundaries.md`（v1.0）
- 定义了 Skill 作为工具层概念的五大边界
- 确保 Skill 是受限的、可预测的、可计量的
- 必读文档，所有 Skill 实现必须遵守

**历史更新**：
- v6.2: 修复 InternalMCPAdapter 重复实现问题（委托给 InternalHTTPClient）
- v6.1: 优化权限策略（默认 LOCAL_ONLY + 降级 + 缓存）
- v6.0: 采用按工具类型划分的目录结构（方案 B）
- v5.0: 深度解析 Skill 执行模型和 MCP/HTTP Adapter

**重要说明 - LLM Gateway 使用**：

在 SkillExecutor 中调用 `llm_gateway.get_chat()` 时：
- `scene` 参数应该是**业务语义场景名**（如 "skill_execution"、"claim_reason"、"policy_query"）
- **不要**把 `llm_config` 中的 `model` 字段直接传给 `scene` 参数
- LLM Gateway 的路由层会根据 `scene` 来决定使用哪个模型
- 如果把模型名（如 "gpt-4"）当作 scene 传入，会导致路由层找不到对应策略，最终 fallback 到默认模型

错误示例：
```python
# ❌ 错误：把 model 当 scene 传入
llm = llm_gateway.get_chat([], scene=skill_def.llm_config.get("model", "gpt-4"))
```

正确示例：
```python
# ✅ 正确：使用业务语义场景名
llm = llm_gateway.get_chat([], scene="skill_execution")
```

**架构原则**：
- 按工具类型划分目录（清晰的边界）
- Base 层提供通用能力（代码复用）
- 各类型继承 Base（扩展特定逻辑）
- 统一的对外接口（解耦实现）
- 性能和可用性优先（权限策略优化）
- DRY 原则（委托而非重复实现）
- 类型安全（使用类型系统而非运行时检查）

---

## 一、核心概念

### 1.1 工具类型定义

| 类型 | 定义 | 执行方式 | 示例 |
|------|------|---------|------|
| **Tool** | 确定性函数，原子化操作 | 直接执行代码 | `query_policy_basic(id)` |
| **Skill** | LLM 驱动的复合能力 | LLM 推理 + 调用 Tools | `analyze_policy_risk(id)` |

### 1.2 Adapter 类型定义

| Adapter | 用途 | 对接对象 | 本质 |
|---------|------|---------|------|
| **External MCP Adapter** | 对接外部 MCP Server | 第三方 MCP 服务（天气、日历等） | MCP 协议客户端 |
| **Internal MCP Adapter** | 对接内部微服务 | 内部微服务（Spring Boot 等） | HTTP Client + MCP 协议封装 |
| **Skill Adapter** | 执行 LLM 驱动的 Skill | LLM + Tools | LLM Agent 执行器 |
| **Function Adapter** | 直接调用 Python 函数 | Python 函数 | 函数包装器 |

**关键澄清**：

1. **External MCP Adapter**：
   - 用于对接外部 MCP Server（第三方服务）
   - 使用 MCP 协议通信
   - Token 认证，不透传内部上下文

2. **Internal MCP Adapter**：
   - **本质是 HTTP Adapter 的 MCP 协议封装**
   - 用于调用内部微服务（Spring Boot 等）
   - 透传上下文信息（tenant_id, user_id 等）
   - 使用内部网络，支持服务发现

3. **Skill Adapter**：
   - **Skill 的执行是基于 LLM 的**
   - Skill = Prompt Template + Available Tools + LLM Execution
   - LLM 推理、决策、调用工具、生成结果
   - **重要**：Skill 必须遵守五大边界约束（详见 `skill_execution_boundaries.md`）：
     - 执行边界：禁止嵌套、max_steps ≤ 5、timeout ≤ 30s
     - 治理归属：独立计量、成本提示、指标透传
     - 观测边界：子事件上报、详细日志、Trace 集成
     - 上下文隔离：不继承主 Agent 历史、显式参数传递
     - 降级边界：统一错误结构、支持重试/降级

4. **Function Adapter**：
   - 最简单的工具类型
   - 直接调用 Python 函数

---

## 二、整体架构

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    LangGraph Agent 层                        │
│  - 顶层决策和编排                                            │
│  - 可以调用 Tool 和 Skill                                    │
└────────────────────────┬────────────────────────────────────┘
                         │ 统一的工具调用接口
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Tool Runtime Layer (核心)                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  ToolGateway - 统一的工具网关                         │  │
│  │  - 工具注册表                                         │  │
│  │  - 工具发现（带权限过滤）                             │  │
│  │  - 工具调用（带权限检查）                             │  │
│  │  - 审计日志                                           │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  ToolRouter - 工具路由器                              │  │
│  │  - keyword/vector/llm/hybrid 匹配                    │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  PermissionChecker - 权限检查器                       │  │
│  │  - 本地规则 + 远程检查（用户中心）                    │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┬────────────────┐
        ▼                ▼                ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│External MCP  │  │Internal MCP  │  │    Skill     │  │   Function   │
│   Adapter    │  │   Adapter    │  │   Adapter    │  │   Adapter    │
│              │  │              │  │              │  │              │
│ 对接外部     │  │ 对接内部     │  │ LLM驱动      │  │ Python函数   │
│ MCP Server   │  │ 微服务       │  │ 复合能力     │  │ 直接调用     │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │                 │
       ▼                 ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ 第三方MCP    │  │ Spring Boot  │  │ LLM Agent    │  │ Python Func  │
│ 服务         │  │ 微服务        │  │ + Tools      │  │              │
│ (天气/日历)  │  │ (policy/     │  │              │  │              │
│              │  │  claim/...)  │  │              │  │              │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
```

### 2.2 层次关系

```
Level 1: LangGraph Agent (顶层编排)
           ↓
Level 2: Tool Runtime (ToolGateway + ToolRouter + PermissionChecker)
           ↓
Level 3: Adapters (External MCP / Internal MCP / Skill / Function)
           ↓
Level 4: 实际执行层 (外部服务 / 内部服务 / LLM / 函数)
```

---

## 三、核心模块设计

### 3.1 目录结构

```
core/tool_service/
├── __init__.py                       # 导出统一接口
├── types.py                          # 通用类型定义
├── registry.py                       # ToolGateway（统一入口）
├── router.py                         # ToolRouter（工具匹配）
│
├── base/                             # 基础抽象层（核心）
│   ├── __init__.py
│   ├── adapter.py                    # ToolAdapter 基类
│   ├── validator.py                  # BaseValidator 基类
│   └── permissions.py                # BasePermissionChecker 基类
│
├── external_mcp/                     # 外部 MCP 工具
│   ├── __init__.py
│   ├── adapter.py                    # ExternalMCPAdapter(ToolAdapter)
│   ├── validator.py                  # ExternalMCPValidator(BaseValidator)
│   ├── client.py                     # MCP 客户端封装
│   └── types.py                      # 外部 MCP 特定类型
│
├── internal_mcp/                     # 内部 MCP 工具
│   ├── __init__.py
│   ├── adapter.py                    # InternalMCPAdapter(ToolAdapter)
│   ├── validator.py                  # InternalMCPValidator(BaseValidator)
│   ├── client.py                     # HTTP 客户端封装
│   └── types.py                      # 内部 MCP 特定类型
│
├── skill/                            # Skill 工具
│   ├── __init__.py
│   ├── adapter.py                    # SkillAdapter(ToolAdapter)
│   ├── validator.py                  # SkillValidator(BaseValidator)
│   ├── executor.py                   # LLM Agent 执行器
│   ├── prompt_manager.py             # Prompt 管理
│   └── types.py                      # Skill 特定类型
│
└── function/                         # Function 工具
    ├── __init__.py
    ├── adapter.py                    # FunctionAdapter(ToolAdapter)
    ├── validator.py                  # FunctionValidator(BaseValidator)
    └── types.py                      # Function 特定类型
```

**设计原则**：

1. **按工具类型划分**：每个工具类型是一个独立的"包"
2. **Base 层提供通用能力**：adapter、validator、permissions 的基类
3. **继承实现复用**：各工具类型继承 base，只实现特定逻辑
4. **清晰的边界**：每个类型有自己的 adapter、validator、client、types

### 3.2 Base 层设计

#### 3.2.1 Base Adapter

```python
# core/tool_service/base/adapter.py
from abc import ABC, abstractmethod
from typing import Any, Dict, List
from ..types import ToolMetadata, ToolContext


class ToolAdapter(ABC):
    """
    工具适配器基类。
    
    提供通用能力：
    - 工具加载
    - 工具验证
    - 工具调用
    - 生命周期管理
    
    子类只需实现抽象方法即可。
    """
    
    @abstractmethod
    async def load_tools(self) -> List[ToolMetadata]:
        """加载工具列表"""
        pass
    
    @abstractmethod
    async def validate_tool(self, metadata: ToolMetadata) -> tuple[bool, list[str]]:
        """验证工具"""
        pass
    
    @abstractmethod
    async def invoke_tool(
        self,
        metadata: ToolMetadata,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Any:
        """调用工具"""
        pass
    
    @abstractmethod
    def get_adapter_type(self) -> str:
        """获取适配器类型"""
        pass
    
    # 通用方法（子类可以直接使用）
    async def health_check(self) -> bool:
        """健康检查（通用实现）"""
        try:
            tools = await self.load_tools()
            return len(tools) >= 0
        except Exception:
            return False
    
    async def close(self):
        """关闭资源（子类可以覆盖）"""
        pass
```

#### 3.2.2 Base Validator

```python
# core/tool_service/base/validator.py
from typing import List, Tuple
from ..types import ToolMetadata


class BaseValidator:
    """
    工具验证器基类。
    
    提供通用验证逻辑，子类只需实现特定验证。
    
    验证流程：
    1. 通用验证（基类实现）- 90% 的逻辑
    2. 特定验证（子类实现）- 10% 的逻辑
    """
    
    async def validate(self, metadata: ToolMetadata) -> Tuple[bool, List[str]]:
        """
        完整验证流程。
        
        1. 通用验证（基类实现）
        2. 特定验证（子类实现）
        """
        errors = []
        
        # 1. 通用验证
        common_errors = self._validate_common(metadata)
        errors.extend(common_errors)
        
        # 2. 特定验证（子类实现）
        specific_errors = await self._validate_specific(metadata)
        errors.extend(specific_errors)
        
        return (len(errors) == 0, errors)
    
    def _validate_common(self, metadata: ToolMetadata) -> List[str]:
        """通用验证逻辑（所有工具都需要）"""
        errors = []
        
        if not metadata.name:
            errors.append("工具名称不能为空")
        
        if not metadata.description:
            errors.append("工具描述不能为空")
        
        if not metadata.input_schema:
            errors.append("工具必须定义 input_schema")
        
        # 验证 input_schema 格式
        if metadata.input_schema:
            if not isinstance(metadata.input_schema, dict):
                errors.append("input_schema 必须是字典")
            elif "type" not in metadata.input_schema:
                errors.append("input_schema 必须包含 type 字段")
        
        return errors
    
    async def _validate_specific(self, metadata: ToolMetadata) -> List[str]:
        """
        特定验证逻辑（子类覆盖）。
        
        子类只需实现这个方法，添加特定的验证逻辑。
        """
        return []
```

#### 3.2.3 Base Permissions

```python
# core/tool_service/base/permissions.py
from typing import Tuple
from ..types import ToolMetadata, ToolContext, PermissionStrategy


class BasePermissionChecker:
    """
    权限检查器基类。
    
    提供通用权限检查逻辑：
    - 本地白名单检查
    - 远程用户中心检查（带缓存和降级）
    - 多种策略支持
    
    生产优化：
    - 默认策略为 LOCAL_ONLY（性能优先）
    - 远程检查失败时降级到本地规则（可用性优先）
    - 权限结果缓存（减少远程调用）
    """
    
    def __init__(
        self,
        user_center_client=None,
        cache_ttl: int = 300,  # 缓存 5 分钟
        enable_fallback: bool = True,  # 启用降级
    ):
        self.user_center_client = user_center_client
        self.cache_ttl = cache_ttl
        self.enable_fallback = enable_fallback
        self._cache: Dict[str, Tuple[bool, str, float]] = {}  # {cache_key: (result, msg, timestamp)}
    
    async def check_permission(
        self,
        metadata: ToolMetadata,
        context: ToolContext,
    ) -> Tuple[bool, str]:
        """
        检查权限。
        
        根据 metadata.permission_strategy 选择策略：
        - LOCAL_ONLY: 仅本地白名单（默认，性能最优）
        - REMOTE_ONLY: 仅用户中心（敏感工具）
        - LOCAL_AND_REMOTE: 双重检查（最严格）
        - LOCAL_OR_REMOTE: 任一通过（最宽松）
        
        生产优化：
        - 远程检查失败时，如果启用降级，会 fallback 到本地规则
        - 远程检查结果会缓存，减少 HTTP 调用
        """
        strategy = metadata.permission_strategy
        
        if strategy == PermissionStrategy.LOCAL_ONLY:
            return await self._check_local(metadata, context)
        
        elif strategy == PermissionStrategy.REMOTE_ONLY:
            return await self._check_remote_with_fallback(metadata, context)
        
        elif strategy == PermissionStrategy.LOCAL_AND_REMOTE:
            # 先本地检查（快速失败）
            local_ok, local_msg = await self._check_local(metadata, context)
            if not local_ok:
                return False, local_msg
            # 再远程检查（带降级）
            return await self._check_remote_with_fallback(metadata, context)
        
        elif strategy == PermissionStrategy.LOCAL_OR_REMOTE:
            # 先本地检查（快速通过）
            local_ok, _ = await self._check_local(metadata, context)
            if local_ok:
                return True, "本地权限通过"
            # 本地不通过，尝试远程（带降级）
            return await self._check_remote_with_fallback(metadata, context)
        
        return False, "未知的权限策略"
    
    async def _check_local(
        self,
        metadata: ToolMetadata,
        context: ToolContext,
    ) -> Tuple[bool, str]:
        """本地白名单检查（通用逻辑）"""
        # 如果没有配置任何白名单，默认允许
        has_restrictions = (
            metadata.allowed_tenants or
            metadata.allowed_channels or
            metadata.allowed_users or
            metadata.allowed_tenant_types
        )
        
        if not has_restrictions:
            return True, "本地无限制，默认允许"
        
        # 检查 tenant_id
        if metadata.allowed_tenants:
            if context.tenant_id not in metadata.allowed_tenants:
                return False, f"租户 {context.tenant_id} 无权限"
        
        # 检查 channel_id
        if metadata.allowed_channels:
            if context.channel_id not in metadata.allowed_channels:
                return False, f"渠道 {context.channel_id} 无权限"
        
        # 检查 user_id
        if metadata.allowed_users:
            if context.user_id not in metadata.allowed_users:
                return False, f"用户 {context.user_id} 无权限"
        
        # 检查 tenant_type
        if metadata.allowed_tenant_types:
            if context.tenant_type not in metadata.allowed_tenant_types:
                return False, f"租户类型 {context.tenant_type} 无权限"
        
        return True, "本地权限检查通过"
    
    async def _check_remote_with_fallback(
        self,
        metadata: ToolMetadata,
        context: ToolContext,
    ) -> Tuple[bool, str]:
        """
        远程用户中心检查（带缓存和降级）。
        
        优化策略：
        1. 先查缓存
        2. 缓存未命中，调用远程
        3. 远程失败，降级到本地规则（如果启用）
        """
        # 1. 检查缓存
        cache_key = self._get_cache_key(metadata.name, context)
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        # 2. 调用远程
        remote_ok, remote_msg = await self._check_remote(metadata, context)
        
        # 3. 缓存结果（只缓存成功的结果）
        if remote_ok:
            self._put_to_cache(cache_key, (remote_ok, remote_msg))
        
        # 4. 如果远程失败且启用降级，fallback 到本地规则
        if not remote_ok and self.enable_fallback:
            logger.warning(
                "remote_check_failed_fallback_to_local",
                tool_name=metadata.name,
                tenant_id=context.tenant_id,
                remote_msg=remote_msg,
            )
            
            local_ok, local_msg = await self._check_local(metadata, context)
            if local_ok:
                return True, f"远程检查失败，降级到本地规则通过: {local_msg}"
            else:
                return False, f"远程检查失败且本地规则也不通过: {remote_msg}"
        
        return remote_ok, remote_msg
    
    async def _check_remote(
        self,
        metadata: ToolMetadata,
        context: ToolContext,
    ) -> Tuple[bool, str]:
        """远程用户中心检查（原始逻辑）"""
        if not self.user_center_client:
            logger.warning("user_center_client_not_configured")
            return True, "用户中心未配置，跳过远程检查"
        
        try:
            has_permission = await self.user_center_client.check_tool_permission(
                tool_name=metadata.name,
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                channel_id=context.channel_id,
                tenant_type=context.tenant_type,
            )
            
            if has_permission:
                return True, "用户中心权限检查通过"
            else:
                return False, "用户中心权限检查失败"
        
        except Exception as e:
            logger.error(
                "user_center_check_exception",
                tool_name=metadata.name,
                tenant_id=context.tenant_id,
                error=str(e),
            )
            # 异常时返回失败，由 _check_remote_with_fallback 处理降级
            return False, f"用户中心检查异常: {str(e)}"
    
    def _get_cache_key(self, tool_name: str, context: ToolContext) -> str:
        """生成缓存 key"""
        return f"perm:{tool_name}:{context.tenant_id}:{context.user_id}:{context.channel_id}"
    
    def _get_from_cache(self, cache_key: str) -> Tuple[bool, str] | None:
        """从缓存获取"""
        import time
        
        if cache_key not in self._cache:
            return None
        
        result, msg, timestamp = self._cache[cache_key]
        
        # 检查是否过期
        if time.time() - timestamp > self.cache_ttl:
            del self._cache[cache_key]
            return None
        
        return (result, msg)
    
    def _put_to_cache(self, cache_key: str, value: Tuple[bool, str]):
        """放入缓存"""
        import time
        self._cache[cache_key] = (value[0], value[1], time.time())
    
    def clear_cache(self):
        """清空缓存（用于测试或手动刷新）"""
        self._cache.clear()
```

### 3.3 通用类型定义

```python
# core/tool_service/types.py
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
```

---

## 四、Adapter 详细设计

### 4.1 External MCP Adapter

**用途**：对接外部 MCP Server（如天气服务、日历服务等第三方服务）

**继承关系**：`ExternalMCPAdapter(ToolAdapter)` + `ExternalMCPValidator(BaseValidator)`

```python
# core/tool_service/external_mcp/adapter.py
from __future__ import annotations
from typing import Any, Dict, List
import httpx
from shared.logging.logger import get_logger
from ..base.adapter import ToolAdapter
from ..types import ToolMetadata, ToolContext, ToolType, AdapterType
from .client import ExternalMCPClient

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
        errors = []
        
        if metadata.name not in self._tools_cache:
            errors.append(f"工具未在外部 MCP Server 中找到: {metadata.name}")
        
        return (len(errors) == 0, errors)
    
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
```


### 4.2 Internal MCP Adapter

**用途**：对接内部微服务（Spring Boot 等），本质是 HTTP Adapter 的 MCP 协议封装

**继承关系**：`InternalMCPAdapter(ToolAdapter)` + `InternalMCPValidator(BaseValidator)`

```python
# core/tool_service/internal_mcp/adapter.py
from __future__ import annotations
from typing import Any, Dict, List
import httpx
from shared.logging.logger import get_logger
from ..base.adapter import ToolAdapter
from ..types import ToolMetadata, ToolContext, ToolType, AdapterType
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
```
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
        await self._client.aclose()


# core/tool_service/internal_mcp/validator.py
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


# core/tool_service/internal_mcp/client.py
import httpx
from typing import Any, Dict
from ..types import ToolContext


class InternalHTTPClient:
    """
    内部 HTTP 客户端封装。
    
    职责：
    - 封装 HTTP 调用逻辑
    - 透传上下文信息（tenant_id, user_id 等）
    - 统一错误处理
    - 支持多种 HTTP 方法
    
    被 InternalMCPAdapter 使用（代码复用）。
    """
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=30)
    
    async def call(
        self,
        endpoint: str,
        method: str,
        data: Dict[str, Any],
        context: ToolContext,
    ) -> Any:
        """
        调用内部服务（透传上下文）。
        
        Args:
            endpoint: API 端点（相对路径）
            method: HTTP 方法（GET/POST/PUT/DELETE）
            data: 请求数据
            context: 工具上下文（用于透传）
        
        Returns:
            响应 JSON 数据
        
        Raises:
            httpx.HTTPStatusError: HTTP 错误
            ValueError: 不支持的 HTTP 方法
        """
        url = f"{self.base_url}{endpoint}"
        
        # 透传上下文信息
        headers = {
            "Content-Type": "application/json",
            "X-Tenant-ID": context.tenant_id,
            "X-User-ID": context.user_id or "",
            "X-Channel-ID": context.channel_id or "",
            "X-Request-ID": context.request_id or "",
            "X-Conversation-ID": context.conversation_id or "",
        }
        
        # 根据 HTTP 方法调用
        if method == "GET":
            response = await self._client.get(url, params=data, headers=headers)
        elif method == "POST":
            response = await self._client.post(url, json=data, headers=headers)
        elif method == "PUT":
            response = await self._client.put(url, json=data, headers=headers)
        elif method == "DELETE":
            response = await self._client.delete(url, params=data, headers=headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        """关闭客户端"""
        await self._client.aclose()
```

### 4.3 Skill Adapter

**用途**：执行 LLM 驱动的 Skill（Prompt + Tools + LLM）

**继承关系**：`SkillAdapter(ToolAdapter)` + `SkillValidator(BaseValidator)` + `SkillExecutor`

**核心理解**：
- **Skill 的执行是基于 LLM 的**
- Skill 本质是提供了 Prompt + 一部分内部的接口调用，然后交给 LLM 执行得到结果
- LLM 负责推理、决策调用哪些工具、综合信息生成结果

**执行流程**：
```
1. 用户调用 Skill
   ↓
2. SkillAdapter 渲染 prompt 模板
   ↓
3. 从 tool_gateway 获取可用工具列表
   ↓
4. 创建 LLM Agent（带指定工具）
   ↓
5. LLM Agent 执行：
   - LLM 读取 prompt，理解任务
   - LLM 决策调用哪些工具（动态推理）
   - 调用 tool_gateway.invoke() 执行工具
   - LLM 综合信息，生成结果
   ↓
6. 返回结果
```

```python
# core/tool_service/skill/adapter.py
from __future__ import annotations
from typing import Any, Dict, List
from dataclasses import dataclass, field
from shared.logging.logger import get_logger
from ..base.adapter import ToolAdapter
from ..types import ToolMetadata, ToolContext, ToolType, AdapterType
from .executor import SkillExecutor

logger = get_logger(__name__)


@dataclass
class SkillDefinition:
    """
    Skill 定义。
    
    Skill = Prompt Template + Available Tools + LLM Execution
    """
    name: str
    description: str
    prompt_template: str              # Prompt 模板
    available_tools: List[str]        # 可用工具列表
    llm_config: dict = field(default_factory=lambda: {"model": "gpt-4", "temperature": 0.3})
    input_schema: dict = field(default_factory=dict)


class SkillAdapter(ToolAdapter):
    """
    Skill 适配器。
    
    Skill 是基于 LLM 的复合能力：
    - Prompt 模板：定义任务
    - Available Tools：可调用的工具
    - LLM Execution：由 LLM 推理和执行
    """
    
    def __init__(self, domain: str, tool_gateway):
        """
        Args:
            domain: 域名
            tool_gateway: 工具网关（用于获取可用工具）
        """
        self.domain = domain
        self.tool_gateway = tool_gateway
        self.executor = SkillExecutor(tool_gateway)
        self._skills: Dict[str, SkillDefinition] = {}
    
    def register_skill(self, skill_def: SkillDefinition):
        """注册一个 Skill"""
        self._skills[skill_def.name] = skill_def
        logger.info(
            "skill_registered",
            name=skill_def.name,
            domain=self.domain,
            tool_count=len(skill_def.available_tools),
        )
    
    async def load_tools(self) -> List[ToolMetadata]:
        """加载所有已注册的 Skill"""
        tools = []
        
        for name, skill_def in self._skills.items():
            metadata = SkillToolMetadata(
                name=name,
                description=skill_def.description,
                category=self.domain,
                input_schema=skill_def.input_schema,
                source_domain=self.domain,
                tags=["skill", "llm", self.domain],
                # Skill 特定字段
                prompt_template=skill_def.prompt_template,
                available_tools=skill_def.available_tools,
                llm_config=skill_def.llm_config,
            )
            tools.append(metadata)
        
        logger.info(
            "skill_tools_loaded",
            domain=self.domain,
            count=len(tools),
        )
        
        return tools
    
    async def validate_tool(self, metadata: ToolMetadata) -> tuple[bool, list[str]]:
        """验证 Skill（使用 SkillValidator）"""
        from .validator import SkillValidator
        validator = SkillValidator(self.tool_gateway)
        return await validator.validate(metadata)
    
    async def invoke_tool(
        self,
        metadata: ToolMetadata,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Any:
        """执行 Skill（通过 SkillExecutor）"""
        skill_def = self._skills.get(metadata.name)
        if not skill_def:
            raise ValueError(f"Skill not found: {metadata.name}")
        
        return await self.executor.execute(skill_def, arguments, context)
    
    def get_adapter_type(self) -> str:
        return AdapterType.SKILL.value


# core/tool_service/skill/validator.py
from ..base.validator import BaseValidator
from ..types import SkillToolMetadata


class SkillValidator(BaseValidator):
    """
    Skill 验证器。
    
    继承 BaseValidator，只需实现特定验证逻辑。
    """
    
    def __init__(self, tool_gateway):
        self.tool_gateway = tool_gateway
    
    async def _validate_specific(self, metadata: SkillToolMetadata) -> list[str]:
        """Skill 特定验证"""
        errors = []
        
        # 类型检查
        if not isinstance(metadata, SkillToolMetadata):
            errors.append(f"Skill 工具必须使用 SkillToolMetadata，当前类型: {type(metadata).__name__}")
            return errors  # 类型错误，后续检查无意义
        
        # 检查 prompt_template
        if not metadata.prompt_template:
            errors.append("Skill 必须定义 prompt_template")
        
        # 检查 available_tools
        if not metadata.available_tools:
            errors.append("Skill 必须指定 available_tools")
        else:
            # 验证工具是否存在
            all_tool_names = {t["name"] for t in self.tool_gateway.list_tools()}
            for tool_name in metadata.available_tools:
                if tool_name not in all_tool_names:
                    errors.append(f"Skill 引用的工具不存在: {tool_name}")
        
        # 检查 llm_config
        if not metadata.llm_config:
            errors.append("Skill 必须配置 llm_config")
        elif "model" not in metadata.llm_config:
            errors.append("Skill 的 llm_config 必须包含 model 字段")
        
        return errors


# core/tool_service/skill/executor.py
from langgraph.prebuilt import create_react_agent
from core.ai_core.llm.client import llm_gateway
from shared.logging.logger import get_logger

logger = get_logger(__name__)


class SkillExecutor:
    """
    Skill 执行器（LLM Agent）。
    
    负责执行 Skill 的核心逻辑：
    1. 渲染 prompt 模板
    2. 获取可用工具
    3. 创建 LLM Agent
    4. 执行 Agent
    5. 返回结果
    """
    
    def __init__(self, tool_gateway):
        self.tool_gateway = tool_gateway
    
    async def execute(self, skill_def, arguments, context):
        """执行 Skill"""
        # 1. 渲染 prompt 模板
        prompt = self._render_prompt(skill_def.prompt_template, arguments)
        
        # 2. 获取可用工具（从 tool_gateway）
        tool_functions = []
        for tool_name in skill_def.available_tools:
            tool_entry = self.tool_gateway._tools.get(tool_name)
            if tool_entry:
                tool_functions.append(self._wrap_tool_for_agent(tool_entry, context))
        
        if not tool_functions:
            raise ValueError(f"No available tools for skill: {skill_def.name}")
        
        # 3. 创建 LLM Agent
        # 注意：scene 参数应该是业务语义场景名（如 "skill_execution"），不是模型名
        # llm_config 中的 model 配置应该在 LLM Gateway 的路由层根据 scene 来决定使用哪个模型
        llm = llm_gateway.get_chat([], scene="skill_execution")
        
        agent = create_react_agent(
            model=llm,
            tools=tool_functions,
        )
        
        # 4. 执行 Agent
        logger.info(
            "skill_executing",
            skill_name=skill_def.name,
            tool_count=len(tool_functions),
            tenant_id=context.tenant_id,
        )
        
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": prompt}]
        })
        
        # 5. 提取结果
        final_message = result["messages"][-1]
        
        return {
            "skill": skill_def.name,
            "result": final_message.content,
            "tool_calls": len([m for m in result["messages"] if hasattr(m, "tool_calls")]),
        }
    
    def _render_prompt(self, template: str, arguments: dict) -> str:
        """渲染 prompt 模板"""
        try:
            return template.format(**arguments)
        except KeyError as e:
            raise ValueError(f"Prompt template missing argument: {e}")
    
    def _wrap_tool_for_agent(self, tool_entry, context):
        """将工具包装成 LangGraph Agent 可用的格式"""
        from langchain_core.tools import tool as langchain_tool
        
        async def wrapped_func(**kwargs):
            return await self.tool_gateway.invoke(
                tool_name=tool_entry.metadata.name,
                arguments=kwargs,
                context=context,
            )
        
        wrapped_func.__name__ = tool_entry.metadata.name
        wrapped_func.__doc__ = tool_entry.metadata.description
        
        return langchain_tool(wrapped_func)
```

### 4.4 Function Adapter

**用途**：直接调用 Python 函数（最简单的工具类型）

**继承关系**：`FunctionAdapter(ToolAdapter)` + `FunctionValidator(BaseValidator)`

```python
# core/tool_service/function/adapter.py
from __future__ import annotations
from typing import Any, Dict, List, Callable
import inspect
import asyncio
from shared.logging.logger import get_logger
from ..base.adapter import ToolAdapter
from ..types import ToolMetadata, ToolContext, ToolType, AdapterType

logger = get_logger(__name__)


class FunctionAdapter(ToolAdapter):
    """
    Function 适配器。
    
    用于直接调用 Python 函数（最简单的工具类型）。
    """
    
    def __init__(self, domain: str = "common"):
        self.domain = domain
        self._functions: Dict[str, Callable] = {}
        self._metadata_cache: Dict[str, ToolMetadata] = {}
    
    def register_function(
        self,
        func: Callable,
        name: str | None = None,
        description: str | None = None,
        category: str | None = None,
    ):
        """注册一个 Python 函数作为工具"""
        tool_name = name or func.__name__
        tool_desc = description or (func.__doc__ or "").strip()
        tool_category = category or self.domain
        
        self._functions[tool_name] = func
        
        # 生成元数据
        sig = inspect.signature(func)
        input_schema = self._generate_schema_from_signature(sig)
        
        metadata = FunctionToolMetadata(
            name=tool_name,
            description=tool_desc,
            type=ToolType.TOOL,
            category=tool_category,
            input_schema=input_schema,
            source_module=func.__module__,
            source_domain=self.domain,
            tags=["function", tool_category],
            # Function 特定字段
            function_ref=func,
        )
        
        self._metadata_cache[tool_name] = metadata
    
    async def load_tools(self) -> List[FunctionToolMetadata]:
        """加载所有已注册的函数工具"""
        return list(self._metadata_cache.values())
    
    def _generate_schema_from_signature(self, sig: inspect.Signature) -> dict:
        """从函数签名生成 JSON Schema"""
        properties = {}
        required = []
        
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "args", "kwargs"):
                continue
            
            param_type = "string"
            if param.annotation != inspect.Parameter.empty:
                if param.annotation == int:
                    param_type = "integer"
                elif param.annotation == float:
                    param_type = "number"
                elif param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation == dict:
                    param_type = "object"
                elif param.annotation == list:
                    param_type = "array"
            
            properties[param_name] = {"type": param_type}
            
            if param.default == inspect.Parameter.empty:
                required.append(param_name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }
    
    async def validate_tool(self, metadata: ToolMetadata) -> tuple[bool, list[str]]:
        """验证函数工具"""
        errors = []
        
        if metadata.name not in self._functions:
            errors.append(f"函数未注册: {metadata.name}")
        
        return (len(errors) == 0, errors)
    
    async def invoke_tool(
        self,
        metadata: ToolMetadata,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Any:
        """执行函数工具"""
        func = self._functions.get(metadata.name)
        if not func:
            raise ValueError(f"Function not found: {metadata.name}")
        
        # 调用函数
        result = func(**arguments)
        
        # 处理异步
        if asyncio.iscoroutine(result):
            result = await result
        
        return result
    
    def get_adapter_type(self) -> str:
        return AdapterType.FUNCTION.value
```


---

### 4.5 目录结构的优势

采用按工具类型划分 + Base 继承的架构，带来以下优势：

#### 1. 清晰的边界

```
每个工具类型都是一个独立的"包"：
- external_mcp/  → 外部 MCP 相关的所有内容
- internal_mcp/  → 内部 MCP 相关的所有内容
- skill/         → Skill 相关的所有内容
- function/      → Function 相关的所有内容
```

**好处**：
- 职责清晰，易于理解
- 修改某个类型不影响其他类型
- 团队可以按类型分工

#### 2. 代码复用（通过继承）

```python
# base/ 提供通用能力
BaseValidator._validate_common()  # 90% 的验证逻辑

# 各类型只需实现特定逻辑
ExternalMCPValidator._validate_specific()  # 10% 的特定逻辑
InternalMCPValidator._validate_specific()  # 10% 的特定逻辑
SkillValidator._validate_specific()        # 10% 的特定逻辑
```

**好处**：
- 避免代码重复
- 通用逻辑统一维护
- 特定逻辑独立扩展

#### 3. 易于扩展

```
新增 gRPC 工具类型：
core/tool_service/grpc/
├── __init__.py
├── adapter.py          # 继承 ToolAdapter
├── validator.py        # 继承 BaseValidator
├── client.py           # gRPC 客户端
└── types.py            # gRPC 特定类型
```

**好处**：
- 新增类型只需创建一个目录
- 继承 base 即可复用通用能力
- 不影响现有类型

#### 4. 独立的特定逻辑

```
skill/ 目录包含 Skill 特有的模块：
- executor.py         # LLM Agent 执行器
- prompt_manager.py   # Prompt 管理
- types.py            # Skill 特定类型（SkillDefinition）
```

**好处**：
- 特定逻辑集中管理
- 不污染其他类型
- 易于测试和维护

#### 5. 统一的对外接口

```python
# 业务层只看到统一接口
from core.tool_service import tool_gateway

# 不关心底层是哪种类型
await tool_gateway.invoke("query_policy_basic", {...})  # Internal MCP
await tool_gateway.invoke("analyze_policy_risk", {...})  # Skill
await tool_gateway.invoke("weather:get_forecast", {...})  # External MCP
```

**好处**：
- 业务层解耦
- 底层实现可替换
- 易于测试（mock）

---

## 五、完整的使用示例

### 5.1 注册所有类型的工具

```python
# app/gateway/lifespan.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from core.tool_service.registry import tool_gateway
from core.tool_service.router import init_tool_router
from core.tool_service.adapters.external_mcp_adapter import ExternalMCPAdapter
from core.tool_service.adapters.internal_mcp_adapter import InternalMCPAdapter
from core.tool_service.adapters.skill_adapter import SkillAdapter, SkillDefinition
from core.tool_service.adapters.function_adapter import FunctionAdapter
from shared.config.settings import settings
from shared.logging.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("agent_platform_starting")
    
    # ========== 1. 注册 External MCP 工具（外部服务）==========
    if settings.weather_mcp_endpoint:
        weather_adapter = ExternalMCPAdapter(
            name="weather",
            endpoint=settings.weather_mcp_endpoint,
            token=settings.weather_mcp_token,
        )
        tool_gateway.register_adapter(weather_adapter)
        await tool_gateway.load_tools_from_adapter(weather_adapter)
    
    # ========== 2. 注册 Internal MCP 工具（内部微服务）==========
    # Policy Service
    policy_adapter = InternalMCPAdapter(
        domain="policy",
        service_name="policy-service",
        base_url="http://policy-service",
    )
    
    policy_adapter.register_tool(
        name="query_policy_basic",
        description="查询保单基本信息",
        endpoint="/api/v1/policies/{policy_id}/basic",
        method="GET",
        input_schema={
            "type": "object",
            "properties": {
                "policy_id": {"type": "string"},
            },
            "required": ["policy_id"],
        },
    )
    
    policy_adapter.register_tool(
        name="list_policies_by_company",
        description="查询企业的保单列表",
        endpoint="/api/v1/companies/{company_id}/policies",
        method="GET",
        input_schema={
            "type": "object",
            "properties": {
                "company_id": {"type": "string"},
                "status": {"type": "string"},
            },
            "required": ["company_id"],
        },
    )
    
    tool_gateway.register_adapter(policy_adapter)
    await tool_gateway.load_tools_from_adapter(policy_adapter)
    
    # Claim Service
    claim_adapter = InternalMCPAdapter(
        domain="claim",
        service_name="claim-service",
        base_url="http://claim-service",
    )
    
    claim_adapter.register_tool(
        name="query_claim_status",
        description="查询理赔进度",
        endpoint="/api/v1/claims/{claim_id}/status",
        method="GET",
    )
    
    tool_gateway.register_adapter(claim_adapter)
    await tool_gateway.load_tools_from_adapter(claim_adapter)
    
    # ========== 3. 注册 Skill 工具（LLM 驱动）==========
    policy_skill_adapter = SkillAdapter(domain="policy", tool_gateway=tool_gateway)
    
    # Skill 1: 分析保单风险
    analyze_risk_skill = SkillDefinition(
        name="analyze_policy_risk",
        description="分析保单的风险等级（低/中/高）",
        prompt_template="""
你是保险风险分析专家。请分析保单 {policy_id} 的风险等级。

分析步骤：
1. 查询保单基本信息
2. 查询历史理赔记录
3. 综合评估风险等级

可用工具：
- query_policy_basic: 查询保单信息
- list_claims_by_policy: 查询理赔记录

请给出风险等级（低/中/高）和详细理由。
        """,
        available_tools=[
            "query_policy_basic",
            "list_claims_by_policy",
        ],
        llm_config={"model": "gpt-4", "temperature": 0.3},
        input_schema={
            "type": "object",
            "properties": {
                "policy_id": {"type": "string"},
            },
            "required": ["policy_id"],
        },
    )
    
    policy_skill_adapter.register_skill(analyze_risk_skill)
    
    tool_gateway.register_adapter(policy_skill_adapter)
    await tool_gateway.load_tools_from_adapter(policy_skill_adapter)
    
    # ========== 4. 注册 Function 工具（Python 函数）==========
    function_adapter = FunctionAdapter(domain="common")
    
    def calculate_age(birth_year: int) -> dict:
        """根据出生年份计算年龄"""
        from datetime import datetime
        current_year = datetime.now().year
        age = current_year - birth_year
        return {"age": age}
    
    function_adapter.register_function(
        func=calculate_age,
        name="calculate_age",
        description="根据出生年份计算年龄",
        category="common",
    )
    
    tool_gateway.register_adapter(function_adapter)
    await tool_gateway.load_tools_from_adapter(function_adapter)
    
    # ========== 5. 初始化工具路由器 ==========
    init_tool_router(tool_gateway)
    
    # ========== 6. 统计工具数量 ==========
    all_tools = tool_gateway.list_tools()
    
    stats = {
        "total": len(all_tools),
        "by_type": {
            "tool": sum(1 for t in all_tools if t["type"] == "tool"),
            "skill": sum(1 for t in all_tools if t["type"] == "skill"),
        },
        "by_adapter": {
            "external_mcp": sum(1 for t in all_tools if t["adapter"] == "external_mcp"),
            "internal_mcp": sum(1 for t in all_tools if t["adapter"] == "internal_mcp"),
            "skill": sum(1 for t in all_tools if t["adapter"] == "skill"),
            "function": sum(1 for t in all_tools if t["adapter"] == "function"),
        },
    }
    
    logger.info("all_tools_registered", **stats)
    
    yield
    
    logger.info("agent_platform_stopped")
```

### 5.2 调用不同类型的工具

```python
from core.tool_service.registry import tool_gateway
from core.tool_service.types import ToolContext

# 创建上下文
context = ToolContext(
    tenant_id="tenant_a",
    user_id="user_123",
    channel_id="web",
    conversation_id="conv_456",
)

# 1. 调用 Internal MCP 工具（查询保单）
result = await tool_gateway.invoke(
    tool_name="query_policy_basic",
    arguments={"policy_id": "P2024001"},
    context=context,
)
# 返回：{"policy_id": "P2024001", "status": "ACTIVE", ...}

# 2. 调用 Skill（分析风险）
result = await tool_gateway.invoke(
    tool_name="analyze_policy_risk",
    arguments={"policy_id": "P2024001"},
    context=context,
)
# 返回：
# {
#     "skill": "analyze_policy_risk",
#     "result": "该保单风险等级为【中】。理由如下：...",
#     "tool_calls": 2
# }

# 3. 调用 External MCP 工具（查询天气）
result = await tool_gateway.invoke(
    tool_name="weather:get_forecast",
    arguments={"location": "Beijing"},
    context=context,
)
# 返回：{"temperature": 15, "condition": "sunny", ...}

# 4. 调用 Function 工具（计算年龄）
result = await tool_gateway.invoke(
    tool_name="calculate_age",
    arguments={"birth_year": 1990},
    context=context,
)
# 返回：{"age": 36}
```

---

## 六、核心概念总结

### 6.1 Tool vs Skill

| 维度 | Tool | Skill |
|------|------|-------|
| **定义** | 确定性函数，原子化操作 | LLM 驱动的复合能力 |
| **执行方式** | 直接执行代码 | LLM 推理 + 调用 Tools |
| **输入** | 结构化参数 | 自然语言 + 结构化参数 |
| **输出** | 确定性结果 | LLM 生成的结果 |
| **复杂度** | 简单 | 复杂 |
| **示例** | `query_policy_basic(id)` | `analyze_policy_risk(id)` |

### 6.2 Adapter 类型

| Adapter | 用途 | 对接对象 | 本质 | 特点 |
|---------|------|---------|------|------|
| **External MCP** | 对接外部 MCP Server | 第三方服务 | MCP 协议客户端 | Token 认证，不透传上下文 |
| **Internal MCP** | 对接内部微服务 | Spring Boot 等 | HTTP Client + MCP 协议封装 | 透传上下文，HTTP + MCP 协议 |
| **Skill** | 执行 LLM 驱动的 Skill | LLM + Tools | LLM Agent 执行器 | Prompt + Tools + LLM |
| **Function** | 直接调用 Python 函数 | Python 函数 | 函数包装器 | 最简单 |

**关键理解**：

1. **External MCP Adapter**：
   - 用于对接外部 MCP Server（第三方服务）
   - 使用 MCP 协议通信

2. **Internal MCP Adapter**：
   - **本质就是 HTTP Adapter 的 MCP 协议封装**
   - 用于调用内部微服务
   - 透传上下文信息

3. **Skill Adapter**：
   - **Skill 的执行是基于 LLM 的**
   - Skill = Prompt + Tools + LLM Execution
   - LLM 负责推理和决策

### 6.3 架构层次

```
Level 1: LangGraph Agent
           ↓ 调用 Tool 和 Skill
Level 2: Tool Runtime (ToolGateway + ToolRouter + PermissionChecker)
           ↓ 委托给 Adapter
Level 3: Adapters (External MCP / Internal MCP / Skill / Function)
           ↓ 执行具体逻辑
Level 4: 实际执行层 (外部服务 / 内部服务 / LLM / 函数)
```

---

## 七、关键设计决策

### 7.1 为什么 Internal MCP Adapter 是 HTTP Adapter 的封装？

**原因**：
1. **内部微服务使用 HTTP 协议**：Spring Boot 服务提供 REST API
2. **MCP 协议是抽象层**：提供统一的工具定义和调用接口
3. **复用 HTTP 能力**：透传上下文、服务发现、负载均衡等

**本质**：
```
Internal MCP Adapter = InternalHTTPClient + MCP Protocol Wrapper
```

**代码复用实现**：
```python
class InternalMCPAdapter(ToolAdapter):
    def __init__(self, domain: str, service_name: str, base_url: str):
        self.client = InternalHTTPClient(base_url)  # 委托给 InternalHTTPClient
        self._tools = {}
    
    async def invoke_tool(self, metadata, arguments, context):
        tool_info = self._tools[metadata.name]
        
        # 委托给 InternalHTTPClient（避免重复实现）
        return await self.client.call(
            endpoint=tool_info["endpoint"],
            method=tool_info["method"],
            data=arguments,
            context=context,  # 透传上下文
        )
```

**为什么要委托而不是重复实现？**

❌ **错误做法（重复实现）**：
```python
class InternalMCPAdapter:
    async def invoke_tool(self, ...):
        # 重复实现 HTTP 调用逻辑
        headers = {
            "X-Tenant-ID": context.tenant_id,
            "X-User-ID": context.user_id,
            ...
        }
        if method == "GET":
            response = await self._client.get(...)
        elif method == "POST":
            response = await self._client.post(...)
        ...
```

**问题**：
- 代码重复（InternalHTTPClient 已经实现了）
- 维护成本高（修改一处要改两处）
- 违背 DRY 原则（Don't Repeat Yourself）

✅ **正确做法（委托）**：
```python
class InternalMCPAdapter:
    async def invoke_tool(self, ...):
        # 委托给 InternalHTTPClient
        return await self.client.call(
            endpoint=tool_info["endpoint"],
            method=tool_info["method"],
            data=arguments,
            context=context,
        )
```

**好处**：
- 代码复用（单一实现）
- 易于维护（修改一处即可）
- 职责清晰（Adapter 负责协议，Client 负责 HTTP）

### 7.2 为什么 Skill 需要单独的 Adapter？

**原因**：
1. **执行方式根本不同**：
   - Tool：直接执行代码（确定性）
   - Skill：LLM 推理 + 动态调用工具（非确定性）

2. **Skill 的本质**：
   - Skill = Prompt Template + Available Tools + LLM Execution
   - Skill 不是简单的 Python 函数
   - Skill 是基于 LLM 的复合能力

3. **执行流程不同**：
   - Tool：`function(args) -> result`
   - Skill：`LLM(prompt, tools) -> reasoning -> tool_calls -> result`

4. **依赖关系不同**：
   - Tool：独立执行，无依赖
   - Skill：依赖其他 Tools，需要 tool_gateway

**执行示例对比**：

```python
# Tool 执行（确定性）
async def query_policy_basic(policy_id: str) -> dict:
    return await db.query(...)  # 直接返回结果

# Skill 执行（LLM 驱动）
async def analyze_policy_risk(policy_id: str) -> dict:
    # 1. 渲染 prompt
    prompt = f"分析保单 {policy_id} 的风险..."
    
    # 2. 创建 LLM Agent（带工具）
    agent = create_react_agent(
        model=llm,
        tools=[query_policy_basic, list_claims, query_credit],
    )
    
    # 3. LLM 执行（推理 + 工具调用）
    result = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    
    # LLM 内部过程：
    # - 理解任务
    # - 决定调用 query_policy_basic(policy_id)
    # - 决定调用 list_claims(policy_id)
    # - 决定调用 query_credit(...)
    # - 综合信息，生成分析报告
    
    return result
```

**本质区别**：
```
Tool  = 函数调用
Skill = LLM 推理 + 多次工具调用 + 结果生成
```

### 7.3 权限策略的设计决策

#### 为什么默认策略是 LOCAL_ONLY？

**问题**：
- 如果默认是 `LOCAL_AND_REMOTE`，每次工具调用都要串行走两层检查
- 远程 HTTP 请求增加延迟（通常 50-200ms）
- 用户中心抖动时，所有工具调用都会失败

**解决方案**：
```python
# 默认策略：LOCAL_ONLY（性能优先）
permission_strategy: PermissionStrategy = PermissionStrategy.LOCAL_ONLY

# 敏感工具才升级策略
sensitive_tool = ToolMetadata(
    name="delete_policy",
    permission_strategy=PermissionStrategy.REMOTE_ONLY,  # 必须用户中心鉴权
)
```

**策略选择指南**：

| 工具类型 | 推荐策略 | 理由 |
|---------|---------|------|
| 查询类工具 | LOCAL_ONLY | 高频调用，性能优先 |
| 普通写入 | LOCAL_ONLY | 本地白名单足够 |
| 敏感操作 | REMOTE_ONLY | 必须用户中心鉴权 |
| 核心资产 | LOCAL_AND_REMOTE | 双重保障 |

#### 为什么需要降级策略？

**问题**：
- 用户中心可能抖动、超时、维护
- 如果直接返回 `False`，所有工具调用都会失败
- 生产环境不可接受

**解决方案**：
```python
# 启用降级（默认）
checker = BasePermissionChecker(
    user_center_client=client,
    enable_fallback=True,  # 远程失败时降级到本地规则
)

# 执行流程：
# 1. 尝试远程检查
# 2. 远程失败 → 降级到本地规则
# 3. 本地规则通过 → 允许（记录日志）
# 4. 本地规则不通过 → 拒绝
```

**降级日志示例**：
```python
logger.warning(
    "remote_check_failed_fallback_to_local",
    tool_name="query_policy_basic",
    tenant_id="tenant_a",
    remote_msg="用户中心超时",
)
```

#### 为什么需要缓存？

**问题**：
- 同一个用户可能短时间内多次调用同一个工具
- 每次都调用用户中心，浪费资源

**解决方案**：
```python
# 缓存 5 分钟
checker = BasePermissionChecker(
    user_center_client=client,
    cache_ttl=300,  # 秒
)

# 缓存 key: perm:{tool_name}:{tenant_id}:{user_id}:{channel_id}
# 只缓存成功的结果（失败的不缓存，避免误拦截）
```

**缓存效果**：
- 第 1 次调用：远程检查（200ms）
- 第 2-N 次调用：缓存命中（<1ms）
- 5 分钟后：缓存过期，重新检查

#### 生产环境最佳实践

```python
# 1. 大部分工具使用默认策略（LOCAL_ONLY）
normal_tool = ToolMetadata(
    name="query_policy_basic",
    # permission_strategy 默认 LOCAL_ONLY
)

# 2. 敏感工具明确指定策略
sensitive_tool = ToolMetadata(
    name="delete_policy",
    permission_strategy=PermissionStrategy.REMOTE_ONLY,
)

# 3. 启用降级和缓存
checker = BasePermissionChecker(
    user_center_client=user_center_client,
    cache_ttl=300,           # 缓存 5 分钟
    enable_fallback=True,    # 启用降级
)

# 4. 监控和告警
# - 监控远程检查失败率
# - 监控降级触发次数
# - 用户中心可用性告警
```

---

### 7.4 为什么需要 ToolRouter？

**原因**：
1. **工具数量多**：可能有几十上百个工具
2. **智能匹配**：根据用户意图自动选择最相关的工具
3. **多种策略**：keyword/vector/llm/hybrid

**价值**：
- 减少 LLM 的工具列表（提高准确率）
- 动态工具选择（根据场景）
- 提升用户体验

---

## 十、关键概念深度解析

### 10.1 Skill 的执行模型

#### Skill 不是简单的函数调用

很多人可能会误解 Skill 是一个封装好的 Python 函数，但实际上：

**❌ 错误理解**：
```python
# Skill 不是这样的
async def analyze_policy_risk(policy_id: str) -> dict:
    policy = await query_policy_basic(policy_id)
    claims = await list_claims(policy_id)
    credit = await query_credit(policy.customer_id)
    
    # 硬编码的逻辑
    if claims > 2:
        risk = "高"
    else:
        risk = "低"
    
    return {"risk": risk}
```

**✅ 正确理解**：
```python
# Skill 是这样的
skill = SkillDefinition(
    name="analyze_policy_risk",
    prompt_template="""
你是保险风险分析专家。请分析保单 {policy_id} 的风险等级。

可用工具：
- query_policy_basic: 查询保单信息
- list_claims: 查询理赔记录
- query_credit: 查询客户信用

请根据实际情况决定调用哪些工具，并给出风险评估。
    """,
    available_tools=["query_policy_basic", "list_claims", "query_credit"],
)

# 执行时：
# 1. LLM 读取 prompt，理解任务
# 2. LLM 决定：先调用 query_policy_basic
# 3. LLM 看到结果，决定：再调用 list_claims
# 4. LLM 看到结果，决定：需要调用 query_credit
# 5. LLM 综合所有信息，生成分析报告
```

#### Skill 执行的完整流程

```
┌─────────────────────────────────────────────────────────┐
│ 1. 用户调用 Skill                                        │
│    tool_gateway.invoke("analyze_policy_risk", {...})    │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ 2. SkillAdapter 接收调用                                 │
│    - 获取 Skill 定义                                     │
│    - 渲染 prompt 模板                                    │
│    - 从 tool_gateway 获取可用工具                        │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ 3. 创建 LLM Agent                                        │
│    agent = create_react_agent(                          │
│        model=llm,                                        │
│        tools=[query_policy_basic, list_claims, ...]     │
│    )                                                     │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ 4. LLM Agent 执行（核心）                                │
│                                                          │
│    LLM 推理循环：                                        │
│    ┌──────────────────────────────────────────┐        │
│    │ a. LLM 读取 prompt 和当前状态            │        │
│    │ b. LLM 决定下一步行动：                  │        │
│    │    - 调用工具？调用哪个？参数是什么？    │        │
│    │    - 还是生成最终答案？                  │        │
│    │ c. 如果调用工具：                        │        │
│    │    - 通过 tool_gateway.invoke() 执行    │        │
│    │    - 获取结果                            │        │
│    │    - 回到步骤 a（继续推理）              │        │
│    │ d. 如果生成答案：                        │        │
│    │    - 结束循环                            │        │
│    └──────────────────────────────────────────┘        │
│                                                          │
│    示例执行轨迹：                                        │
│    - LLM: "我需要先查询保单信息"                         │
│    - Action: query_policy_basic("P001")                 │
│    - Result: {...}                                       │
│    - LLM: "保单状态正常，我需要查理赔记录"               │
│    - Action: list_claims("P001")                         │
│    - Result: [...]                                       │
│    - LLM: "有2次理赔，我需要查客户信用"                  │
│    - Action: query_credit(...)                          │
│    - Result: {...}                                       │
│    - LLM: "综合分析，风险等级为中"                       │
│    - Final Answer: "该保单风险等级为【中】..."           │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ 5. 返回结果                                              │
│    {                                                     │
│      "skill": "analyze_policy_risk",                    │
│      "result": "该保单风险等级为【中】...",              │
│      "tool_calls": 3                                     │
│    }                                                     │
└─────────────────────────────────────────────────────────┘
```

#### Skill vs Tool 的本质区别

| 维度 | Tool | Skill |
|------|------|-------|
| **执行方式** | 直接调用函数 | LLM 推理 + 动态工具调用 |
| **逻辑** | 硬编码 | LLM 动态决策 |
| **灵活性** | 固定流程 | 根据情况调整 |
| **调用次数** | 1 次 | 可能多次（LLM 决定） |
| **结果** | 结构化数据 | 自然语言 + 结构化数据 |
| **适用场景** | 确定性操作 | 需要推理和决策 |

**一句话总结**：
> Tool 是"函数"，Skill 是"带工具的 LLM Agent"。

---

### 10.2 Internal MCP Adapter 的本质

#### 为什么叫 "Internal MCP Adapter"？

很多人可能会困惑：既然是调用内部微服务（HTTP），为什么叫 "MCP Adapter"？

**答案**：Internal MCP Adapter 本质就是 **HTTP Adapter 的 MCP 协议封装**。

#### 架构层次

```
┌─────────────────────────────────────────────────────────┐
│              Internal MCP Adapter                        │
│  ┌───────────────────────────────────────────────────┐  │
│  │  MCP 协议层（统一接口）                           │  │
│  │  - list_tools()                                   │  │
│  │  - invoke(tool, arguments)                        │  │
│  └─────────────────────┬─────────────────────────────┘  │
│                        ↓                                 │
│  ┌───────────────────────────────────────────────────┐  │
│  │  HTTP Client 层（实际执行）                       │  │
│  │  - httpx.AsyncClient                              │  │
│  │  - 透传上下文（tenant_id, user_id, ...）         │  │
│  │  - 服务发现、负载均衡                             │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│         内部微服务（Spring Boot）                        │
│  - policy-service                                        │
│  - claim-service                                         │
│  - customer-service                                      │
└─────────────────────────────────────────────────────────┘
```

#### 为什么要这样设计？

**1. 统一抽象**：
```python
# 对外统一的接口（MCP 协议）
adapter.list_tools()      # 列出所有工具
adapter.invoke(tool, args)  # 调用工具

# 无论是 External MCP 还是 Internal MCP，接口一致
```

**2. 解耦实现**：
```python
# 业务层不关心底层是 HTTP 还是 gRPC
await tool_gateway.invoke("query_policy_basic", {...})

# ToolGateway 委托给 Adapter
# Adapter 内部使用 HTTP Client 调用微服务
```

**3. 灵活替换**：
```python
# 未来可以替换为 gRPC、消息队列等
class InternalGrpcAdapter(ToolAdapter):
    async def invoke_tool(self, ...):
        return await grpc_client.call(...)
```

#### External MCP vs Internal MCP

| 维度 | External MCP Adapter | Internal MCP Adapter |
|------|---------------------|---------------------|
| **对接对象** | 外部 MCP Server（第三方） | 内部微服务（Spring Boot） |
| **协议** | MCP 协议 | HTTP + MCP 协议封装 |
| **认证** | Token 认证 | 内部网络，透传上下文 |
| **上下文** | 不透传（安全考虑） | 透传（tenant_id, user_id 等） |
| **网络** | 外部网络 | 内部网络 |
| **示例** | 天气服务、日历服务 | policy-service, claim-service |

#### 代码对比

**External MCP Adapter**：
```python
# 调用外部 MCP Server
response = await self._client.post(
    f"{self.endpoint}/mcp/invoke",
    headers={"Authorization": f"Bearer {self.token}"},  # Token 认证
    json={
        "tool": tool_name,
        "arguments": arguments,
        # 不透传内部上下文
    },
)
```

**Internal MCP Adapter**：
```python
# 调用内部微服务
response = await self._client.post(
    f"{self.base_url}{endpoint}",
    headers={
        "X-Tenant-ID": context.tenant_id,      # 透传上下文
        "X-User-ID": context.user_id,
        "X-Channel-ID": context.channel_id,
        "X-Request-ID": context.request_id,
    },
    json=arguments,
)
```

**一句话总结**：
> Internal MCP Adapter = HTTP Client + MCP 协议抽象 + 上下文透传

---

### 10.3 架构清晰度总结

#### MCP 的两种用途

```
MCP 协议
    ├── External MCP Adapter
    │   └── 用于对接外部 MCP Server（第三方服务）
    │
    └── Internal MCP Adapter
        └── 用于对接内部微服务（HTTP + MCP 协议封装）
```

#### 完整的工具类型

```
Tool Service
    ├── Tool（确定性工具）
    │   ├── External MCP Adapter → 外部 MCP Server
    │   ├── Internal MCP Adapter → 内部微服务（HTTP）
    │   └── Function Adapter → Python 函数
    │
    └── Skill（LLM 驱动的复合能力）
        └── Skill Adapter → LLM Agent + Tools
```

#### 关键理解

1. **MCP 是协议抽象**：
   - External MCP：真正的 MCP 协议通信
   - Internal MCP：HTTP 通信 + MCP 协议封装

2. **Skill 是 LLM 驱动**：
   - 不是简单的函数
   - 是 Prompt + Tools + LLM Execution

3. **统一对外接口**：
   - 业务层只看到 `tool_gateway.invoke()`
   - 不关心底层是 MCP、HTTP、还是 Function

---

## 十一、未来扩展

### 11.1 工具版本管理

```python
@tool(
    name="query_policy_basic",
    version="2.0.0",
)
async def query_policy_basic_v2(...):
    ...

# 调用时指定版本
await tool_gateway.invoke(
    tool_name="query_policy_basic",
    version="2.0.0",
    arguments={...},
    context=context,
)
```

### 11.2 工具组合（Skill 的扩展）

```python
# Skill 可以调用其他 Skill
composite_skill = SkillDefinition(
    name="comprehensive_policy_analysis",
    prompt_template="...",
    available_tools=[
        "analyze_policy_risk",  # 另一个 Skill
        "query_policy_basic",   # Tool
    ],
)
```

### 11.3 工具市场

```python
# 从工具市场安装工具
await tool_marketplace.install(
    tool_name="sentiment_analysis",
    version="1.0.0",
)

# 自动注册到 tool_gateway
```

---

## 十二、常见问题和最佳实践

### 12.1 架构设计问题（v6.3 已知问题）

本节列出 v6.3 版本中发现的架构问题，详细修正方案请参考 `tool_service_architecture_fixes.md`。

#### 问题 1：health_check 实现有误导性

```python
# ❌ 错误：len(tools) >= 0 永远为 True
async def health_check(self) -> bool:
    try:
        tools = await self.load_tools()
        return len(tools) >= 0
    except Exception:
        return False

# ✅ 正确：应该检查是否有工具
async def health_check(self) -> bool:
    try:
        tools = await self.load_tools()
        return len(tools) > 0  # 至少有一个工具
    except Exception:
        return False
```

**影响**：健康检查无法正确反映服务状态。

**修正**：参考 `tool_service_architecture_fixes.md` 问题 1。

#### 问题 2：External MCP 工具缓存只在内存里

```python
# ❌ 问题：实例级内存缓存，服务重启后丢失
class ExternalMCPAdapter(ToolAdapter):
    def __init__(self, name: str, endpoint: str, token: str):
        self._tools_cache: Dict[str, dict] = {}  # 内存缓存
```

**影响**：
- 服务重启后需要重新加载
- 多实例部署时缓存不一致
- 没有缓存刷新机制

**修正**：
- 开发环境：添加 TTL 和手动刷新
- 生产环境：使用 Redis 共享缓存

详见 `tool_service_architecture_fixes.md` 问题 2。

#### 问题 3：SkillDefinition 和 ToolMetadata 数据结构不一致

```python
# ❌ 问题：两套数据结构，Skill 定义只在 Adapter 实例里
@dataclass
class SkillDefinition:  # 只在 Adapter 里
    name: str
    description: str
    prompt_template: str
    # ...

class SkillAdapter(ToolAdapter):
    def __init__(self, domain: str, tool_gateway):
        self._skills: Dict[str, SkillDefinition] = {}  # 实例级存储
```

**影响**：
- Adapter 实例销毁后定义丢失
- 多实例部署时定义不一致
- 需要手动同步两套数据结构

**修正**：
- 方案 A：统一使用 SkillToolMetadata
- 方案 B：持久化存储（数据库/配置文件）

详见 `tool_service_architecture_fixes.md` 问题 3。

---

### 12.2 LLM Gateway 使用问题

#### 问题：SkillExecutor 中 llm_gateway.get_chat() 的 scene 参数使用错误

**错误示例**：
```python
# ❌ 错误：把 llm_config 中的 model 当作 scene 传入
llm = llm_gateway.get_chat([], scene=skill_def.llm_config.get("model", "gpt-4"))
```

**问题分析**：
- `scene` 参数应该是**业务语义场景名**（如 "skill_execution"、"claim_reason"、"policy_query"）
- 不应该把模型名（如 "gpt-4"、"claude-3"）直接传给 `scene` 参数
- LLM Gateway 的路由层会根据 `scene` 查找对应的路由策略，决定使用哪个模型
- 如果把模型名当作 scene 传入，路由层找不到对应策略，会 fallback 到默认模型
- 这会导致 `llm_config` 中的模型配置完全失效

**正确示例**：
```python
# ✅ 正确：使用业务语义场景名
llm = llm_gateway.get_chat([], scene="skill_execution")
```

**LLM Gateway 的工作原理**：
```python
# LLM Gateway 内部的路由逻辑
scene_to_model_mapping = {
    "skill_execution": "gpt-4",
    "claim_reason": "claude-3-sonnet",
    "policy_query": "gpt-3.5-turbo",
    "tool_select": "gpt-4",
    # ...
}

def get_chat(tools, scene):
    # 根据 scene 查找对应的模型
    model = scene_to_model_mapping.get(scene, "default-model")
    return create_llm_client(model)
```

**最佳实践**：
1. 在 Skill 定义中，`llm_config` 可以保留用于其他配置（如 temperature、max_tokens）
2. 模型选择应该由 LLM Gateway 的路由层统一管理
3. 使用有意义的 scene 名称，反映业务语义
4. 在 LLM Gateway 的配置中维护 scene 到 model 的映射关系

**参考其他正确用法**：
```python
# 在 subagent_planner_provider.py 中
llm = llm_gateway.get_chat([], scene="subagent_planner")

# 在 tools/router.py 中
llm = llm_gateway.get_chat([], scene="tool_select")

# 在 plan_execute.py 中
llm = llm_gateway.get_chat([], scene="plan_execute_step")
llm = llm_gateway.get_chat([], scene="plan_execute_summary")

# 在 memory/extractor.py 中
chat = llm_gateway.get_chat(tools=[], scene="memory_summary")
```

---

## 十三、总结

### 13.1 核心价值

1. **统一抽象**：Tool 和 Skill 统一管理
2. **灵活扩展**：支持多种 Adapter 类型
3. **智能匹配**：ToolRouter 提供多种匹配策略
4. **权限控制**：多维度权限检查
5. **可观测性**：完整的审计日志

### 13.2 架构优势

| 层级 | 职责 | 优势 |
|------|------|------|
| **LangGraph** | 顶层编排 | 专注业务逻辑 |
| **Tool Runtime** | 工具管理 | 统一接口，权限控制 |
| **Adapters** | 适配不同来源 | 解耦，易扩展 |
| **执行层** | 实际执行 | 灵活，可替换 |

### 13.3 一句话总结

> **Tool Service 是 Agent Platform 的"工具网关"，通过统一的 Runtime 和多种 Adapter，管理 Tool（确定性）和 Skill（LLM 驱动）两种类型的工具，支持内部微服务、外部 MCP Server、Python 函数等多种来源，提供智能匹配、权限控制、审计日志等平台级能力。**

---

**文档维护者**：Agent Platform Team  
**最后更新**：2026-04-02  
**版本**：6.3 Final（已修复 LLM Gateway 使用问题）
