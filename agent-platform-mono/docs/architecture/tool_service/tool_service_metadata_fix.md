# Tool Service Metadata 类型系统修复

> 版本：v6.3  
> 日期：2026-04-02  
> 类型：类型系统重构

## 一、问题背景

### 1.1 发现的问题

**问题代码**：
```python
# core/tool_service/internal_mcp/validator.py
async def _validate_specific(self, metadata: ToolMetadata) -> list[str]:
    errors = []
    
    # ❌ 错误：使用 hasattr 检查不存在的字段
    if not hasattr(metadata, 'base_url') or not metadata.base_url:
        errors.append("内部 MCP 工具必须配置 base_url")
    
    if not hasattr(metadata, 'endpoint') or not metadata.endpoint:
        errors.append("内部 MCP 工具必须配置 endpoint")
    
    return errors
```

**问题分析**：

1. **ToolMetadata 是标准 dataclass**：字段是固定的，不应该用 `hasattr` 检查
2. **base_url 和 endpoint 不在 ToolMetadata 定义中**：这些字段是 Internal MCP 特有的
3. **验证逻辑永远会报错**（或永远不报错，取决于字段是否被动态附加）
4. **违背类型安全原则**：动态附加字段会导致类型检查失效

### 1.2 根本原因

**设计缺陷**：试图用一个通用的 `ToolMetadata` 来表示所有类型的工具，但不同类型的工具需要不同的配置信息：

| 工具类型 | 特有字段 |
|---------|---------|
| **External MCP** | `mcp_server_name`, `original_tool_name` |
| **Internal MCP** | `base_url`, `endpoint`, `method`, `service_name` |
| **Skill** | `prompt_template`, `available_tools`, `llm_config` |
| **Function** | `function_ref` |

**当前设计的问题**：
```python
# ❌ 错误：所有类型都用同一个 ToolMetadata
metadata = ToolMetadata(
    name="query_policy_basic",
    description="...",
    type=ToolType.TOOL,
    adapter_type=AdapterType.INTERNAL_MCP,
    # 问题：base_url, endpoint 等字段无处存放
)

# 然后在验证时用 hasattr 检查（错误做法）
if hasattr(metadata, 'base_url'):  # 永远是 False
    ...
```

---

## 二、解决方案

### 2.1 设计原则

**采用类型特定的 Metadata 子类**，而不是在通用类上动态附加字段。

**设计思路**：
```
ToolMetadata (基类)
    ├── ExternalMCPToolMetadata (外部 MCP 特有字段)
    ├── InternalMCPToolMetadata (内部 MCP 特有字段)
    ├── SkillToolMetadata (Skill 特有字段)
    └── FunctionToolMetadata (Function 特有字段)
```

### 2.2 类型定义

```python
# core/tool_service/types.py
from dataclasses import dataclass, field
from typing import Any, Callable
from enum import Enum


@dataclass
class ToolMetadata:
    """
    工具元数据基类。
    
    包含所有工具类型的通用字段。
    不同类型的工具应该使用对应的子类。
    """
    name: str
    description: str
    type: ToolType
    adapter_type: AdapterType
    category: str
    
    # Schema
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    
    # 权限控制
    allowed_tenants: list[str] | None = None
    allowed_channels: list[str] | None = None
    allowed_users: list[str] | None = None
    allowed_tenant_types: list[str] | None = None
    permission_strategy: PermissionStrategy = PermissionStrategy.LOCAL_ONLY
    
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
```

### 2.3 Adapter 使用子类

#### Internal MCP Adapter

```python
# core/tool_service/internal_mcp/adapter.py
from ..types import InternalMCPToolMetadata

class InternalMCPAdapter(ToolAdapter):
    async def load_tools(self) -> List[ToolMetadata]:
        tools = []
        
        for name, tool_info in self._tools.items():
            # ✅ 正确：使用 InternalMCPToolMetadata
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
        
        return tools
```

#### Skill Adapter

```python
# core/tool_service/skill/adapter.py
from ..types import SkillToolMetadata

class SkillAdapter(ToolAdapter):
    async def load_tools(self) -> List[ToolMetadata]:
        tools = []
        
        for name, skill_def in self._skills.items():
            # ✅ 正确：使用 SkillToolMetadata
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
        
        return tools
```

### 2.4 Validator 使用类型检查

#### Internal MCP Validator

```python
# core/tool_service/internal_mcp/validator.py
from ..base.validator import BaseValidator
from ..types import InternalMCPToolMetadata


class InternalMCPValidator(BaseValidator):
    async def _validate_specific(self, metadata: InternalMCPToolMetadata) -> list[str]:
        """内部 MCP 特定验证"""
        errors = []
        
        # ✅ 正确：类型检查
        if not isinstance(metadata, InternalMCPToolMetadata):
            errors.append(f"内部 MCP 工具必须使用 InternalMCPToolMetadata，当前类型: {type(metadata).__name__}")
            return errors  # 类型错误，后续检查无意义
        
        # ✅ 正确：直接访问字段（不用 hasattr）
        if not metadata.base_url:
            errors.append("内部 MCP 工具必须配置 base_url")
        
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
```

#### Skill Validator

```python
# core/tool_service/skill/validator.py
from ..base.validator import BaseValidator
from ..types import SkillToolMetadata


class SkillValidator(BaseValidator):
    def __init__(self, tool_gateway):
        self.tool_gateway = tool_gateway
    
    async def _validate_specific(self, metadata: SkillToolMetadata) -> list[str]:
        """Skill 特定验证"""
        errors = []
        
        # ✅ 正确：类型检查
        if not isinstance(metadata, SkillToolMetadata):
            errors.append(f"Skill 工具必须使用 SkillToolMetadata，当前类型: {type(metadata).__name__}")
            return errors
        
        # ✅ 正确：直接访问字段
        if not metadata.prompt_template:
            errors.append("Skill 必须定义 prompt_template")
        
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
```

---

## 三、对比分析

### 3.1 代码对比

#### 错误做法（v6.2）

```python
# ❌ 错误：使用通用 ToolMetadata + hasattr
metadata = ToolMetadata(
    name="query_policy_basic",
    description="...",
    type=ToolType.TOOL,
    adapter_type=AdapterType.INTERNAL_MCP,
    # 问题：base_url, endpoint 无处存放
)

# 验证时用 hasattr（错误）
if not hasattr(metadata, 'base_url') or not metadata.base_url:
    errors.append("必须配置 base_url")
```

**问题**：
- 字段无处存放
- hasattr 检查不可靠
- 类型检查失效
- IDE 无法提供代码补全

#### 正确做法（v6.3）

```python
# ✅ 正确：使用类型特定的 Metadata
metadata = InternalMCPToolMetadata(
    name="query_policy_basic",
    description="...",
    type=ToolType.TOOL,
    category="policy",
    # Internal MCP 特定字段
    base_url="http://policy-service",
    endpoint="/api/v1/policies/{policy_id}/basic",
    method="GET",
    service_name="policy-service",
)

# 验证时直接访问字段（正确）
if not isinstance(metadata, InternalMCPToolMetadata):
    errors.append("类型错误")
    return errors

if not metadata.base_url:
    errors.append("必须配置 base_url")
```

**好处**：
- 字段有明确定义
- 类型安全
- IDE 代码补全
- 编译时检查

### 3.2 类型安全对比

| 维度 | 错误做法（hasattr） | 正确做法（子类） |
|------|-------------------|-----------------|
| **类型检查** | ❌ 运行时才发现错误 | ✅ 编译时检查 |
| **IDE 支持** | ❌ 无代码补全 | ✅ 完整代码补全 |
| **可维护性** | ❌ 字段定义不明确 | ✅ 字段定义清晰 |
| **可扩展性** | ❌ 难以扩展 | ✅ 易于扩展 |
| **错误提示** | ❌ AttributeError | ✅ 类型错误提示 |

### 3.3 验证逻辑对比

#### 错误做法

```python
# ❌ 问题 1：hasattr 检查不存在的字段
if not hasattr(metadata, 'base_url'):
    # 永远是 True（字段不存在）
    errors.append("必须配置 base_url")

# ❌ 问题 2：即使字段存在，也可能是 None
if hasattr(metadata, 'base_url') and not metadata.base_url:
    # 逻辑复杂，容易出错
    errors.append("base_url 不能为空")
```

#### 正确做法

```python
# ✅ 正确：先类型检查
if not isinstance(metadata, InternalMCPToolMetadata):
    errors.append("类型错误")
    return errors  # 类型错误，后续检查无意义

# ✅ 正确：直接访问字段
if not metadata.base_url:
    errors.append("必须配置 base_url")

if not metadata.endpoint:
    errors.append("必须配置 endpoint")
```

---

## 四、迁移指南

### 4.1 代码迁移

#### 步骤 1：更新 types.py

```python
# 新增子类定义
from core.tool_service.types import (
    ToolMetadata,
    ExternalMCPToolMetadata,
    InternalMCPToolMetadata,
    SkillToolMetadata,
    FunctionToolMetadata,
)
```

#### 步骤 2：更新 Adapter

```python
# 旧代码
metadata = ToolMetadata(
    name=name,
    description=description,
    type=ToolType.TOOL,
    adapter_type=AdapterType.INTERNAL_MCP,
)

# 新代码
metadata = InternalMCPToolMetadata(
    name=name,
    description=description,
    type=ToolType.TOOL,
    category=self.domain,
    # 特定字段
    base_url=self.client.base_url,
    endpoint=tool_info["endpoint"],
    method=tool_info["method"],
    service_name=self.service_name,
)
```

#### 步骤 3：更新 Validator

```python
# 旧代码
async def _validate_specific(self, metadata: ToolMetadata) -> list[str]:
    errors = []
    if not hasattr(metadata, 'base_url') or not metadata.base_url:
        errors.append("必须配置 base_url")
    return errors

# 新代码
async def _validate_specific(self, metadata: InternalMCPToolMetadata) -> list[str]:
    errors = []
    
    # 类型检查
    if not isinstance(metadata, InternalMCPToolMetadata):
        errors.append(f"类型错误: {type(metadata).__name__}")
        return errors
    
    # 直接访问字段
    if not metadata.base_url:
        errors.append("必须配置 base_url")
    
    return errors
```

### 4.2 兼容性说明

**向后兼容**：
- `ToolMetadata` 仍然存在（作为基类）
- 子类继承所有基类字段
- 现有代码可以逐步迁移

**不兼容的地方**：
- 不能再用 `hasattr` 检查特定字段
- 必须使用正确的子类创建 metadata

---

## 五、设计原则总结

### 5.1 类型安全原则

**原则**：使用类型系统而不是运行时检查。

```python
# ❌ 错误：运行时检查
if hasattr(obj, 'field'):
    value = obj.field

# ✅ 正确：类型检查
if isinstance(obj, SpecificType):
    value = obj.field  # IDE 知道这个字段存在
```

### 5.2 继承原则

**原则**：使用继承表示"是一个"关系。

```python
# ✅ 正确：InternalMCPToolMetadata 是一个 ToolMetadata
class InternalMCPToolMetadata(ToolMetadata):
    base_url: str
    endpoint: str
    method: str
```

### 5.3 单一职责原则

**原则**：每个类只负责一种类型的数据。

```python
# ✅ 正确：每种工具类型有自己的 Metadata
InternalMCPToolMetadata  # 内部 MCP 特定字段
ExternalMCPToolMetadata  # 外部 MCP 特定字段
SkillToolMetadata        # Skill 特定字段
FunctionToolMetadata     # Function 特定字段
```

### 5.4 开闭原则

**原则**：对扩展开放，对修改关闭。

```python
# ✅ 正确：新增工具类型只需添加新的子类
@dataclass
class GrpcToolMetadata(ToolMetadata):
    """gRPC 工具元数据"""
    grpc_service: str
    grpc_method: str
    
    def __post_init__(self):
        self.adapter_type = AdapterType.GRPC
```

---

## 六、最佳实践

### 6.1 创建 Metadata

```python
# ✅ 推荐：使用类型特定的 Metadata
metadata = InternalMCPToolMetadata(
    name="query_policy_basic",
    description="查询保单基本信息",
    type=ToolType.TOOL,
    category="policy",
    input_schema={...},
    # 特定字段
    base_url="http://policy-service",
    endpoint="/api/v1/policies/{policy_id}/basic",
    method="GET",
    service_name="policy-service",
)
```

### 6.2 验证 Metadata

```python
# ✅ 推荐：先类型检查，再字段检查
async def _validate_specific(self, metadata: InternalMCPToolMetadata) -> list[str]:
    errors = []
    
    # 1. 类型检查（防御性编程）
    if not isinstance(metadata, InternalMCPToolMetadata):
        errors.append(f"类型错误: {type(metadata).__name__}")
        return errors
    
    # 2. 字段检查
    if not metadata.base_url:
        errors.append("必须配置 base_url")
    
    if not metadata.endpoint:
        errors.append("必须配置 endpoint")
    
    return errors
```

### 6.3 类型注解

```python
# ✅ 推荐：使用具体的类型注解
async def load_tools(self) -> List[InternalMCPToolMetadata]:
    """返回类型明确"""
    ...

async def validate_tool(self, metadata: InternalMCPToolMetadata) -> tuple[bool, list[str]]:
    """参数类型明确"""
    ...
```

---

## 七、总结

### 7.1 核心改进

1. **引入类型特定的 Metadata 子类**：
   - `ExternalMCPToolMetadata`
   - `InternalMCPToolMetadata`
   - `SkillToolMetadata`
   - `FunctionToolMetadata`

2. **消除 hasattr 检查**：
   - 使用 `isinstance` 类型检查
   - 直接访问字段

3. **提升类型安全**：
   - 编译时检查
   - IDE 代码补全
   - 更好的错误提示

### 7.2 设计原则

1. ✅ 使用类型系统而不是运行时检查
2. ✅ 使用继承表示"是一个"关系
3. ✅ 每个类只负责一种类型的数据
4. ✅ 对扩展开放，对修改关闭

### 7.3 一句话总结

> 用类型特定的 Metadata 子类替代通用 ToolMetadata + hasattr 检查，提升类型安全和代码可维护性。

---

**文档维护者**：Agent Platform Team  
**最后更新**：2026-04-02  
**版本**：v6.3
