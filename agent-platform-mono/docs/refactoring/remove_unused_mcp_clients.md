# 删除未使用的 MCP 客户端

## 问题

在 `core/tool_service/mcp/` 目录下有两个 MCP 客户端：
- `internal_client.py` (InternalMCPClient)
- `external_client.py` (ExternalMCPClient)

但在当前的 `agent-platform-mono` 架构中，这两个客户端**完全没有被使用**。

## 原因分析

### 当前架构

在 `agent-platform-mono` 中：

1. **所有工具都直接在 domain_agents 中定义**
   ```python
   # domain_agents/policy/tools/policy_tools.py
   from mcp.server.fastmcp import FastMCP
   
   mcp = FastMCP("policy-domain")
   
   @mcp.tool()
   async def query_policy_basic(policy_id: str) -> dict:
       """查询保单基本信息"""
       # 直接实现工具逻辑
       return {...}
   ```

2. **工具通过装饰器自动注册**
   - MCP 工具：`@mcp.tool()` 装饰器
   - Skill 工具：`@skill` 装饰器
   - 导入模块时自动注册到 `tool_gateway`

3. **没有独立的 MCP 服务**
   - 不存在独立的 `mcp-service` 微服务
   - 所有工具都在同一个进程中

### 原始设计意图

这两个客户端是为了支持以下场景：

1. **InternalMCPClient**: 调用独立的内部 MCP 服务
   - 假设有一个独立的 `mcp-service` 微服务
   - 通过 HTTP 调用其 `/tools` 和 `/invoke` 接口

2. **ExternalMCPClient**: 调用外部第三方 MCP 服务器
   - 接入外部 MCP 生态
   - 使用 token 认证

但在当前的 mono 架构中，这两个场景都不存在。

## 决策

**删除这两个未使用的客户端**，原因：

1. **YAGNI 原则** (You Aren't Gonna Need It)
   - 当前用不到
   - 增加代码复杂度
   - 需要维护和测试

2. **架构简化**
   - 当前架构更简单：工具直接定义，装饰器自动注册
   - 不需要额外的客户端层

3. **需要时再添加**
   - 如果未来需要接入外部 MCP 服务器，可以再实现
   - 保留 `base.py` 作为接口定义

## 修改内容

### 删除文件

1. `core/tool_service/mcp/internal_client.py`
2. `core/tool_service/mcp/external_client.py`

### 修改文件

1. **core/tool_service/mcp/__init__.py**
   - 删除对已删除客户端的导出
   - 只保留 `MCPClientBase`
   - 添加说明注释

2. **core/tool_service/mcp/base.py**
   - 添加说明注释
   - 保留作为接口定义

3. **app/gateway/lifespan.py**
   - 删除 MCP 客户端注册代码
   - 添加注释说明工具已自动注册

## 当前工具注册流程

### 1. 定义工具

```python
# domain_agents/policy/tools/policy_tools.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("policy-domain")

@mcp.tool()
async def query_policy_basic(policy_id: str) -> dict:
    """查询保单基本信息"""
    client = get_internal_api_client()
    data = await client.get(f"/policy-service/api/v1/policies/{policy_id}/basic")
    return {...}
```

```python
# domain_agents/policy/skills/policy_skills.py
from core.tool_service.skills.base import skill

@skill(name="format_policy_id")
async def format_policy_id(args: dict) -> dict:
    """格式化保单号"""
    return {"normalized": "..."}
```

### 2. 导入模块（自动注册）

```python
# domain_agents/policy/register.py
from domain_agents.policy.tools.policy_tools import policy_tools
from domain_agents.policy.skills import policy_skills  # 导入即注册

def register():
    # 工具已通过装饰器自动注册
    agent_gateway.register(AgentMeta(
        agent_id="policy-assistant",
        tools=[
            "mcp:query_policy_basic",  # MCP 工具
            "format_policy_id",         # Skill 工具
        ],
        # ...
    ))
```

### 3. 使用工具

```python
# Agent 运行时
result = await tool_gateway.invoke("format_policy_id", {"policy_id": "p2024001"})
```

## 未来扩展

如果未来需要接入外部 MCP 服务器或独立的 MCP 服务，可以：

1. **实现 MCPClientBase 接口**
   ```python
   # core/tool_service/mcp/external_client.py
   from core.tool_service.mcp.base import MCPClientBase
   
   class ExternalMCPClient(MCPClientBase):
       async def list_tools(self) -> List[Dict[str, Any]]:
           # 实现逻辑
           pass
       
       async def invoke(self, tool: str, arguments: Dict[str, Any]) -> Any:
           # 实现逻辑
           pass
   ```

2. **注册 MCP 提供者**
   ```python
   # app/gateway/lifespan.py
   from core.tool_service.mcp.external_client import ExternalMCPClient
   
   external_client = ExternalMCPClient(
       base_url="https://external-mcp.example.com",
       token="your-token"
   )
   await tool_gateway.register_mcp_provider("ext1", external_client)
   ```

3. **使用外部工具**
   ```python
   # 工具名称格式：provider:tool_name
   result = await tool_gateway.invoke("ext1:weather_forecast", {"city": "Beijing"})
   ```

## 架构对比

### 修改前

```
core/tool_service/
├── registry.py
├── mcp/
│   ├── base.py
│   ├── internal_client.py  ❌ 未使用
│   ├── external_client.py  ❌ 未使用
│   └── __init__.py
├── skills/
└── common_tools/

domain_agents/
├── policy/tools/           ✅ 直接定义工具
└── policy/skills/          ✅ 直接定义工具
```

### 修改后

```
core/tool_service/
├── registry.py
├── mcp/
│   ├── base.py            ✅ 保留作为接口定义
│   └── __init__.py
├── skills/
└── common_tools/

domain_agents/
├── policy/tools/          ✅ 直接定义工具
└── policy/skills/         ✅ 直接定义工具
```

## 优势

1. **代码更简洁**：删除了 200+ 行未使用的代码
2. **架构更清晰**：工具直接定义，装饰器自动注册
3. **维护成本更低**：不需要维护和测试未使用的代码
4. **符合 YAGNI 原则**：不实现当前用不到的功能

## 总结

- 删除了未使用的 `InternalMCPClient` 和 `ExternalMCPClient`
- 保留了 `MCPClientBase` 作为接口定义，供未来扩展
- 当前架构更简单：工具直接定义，装饰器自动注册
- 如果未来需要接入外部 MCP 服务器，可以再实现客户端
