# Tool Service 代码框架

> 基于 `tool_service_final_design.md` v6.3 搭建的完整代码框架

## 目录结构

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
│   └── validator.py                  # ExternalMCPValidator(BaseValidator)
│
├── internal_mcp/                     # 内部 MCP 工具
│   ├── __init__.py
│   ├── adapter.py                    # InternalMCPAdapter(ToolAdapter)
│   ├── validator.py                  # InternalMCPValidator(BaseValidator)
│   └── client.py                     # HTTP 客户端封装
│
├── skill/                            # Skill 工具
│   ├── __init__.py
│   ├── adapter.py                    # SkillAdapter(ToolAdapter)
│   ├── validator.py                  # SkillValidator(BaseValidator)
│   └── executor.py                   # LLM Agent 执行器
│
└── function/                         # Function 工具
    ├── __init__.py
    ├── adapter.py                    # FunctionAdapter(ToolAdapter)
    └── validator.py                  # FunctionValidator(BaseValidator)
```

## 核心模块说明

### 1. types.py - 类型定义

包含所有类型定义：
- `ToolType`: 工具类型枚举（TOOL, SKILL）
- `AdapterType`: 适配器类型枚举（EXTERNAL_MCP, INTERNAL_MCP, SKILL, FUNCTION）
- `PermissionStrategy`: 权限策略枚举（LOCAL_ONLY, REMOTE_ONLY, LOCAL_AND_REMOTE, LOCAL_OR_REMOTE）
- `ToolMetadata`: 工具元数据基类
- `ExternalMCPToolMetadata`: 外部 MCP 工具元数据
- `InternalMCPToolMetadata`: 内部 MCP 工具元数据
- `SkillToolMetadata`: Skill 工具元数据
- `FunctionToolMetadata`: Function 工具元数据
- `ToolContext`: 工具调用上下文

### 2. base/ - 基础抽象层

提供所有 Adapter 的基类和通用组件：

#### adapter.py - ToolAdapter 基类
- `load_tools()`: 加载工具列表
- `validate_tool()`: 验证工具
- `invoke_tool()`: 调用工具
- `get_adapter_type()`: 获取适配器类型
- `health_check()`: 健康检查
- `close()`: 关闭资源

#### validator.py - BaseValidator 基类
- `validate()`: 完整验证流程
- `_validate_common()`: 通用验证逻辑（90%）
- `_validate_specific()`: 特定验证逻辑（10%，子类实现）

#### permissions.py - BasePermissionChecker 基类
- `check_permission()`: 检查权限（支持多种策略）
- `_check_local()`: 本地白名单检查
- `_check_remote()`: 远程用户中心检查
- `_check_remote_with_fallback()`: 远程检查（带缓存和降级）

### 3. registry.py - ToolGateway

统一的工具网关：
- `register_adapter()`: 注册 Adapter
- `load_tools_from_adapter()`: 从 Adapter 加载工具
- `list_tools()`: 列出所有工具（带权限过滤）
- `invoke()`: 调用工具（带权限检查和审计）
- `health_check()`: 健康检查
- `close()`: 关闭所有 Adapter

全局单例：`tool_gateway`

### 4. router.py - ToolRouter

工具路由器，支持多种匹配策略：
- `match_tools()`: 根据查询匹配工具
- `_match_by_keyword()`: 关键词匹配
- `_match_by_vector()`: 向量相似度匹配（TODO）
- `_match_by_llm()`: LLM 推理匹配（TODO）
- `_match_by_hybrid()`: 混合策略匹配（TODO）

### 5. Adapters

#### external_mcp/ - 外部 MCP Adapter
对接外部 MCP Server（第三方服务）：
- 使用 token 认证
- 不透传内部上下文
- 支持重试机制

#### internal_mcp/ - 内部 MCP Adapter
对接内部微服务（Spring Boot 等）：
- 透传上下文信息（tenant_id, user_id 等）
- 使用内部网络
- 委托给 InternalHTTPClient 执行

#### skill/ - Skill Adapter
执行 LLM 驱动的 Skill：
- Skill = Prompt Template + Available Tools + LLM Execution
- 由 LLM 推理和决策
- 通过 SkillExecutor 执行

#### function/ - Function Adapter
直接调用 Python 函数：
- 最简单的工具类型
- 自动从函数签名生成 schema
- 支持同步和异步函数

## 架构原则

1. **按工具类型划分**：每个工具类型是一个独立的"包"
2. **Base 层提供通用能力**：adapter、validator、permissions 的基类
3. **继承实现复用**：各工具类型继承 base，只实现特定逻辑
4. **清晰的边界**：每个类型有自己的 adapter、validator、client、types
5. **统一的对外接口**：业务层只看到 `tool_gateway.invoke()`
6. **类型安全**：使用类型系统而非运行时检查

## 使用示例

### 注册工具

```python
from core.tool_service import (
    tool_gateway,
    ExternalMCPAdapter,
    InternalMCPAdapter,
    SkillAdapter,
    SkillDefinition,
    FunctionAdapter,
)

# 1. 注册 External MCP 工具
weather_adapter = ExternalMCPAdapter(
    name="weather",
    endpoint="https://weather-api.example.com",
    token="your-token",
)
tool_gateway.register_adapter(weather_adapter)
await tool_gateway.load_tools_from_adapter(weather_adapter)

# 2. 注册 Internal MCP 工具
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
)
tool_gateway.register_adapter(policy_adapter)
await tool_gateway.load_tools_from_adapter(policy_adapter)

# 3. 注册 Skill
skill_adapter = SkillAdapter(domain="policy", tool_gateway=tool_gateway)
skill_def = SkillDefinition(
    name="analyze_policy_risk",
    description="分析保单风险",
    prompt_template="分析保单 {policy_id} 的风险...",
    available_tools=["query_policy_basic"],
)
skill_adapter.register_skill(skill_def)
tool_gateway.register_adapter(skill_adapter)
await tool_gateway.load_tools_from_adapter(skill_adapter)

# 4. 注册 Function
function_adapter = FunctionAdapter(domain="common")
def calculate_age(birth_year: int) -> dict:
    """计算年龄"""
    from datetime import datetime
    return {"age": datetime.now().year - birth_year}

function_adapter.register_function(calculate_age)
tool_gateway.register_adapter(function_adapter)
await tool_gateway.load_tools_from_adapter(function_adapter)
```

### 调用工具

```python
from core.tool_service import tool_gateway, ToolContext

# 创建上下文
context = ToolContext(
    tenant_id="tenant_a",
    user_id="user_123",
    channel_id="web",
)

# 调用 Internal MCP 工具
result = await tool_gateway.invoke(
    tool_name="query_policy_basic",
    arguments={"policy_id": "P2024001"},
    context=context,
)

# 调用 Skill
result = await tool_gateway.invoke(
    tool_name="analyze_policy_risk",
    arguments={"policy_id": "P2024001"},
    context=context,
)

# 调用 Function
result = await tool_gateway.invoke(
    tool_name="calculate_age",
    arguments={"birth_year": 1990},
    context=context,
)
```

### 列出工具

```python
# 列出所有工具
all_tools = await tool_gateway.list_tools()

# 按分类过滤
policy_tools = await tool_gateway.list_tools(category="policy")

# 带权限过滤
available_tools = await tool_gateway.list_tools(context=context)
```

### 工具路由

```python
from core.tool_service import init_tool_router, MatchStrategy

router = init_tool_router(tool_gateway)

# 关键词匹配
matched_tools = await router.match_tools(
    query="查询保单",
    strategy=MatchStrategy.KEYWORD,
    top_k=5,
    context=context,
)
```

## 下一步工作

1. **实现完整的 ToolRouter**：
   - 向量相似度匹配
   - LLM 推理匹配
   - 混合策略匹配

2. **完善 Skill 执行边界**：
   - 实现五大边界约束（参考 `skill_execution_boundaries.md`）
   - 添加 max_steps、timeout 限制
   - 实现独立计量和观测

3. **修复已知问题**：
   - health_check 实现（参考 `tool_service_architecture_fixes.md`）
   - External MCP 工具缓存（使用 Redis）
   - SkillDefinition 持久化存储

4. **集成到 Gateway**：
   - 在 `app/gateway/lifespan.py` 中注册所有工具
   - 配置权限检查器
   - 添加监控和告警

5. **测试**：
   - 单元测试（每个 Adapter）
   - 集成测试（完整流程）
   - 性能测试（权限检查、工具调用）

## 参考文档

- 设计文档：`docs/architecture/tool_service/tool_service_final_design.md`
- 架构修复：`docs/architecture/tool_service/tool_service_architecture_fixes.md`
- Skill 边界：`docs/architecture/tool_service/skill_execution_boundaries.md`
- 变更日志：`docs/architecture/tool_service/tool_service_changelog.md`
