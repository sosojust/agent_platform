# Tool Service 架构更新说明 v6.0

> 日期：2026-04-02  
> 更新版本：v6.0

## 一、更新概述

本次更新采用了**按工具类型划分 + Base 继承**的目录结构（方案 B），相比 v5.0 的按职责划分结构，提供了更清晰的边界和更好的扩展性。

---

## 二、目录结构变化

### 2.1 v5.0 结构（按职责划分）

```
core/tool_service/
├── types.py
├── registry.py
├── router.py
├── permissions.py              # 统一权限检查
├── validator.py                # 统一验证器
└── adapters/                   # 所有适配器
    ├── base.py
    ├── external_mcp_adapter.py
    ├── internal_mcp_adapter.py
    ├── skill_adapter.py
    └── function_adapter.py
```

### 2.2 v6.0 结构（按工具类型划分）

```
core/tool_service/
├── types.py                    # 通用类型
├── registry.py                 # ToolGateway
├── router.py                   # ToolRouter
│
├── base/                       # 基础抽象层（核心）
│   ├── adapter.py              # ToolAdapter 基类
│   ├── validator.py            # BaseValidator 基类
│   └── permissions.py          # BasePermissionChecker 基类
│
├── external_mcp/               # 外部 MCP 工具
│   ├── adapter.py
│   ├── validator.py
│   ├── client.py
│   └── types.py
│
├── internal_mcp/               # 内部 MCP 工具
│   ├── adapter.py
│   ├── validator.py
│   ├── client.py
│   └── types.py
│
├── skill/                      # Skill 工具
│   ├── adapter.py
│   ├── validator.py
│   ├── executor.py             # Skill 特有
│   ├── prompt_manager.py       # Skill 特有
│   └── types.py
│
└── function/                   # Function 工具
    ├── adapter.py
    ├── validator.py
    └── types.py
```

---

## 三、核心设计原则

### 3.1 按工具类型划分

每个工具类型是一个独立的"包"：
- 有自己的 adapter
- 有自己的 validator（继承 base）
- 有自己的 client（如果需要）
- 有自己的特定类型定义

### 3.2 Base 层提供通用能力

```python
# base/adapter.py
class ToolAdapter(ABC):
    """所有 Adapter 的基类"""
    @abstractmethod
    async def load_tools(self): ...
    @abstractmethod
    async def invoke_tool(self, ...): ...
    
    # 通用方法
    async def health_check(self): ...

# base/validator.py
class BaseValidator:
    """所有 Validator 的基类"""
    async def validate(self, metadata):
        # 1. 通用验证（90%）
        errors = self._validate_common(metadata)
        # 2. 特定验证（10%，子类实现）
        errors.extend(await self._validate_specific(metadata))
        return errors
    
    def _validate_common(self, metadata):
        """通用验证逻辑"""
        ...
    
    async def _validate_specific(self, metadata):
        """特定验证逻辑（子类覆盖）"""
        return []
```

### 3.3 各类型继承 Base

```python
# external_mcp/adapter.py
class ExternalMCPAdapter(ToolAdapter):
    """继承 ToolAdapter，实现特定逻辑"""
    ...

# external_mcp/validator.py
class ExternalMCPValidator(BaseValidator):
    """继承 BaseValidator，只需实现特定验证"""
    async def _validate_specific(self, metadata):
        errors = []
        if not metadata.endpoint:
            errors.append("必须配置 endpoint")
        return errors
```

---

## 四、主要优势

### 4.1 清晰的边界

```
每个工具类型独立：
- external_mcp/  → 外部 MCP 相关
- internal_mcp/  → 内部 MCP 相关
- skill/         → Skill 相关
- function/      → Function 相关
```

**好处**：
- 职责清晰，易于理解
- 修改某个类型不影响其他类型
- 团队可以按类型分工

### 4.2 代码复用

```python
# 通用逻辑在 base 中实现（90%）
BaseValidator._validate_common()

# 特定逻辑在子类中实现（10%）
ExternalMCPValidator._validate_specific()
InternalMCPValidator._validate_specific()
SkillValidator._validate_specific()
```

**好处**：
- 避免代码重复
- 通用逻辑统一维护
- 特定逻辑独立扩展

### 4.3 易于扩展

```
新增 gRPC 工具类型：
core/tool_service/grpc/
├── adapter.py          # 继承 ToolAdapter
├── validator.py        # 继承 BaseValidator
├── client.py
└── types.py
```

**好处**：
- 新增类型只需创建一个目录
- 继承 base 即可复用通用能力
- 不影响现有类型

### 4.4 独立的特定逻辑

```
skill/ 目录包含 Skill 特有的模块：
- executor.py         # LLM Agent 执行器
- prompt_manager.py   # Prompt 管理
- types.py            # Skill 特定类型
```

**好处**：
- 特定逻辑集中管理
- 不污染其他类型
- 易于测试和维护

### 4.5 统一的对外接口

```python
# 业务层只看到统一接口
from core.tool_service import tool_gateway

# 不关心底层是哪种类型
await tool_gateway.invoke("query_policy_basic", {...})
await tool_gateway.invoke("analyze_policy_risk", {...})
```

**好处**：
- 业务层解耦
- 底层实现可替换
- 易于测试（mock）

---

## 五、继承关系

### 5.1 Adapter 继承

```
ToolAdapter (base/adapter.py)
    ├── ExternalMCPAdapter (external_mcp/adapter.py)
    ├── InternalMCPAdapter (internal_mcp/adapter.py)
    ├── SkillAdapter (skill/adapter.py)
    └── FunctionAdapter (function/adapter.py)
```

### 5.2 Validator 继承

```
BaseValidator (base/validator.py)
    ├── ExternalMCPValidator (external_mcp/validator.py)
    ├── InternalMCPValidator (internal_mcp/validator.py)
    ├── SkillValidator (skill/validator.py)
    └── FunctionValidator (function/validator.py)
```

### 5.3 Permissions（通用）

```
BasePermissionChecker (base/permissions.py)
    └── 所有类型共用（不需要子类）
```

---

## 六、导入方式

### 6.1 v5.0 导入

```python
from core.tool_service.adapters import (
    ExternalMCPAdapter,
    InternalMCPAdapter,
    SkillAdapter,
    FunctionAdapter,
)
from core.tool_service.validator import ToolValidator
from core.tool_service.permissions import PermissionChecker
```

### 6.2 v6.0 导入

```python
# 方式 1：从各类型目录导入
from core.tool_service.external_mcp.adapter import ExternalMCPAdapter
from core.tool_service.internal_mcp.adapter import InternalMCPAdapter
from core.tool_service.skill.adapter import SkillAdapter
from core.tool_service.function.adapter import FunctionAdapter

# 方式 2：从 __init__.py 统一导出
from core.tool_service import (
    ExternalMCPAdapter,
    InternalMCPAdapter,
    SkillAdapter,
    FunctionAdapter,
)
```

---

## 七、测试组织

### 7.1 v5.0 测试结构

```
tests/tool_service/
├── test_registry.py
├── test_router.py
├── test_validator.py
├── test_permissions.py
└── adapters/
    ├── test_external_mcp_adapter.py
    ├── test_internal_mcp_adapter.py
    ├── test_skill_adapter.py
    └── test_function_adapter.py
```

### 7.2 v6.0 测试结构

```
tests/tool_service/
├── test_registry.py
├── test_router.py
├── base/
│   ├── test_adapter.py
│   ├── test_validator.py
│   └── test_permissions.py
├── external_mcp/
│   ├── test_adapter.py
│   ├── test_validator.py
│   └── test_client.py
├── internal_mcp/
│   ├── test_adapter.py
│   ├── test_validator.py
│   └── test_client.py
├── skill/
│   ├── test_adapter.py
│   ├── test_validator.py
│   └── test_executor.py
└── function/
    ├── test_adapter.py
    └── test_validator.py
```

---

## 八、迁移指南

### 8.1 代码迁移

**旧代码（v5.0）**：
```python
from core.tool_service.adapters.external_mcp_adapter import ExternalMCPAdapter
```

**新代码（v6.0）**：
```python
from core.tool_service.external_mcp.adapter import ExternalMCPAdapter
# 或
from core.tool_service import ExternalMCPAdapter
```

### 8.2 自定义 Validator

**旧代码（v5.0）**：
```python
# 需要实现完整的验证逻辑
class MyValidator:
    def validate(self, metadata):
        errors = []
        # 通用验证
        if not metadata.name:
            errors.append("名称不能为空")
        # 特定验证
        if not metadata.custom_field:
            errors.append("必须有 custom_field")
        return errors
```

**新代码（v6.0）**：
```python
# 只需实现特定验证逻辑
from core.tool_service.base.validator import BaseValidator

class MyValidator(BaseValidator):
    async def _validate_specific(self, metadata):
        errors = []
        # 只需实现特定验证
        if not metadata.custom_field:
            errors.append("必须有 custom_field")
        return errors
```

---

## 九、总结

### 9.1 核心变化

1. **目录结构**：从按职责划分改为按工具类型划分
2. **Base 层**：新增 base/ 目录，提供通用能力
3. **继承机制**：各类型继承 base，实现代码复用
4. **独立性**：每个类型有自己的目录，包含所有相关内容

### 9.2 保留的内容

1. **v5.0 的所有概念澄清**：
   - Skill 执行模型（LLM 驱动）
   - Internal MCP Adapter 本质（HTTP + MCP 封装）
   - MCP 的两种用途

2. **统一的对外接口**：
   - tool_gateway
   - tool_router
   - ToolContext

### 9.3 一句话总结

> v6.0 采用按工具类型划分 + Base 继承的架构，在保留 v5.0 所有概念澄清的基础上，提供了更清晰的边界、更好的代码复用和更强的扩展性。

---

**文档维护者**：Agent Platform Team  
**最后更新**：2026-04-02  
**版本**：v6.0
