# Tool Service 架构说明

## 目录结构

```
┌─────────────────────────────────────────────────────────────┐
│                     domain_agents/                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   policy/    │  │   claim/     │  │  customer/   │     │
│  │   ├─tools/   │  │   ├─tools/   │  │   ├─tools/   │     │
│  │   │ (MCP)    │  │   │ (MCP)    │  │   │ (MCP)    │     │
│  │   └─skills/  │  │   └─skills/  │  │   └─skills/  │     │
│  │   (Skill)    │  │   (Skill)    │  │   (Skill)    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                     common_tools/                           │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │   mcp/       │  │   skills/    │                        │
│  │ (公共MCP工具) │  │ (公共Skill)  │                        │
│  └──────────────┘  └──────────────┘                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              core/tool_service/ (基础设施层)                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  registry.py - 工具注册表和调用网关                   │  │
│  │  - ToolGateway: 统一的工具注册和调用入口              │  │
│  │  - register_skill(): 注册 skill 类型工具              │  │
│  │  - register_mcp_provider(): 注册 MCP 提供者           │  │
│  │  - list_tools(): 列出所有工具                         │  │
│  │  - invoke(): 调用指定工具                             │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  mcp/ - MCP 客户端                                    │  │
│  │  - internal_client.py: 内部 MCP 服务客户端           │  │
│  │  - external_client.py: 外部 MCP 服务器客户端         │  │
│  │  - base.py: MCP 客户端抽象基类                        │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  skills/ - Skill 装饰器                               │  │
│  │  - base.py: @skill 装饰器，用于注册简单函数工具       │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 职责划分

### 1. core/tool_service/ - 基础设施层

**职责**：
- 提供工具注册、发现、调用的统一接口
- 管理不同类型的工具提供者（MCP、Skill）
- 提供工具路由和调用网关
- 提供 MCP 客户端实现

**不包含**：
- ❌ 具体的业务工具实现
- ❌ 业务逻辑
- ❌ 领域知识

**核心组件**：

#### registry.py
```python
class ToolGateway:
    """工具注册表和调用网关"""
    
    def register_skill(name, func, ...):
        """注册 skill 类型工具"""
    
    async def register_mcp_provider(provider, mcp_provider):
        """注册 MCP 提供者，自动发现其工具"""
    
    def list_tools() -> List[Dict]:
        """列出所有已注册的工具"""
    
    async def invoke(tool_name, arguments) -> Any:
        """调用指定的工具"""
```

#### mcp/internal_client.py
```python
class InternalMCPClient:
    """内部 MCP 服务客户端"""
    - 调用内部 MCP 服务（如 mcp-service）
    - 自动透传上下文信息
    - 支持重试机制
```

#### mcp/external_client.py
```python
class ExternalMCPClient:
    """外部 MCP 服务器客户端"""
    - 调用第三方 MCP 服务器
    - 使用 token 认证
    - 不透传内部上下文
```

#### skills/base.py
```python
@skill(name="my_skill")
async def my_skill_func(args: dict) -> dict:
    """简单的函数式工具"""
    return {"result": "..."}
```

### 2. domain_agents/*/tools/ 和 domain_agents/*/skills/ - 业务层

**职责**：
- 实现具体的业务工具（MCP 和 Skill）
- 包含领域知识和业务逻辑
- 调用后端服务 API
- 处理业务数据转换

**目录结构**：
```
domain_agents/
  policy/
    tools/          # MCP 工具（复杂业务逻辑）
      policy_tools.py
    skills/         # Skill 工具（简单函数）
      policy_skills.py
    register.py
    memory_config.py
```

**MCP 工具示例**：

```python
# domain_agents/policy/tools/policy_tools.py
from mcp.server.fastmcp import FastMCP
from shared.internal_http.client import get_internal_api_client

mcp = FastMCP("policy-domain")

@mcp.tool()
async def query_policy_basic(policy_id: str) -> dict:
    """查询保单基本信息"""
    client = get_internal_api_client()
    data = await client.get(f"/policy-service/api/v1/policies/{policy_id}/basic")
    return {
        "policy_id": data["policyId"],
        "status": data["status"],
        # ... 业务数据转换
    }
```

**Skill 工具示例**：

```python
# domain_agents/policy/skills/policy_skills.py
from core.tool_service.skills.base import skill

@skill(name="format_policy_id")
async def format_policy_id(args: dict) -> dict:
    """格式化保单号"""
    pid = str(args.get("policy_id", "")).strip().upper()
    return {"normalized": pid}
```

### 3. common_tools/ - 公共工具层

**职责**：
- 提供跨领域的通用工具
- 不包含业务逻辑和领域知识
- 可被多个 domain agent 共享使用

**目录结构**：
```
common_tools/
  mcp/              # 公共 MCP 工具
    time_tools.py   # 时间处理
    text_tools.py   # 文本处理
  skills/           # 公共 Skill 工具
    format_skills.py    # 格式化
    validation_skills.py # 验证
  README.md
```

**何时使用 common_tools**：

✅ 应该放在 common_tools：
- 跨多个领域使用的工具
- 与业务领域无关的工具
- 纯技术性功能（时间、格式化、验证等）

❌ 应该放在 domain_agents：
- 领域特定的工具
- 包含业务逻辑的工具
- 需要调用特定业务服务的工具

**示例**：

```python
# common_tools/mcp/time_tools.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("common-time")

@mcp.tool()
async def get_current_time(timezone: str = "UTC") -> dict:
    """获取指定时区的当前时间"""
    # 通用时间处理逻辑
    return {"time": "...", "timezone": timezone}
```

```python
# common_tools/skills/format_skills.py
from core.tool_service.skills.base import skill

@skill(name="format_phone_number")
async def format_phone_number(args: dict) -> dict:
    """格式化电话号码"""
    phone = args.get("phone", "")
    # 通用格式化逻辑
    return {"formatted": "..."}
```

### 3. 工具注册流程

```python
# app/gateway/lifespan.py

# 1. 注册公共工具（如果有）
# 导入即自动注册 Skills
from core.tool_service.common_tools.skills import format_skills
# 注册公共 MCP 工具（如果需要）
# from core.tool_service.common_tools.mcp import time_tools

# 2. 注册内部 MCP 服务（如果有独立的 mcp-service）
from core.tool_service.mcp.internal_client import InternalMCPClient
await tool_gateway.register_mcp_provider("mcp", InternalMCPClient())

# 3. 注册外部 MCP 服务器
from core.tool_service.mcp.external_client import ExternalMCPClient
for idx, endpoint in enumerate(settings.external_mcp_endpoints):
    await tool_gateway.register_mcp_provider(
        f"ext{idx + 1}",
        ExternalMCPClient(endpoint, token=settings.external_mcp_token)
    )

# 4. Domain agents 在 register() 中注册自己的工具
# domain_agents/policy/register.py
from domain_agents.policy.tools.policy_tools import policy_tools
from domain_agents.policy.skills import policy_skills  # 导入即注册

def register():
    agent_gateway.register(AgentMeta(
        agent_id="policy-assistant",
        tools=[
            # 领域 MCP 工具
            "mcp:query_policy_basic",
            # 领域 Skill 工具
            "format_policy_id",
            # 公共工具
            "common-time:get_current_time",
            "format_phone_number",
        ],
        # ...
    ))
```

## 工具类型

### 1. MCP Tools (推荐)

**特点**：
- 使用 FastMCP 定义
- 支持完整的 MCP 协议
- 自动生成 schema
- 支持工具发现

**使用场景**：
- 业务领域工具（policy, claim, customer）
- 需要调用后端服务的工具
- 复杂的业务逻辑

**示例**：
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-domain")

@mcp.tool()
async def my_tool(arg1: str, arg2: int) -> dict:
    """工具描述"""
    return {"result": "..."}
```

### 2. Skills (简单函数)

**特点**：
- 使用 @skill 装饰器
- 简单的函数式工具
- 不需要 MCP 协议

**使用场景**：
- 简单的数据转换
- 工具函数
- 不需要外部调用的逻辑

**示例**：
```python
from core.tool_service.skills.base import skill

@skill(name="format_policy_id")
async def format_policy_id(args: dict) -> dict:
    pid = str(args.get("policy_id", "")).strip().upper()
    return {"normalized": pid}
```

## 工具调用流程

```
Agent 执行
    ↓
调用 tool_gateway.invoke("mcp:query_policy_basic", {...})
    ↓
ToolGateway 查找工具
    ↓
找到对应的 ToolEntry
    ↓
调用 MCP Provider 的 invoke()
    ↓
InternalMCPClient 发送 HTTP 请求到 mcp-service
    ↓
mcp-service 执行具体的工具逻辑
    ↓
返回结果
```

## 扩展点

### 1. 添加新的业务工具

在 `domain_agents/` 下创建新的领域目录：

```
domain_agents/
  new_domain/
    tools/
      new_tools.py      # 使用 FastMCP 定义工具
    register.py         # 注册 agent 和工具
    memory_config.py    # 记忆配置
```

### 2. 添加新的 MCP 提供者

实现 `McpProvider` 协议：

```python
class CustomMCPProvider:
    async def list_tools(self) -> List[Dict[str, Any]]:
        """返回工具列表"""
        
    async def invoke(self, tool: str, arguments: Dict[str, Any]) -> Any:
        """调用工具"""
```

### 3. 添加工具中间件

在 `ToolGateway.invoke()` 中添加：
- 权限检查
- 参数验证
- 日志记录
- 性能监控
- 熔断限流

## 最佳实践

### 1. 工具命名

- MCP 工具：使用 `provider:tool_name` 格式
  - 例如：`mcp:query_policy_basic`
  - 例如：`ext1:weather_forecast`
- Skill 工具：直接使用名称
  - 例如：`format_policy_id`

### 2. 工具描述

- 清晰描述工具的功能
- 说明何时应该调用此工具
- 列出参数的含义和格式

### 3. 错误处理

```python
@mcp.tool()
async def my_tool(arg: str) -> dict:
    try:
        # 业务逻辑
        return {"result": "..."}
    except Exception as e:
        logger.error("tool_failed", tool="my_tool", error=str(e))
        return {"error": f"执行失败: {str(e)}"}
```

### 4. 上下文传递

- 内部服务调用：使用 `shared/internal_http/client.py`
- MCP 服务调用：使用 `InternalMCPClient`
- 两者都会自动透传上下文信息

## 总结

- `core/tool_service/` 是**基础设施层**，只提供工具管理能力
- `domain_agents/*/tools/` 是**业务层**，包含具体的工具实现
- 工具通过 `ToolGateway` 统一注册和调用
- 支持 MCP 和 Skill 两种工具类型
- 内部/外部 MCP 客户端分离，职责清晰
