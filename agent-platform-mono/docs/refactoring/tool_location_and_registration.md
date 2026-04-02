# 工具位置和注册机制澄清

## 问题

在之前的架构设计中，存在两个需要澄清的问题：

1. **common_tools 的位置**
   - 最初放在顶层 `common_tools/`
   - 但实际上应该放在 `core/tool_service/` 下更合适

2. **工具注册机制的误解**
   - 文档中提到需要"注册"工具
   - 但实际上工具通过装饰器**自动注册**，不需要手动调用

## 解决方案

### 1. 将 common_tools 移动到 tool_service 下

**原因**：

- `core/tool_service/` 是工具相关的模块
- `common_tools/` 虽然是具体工具实现，但属于工具服务的一部分
- 与 `registry.py`、`mcp/`、`skills/` 等放在一起更合理
- 便于统一管理和发现

**目录结构**：

```
core/tool_service/
├── registry.py          # 工具注册表（基础设施）
├── mcp/                 # MCP 客户端（基础设施）
│   ├── internal_client.py
│   ├── external_client.py
│   └── base.py
├── skills/              # Skill 装饰器（基础设施）
│   └── base.py
└── common_tools/        # 公共工具（具体实现）
    ├── mcp/             # 公共 MCP 工具
    │   ├── time_tools.py
    │   └── text_tools.py
    └── skills/          # 公共 Skill 工具
        ├── format_skills.py
        └── validation_skills.py
```

**职责划分**：

- `registry.py`, `mcp/`, `skills/` - 基础设施，提供工具管理能力
- `common_tools/` - 具体的公共工具实现

### 2. 澄清工具注册机制

工具通过装饰器**自动注册**，不需要手动调用注册函数。

#### Skill 工具的自动注册

```python
# core/tool_service/skills/base.py
def skill(name: str | None = None, ...):
    def decorator(func: F) -> F:
        reg_name = name or func.__name__
        # 装饰器执行时自动注册
        tool_gateway.register_skill(
            reg_name,
            func,
            input_schema=input_schema,
            output_schema=output_schema,
            provider="skill",
        )
        return func
    return decorator
```

当模块被导入时，装饰器就会执行，工具自动注册到 `tool_gateway`。

**示例**：

```python
# domain_agents/policy/skills/policy_skills.py
from core.tool_service.skills.base import skill

@skill(name="format_policy_id")
async def format_policy_id(args: dict) -> dict:
    """格式化保单号"""
    pid = str(args.get("policy_id", "")).strip().upper()
    return {"normalized": pid}

# 当这个模块被导入时，装饰器执行，工具自动注册
```

#### MCP 工具的管理

MCP 工具通过 FastMCP 管理：

```python
# domain_agents/policy/tools/policy_tools.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("policy-domain")

@mcp.tool()
async def query_policy_basic(policy_id: str) -> dict:
    """查询保单基本信息"""
    # FastMCP 管理这些工具
    return {"policy_id": "..."}
```

FastMCP 会管理这些工具，并通过 MCP 协议暴露。

#### 使用工具的流程

1. **导入模块**（工具自动注册）

```python
# app/gateway/lifespan.py

# 导入 Skills（导入即自动注册）
from core.tool_service.common_tools.skills import format_skills
from domain_agents.policy.skills import policy_skills

# 导入 MCP 工具（如果需要）
# from core.tool_service.common_tools.mcp import time_tools
```

2. **在 Agent 配置中引用工具名称**

```python
# domain_agents/policy/register.py
def register():
    agent_gateway.register(AgentMeta(
        agent_id="policy-assistant",
        tools=[
            # 领域 MCP 工具
            "mcp:query_policy_basic",
            # 领域 Skill 工具（已通过导入自动注册）
            "format_policy_id",
            # 公共 Skill 工具（已通过导入自动注册）
            "format_phone_number",
            # 公共 MCP 工具
            "common-time:get_current_time",
        ],
        # ...
    ))
```

3. **Agent 执行时调用工具**

```python
# Agent 运行时
result = await tool_gateway.invoke("format_policy_id", {"policy_id": "p2024001"})
```

## 修改内容

### 目录移动

- `common_tools/` → `core/tool_service/common_tools/`

### 文档更新

1. **core/tool_service/common_tools/README.md**
   - 更新路径说明
   - 澄清自动注册机制
   - 添加"为什么放在 tool_service 下"的说明

2. **docs/architecture/tool_service_architecture.md**
   - 更新目录结构图
   - 更新路径引用

3. **docs/refactoring/tool_organization.md**
   - 更新路径引用
   - 澄清注册机制

## 架构优势

### 1. 目录结构更清晰

```
core/tool_service/          # 工具服务模块
├── registry.py            # 基础设施
├── mcp/                   # 基础设施
├── skills/                # 基础设施
└── common_tools/          # 公共工具实现
    ├── mcp/
    └── skills/

domain_agents/             # 领域 Agent
├── policy/
│   ├── tools/            # 领域工具实现
│   └── skills/           # 领域工具实现
├── claim/
└── customer/
```

### 2. 职责划分明确

- **基础设施** (`registry`, `mcp`, `skills`): 提供工具管理能力
- **公共工具** (`common_tools`): 跨领域的通用工具实现
- **领域工具** (`domain_agents/*/tools`, `domain_agents/*/skills`): 领域特定的工具实现

### 3. 自动注册机制

- 开发者只需要使用装饰器
- 导入模块时工具自动注册
- 不需要手动调用注册函数
- 减少样板代码

## 最佳实践

### 1. 工具定义

```python
# 使用装饰器定义工具
@skill(name="my_skill")
async def my_skill(args: dict) -> dict:
    return {"result": "..."}

@mcp.tool()
async def my_mcp_tool(arg: str) -> dict:
    return {"result": "..."}
```

### 2. 工具导入

```python
# 在启动时导入模块（工具自动注册）
from core.tool_service.common_tools.skills import format_skills
from domain_agents.policy.skills import policy_skills
```

### 3. 工具使用

```python
# 在 Agent 配置中引用工具名称
tools=["format_policy_id", "format_phone_number"]

# 在运行时调用工具
result = await tool_gateway.invoke("format_policy_id", {"policy_id": "..."})
```

## 总结

1. **common_tools 放在 core/tool_service/ 下**，与其他工具相关模块在一起
2. **工具通过装饰器自动注册**，不需要手动调用注册函数
3. **导入模块即注册**，在 Agent 配置中引用工具名称即可使用
4. **职责清晰**：基础设施 vs 工具实现，公共 vs 领域
