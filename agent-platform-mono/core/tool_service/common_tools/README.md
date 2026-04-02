# 公共工具 (Common Tools)

## 概述

`core/tool_service/common_tools/` 目录存放跨领域的通用工具，可被多个 domain agent 共享使用。

这些工具属于 tool_service 的一部分，但不是基础设施（registry、mcp client），而是具体的工具实现。

## 为什么放在 tool_service 下？

- `core/tool_service/` 是工具相关的模块
- `common_tools/` 虽然是具体工具，但是跨领域的公共工具
- 与 `domain_agents/` 中的领域工具形成对比
- 便于统一管理和发现

## 目录结构

```
core/tool_service/
├── registry.py          # 工具注册表（基础设施）
├── mcp/                 # MCP 客户端（基础设施）
├── skills/              # Skill 装饰器（基础设施）
└── common_tools/        # 公共工具（具体实现）
    ├── mcp/             # 公共 MCP 工具
    │   ├── __init__.py
    │   ├── time_tools.py
    │   └── text_tools.py
    └── skills/          # 公共 Skill 工具
        ├── __init__.py
        ├── format_skills.py
        └── validation_skills.py
```

## 何时使用公共工具

### 应该放在 core/tool_service/common_tools/

✅ 跨多个领域使用的工具
- 时间日期处理
- 文本格式化
- 数据验证
- 数学计算
- 通用 API 调用（如天气、汇率）

✅ 与业务领域无关的工具
- 不包含领域知识
- 纯技术性功能
- 可独立测试

### 应该放在 domain_agents/

❌ 领域特定的工具
- 保单查询（policy）
- 理赔处理（claim）
- 客户服务（customer）

❌ 包含业务逻辑的工具
- 需要调用特定业务服务
- 包含领域规则
- 依赖领域数据模型

## 工具类型

### 1. MCP 工具 (common_tools/mcp/)

适用于需要复杂逻辑或外部调用的通用工具。

**示例**：

```python
# core/tool_service/common_tools/mcp/time_tools.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("common-time")

@mcp.tool()
async def get_current_time(timezone: str = "UTC") -> dict:
    """获取指定时区的当前时间"""
    # 实现逻辑
    return {"time": "...", "timezone": timezone}

@mcp.tool()
async def calculate_date_diff(start: str, end: str) -> dict:
    """计算两个日期之间的天数差"""
    # 实现逻辑
    return {"days": 10}
```

### 2. Skill 工具 (common_tools/skills/)

适用于简单的数据转换和验证。

**示例**：

```python
# core/tool_service/common_tools/skills/format_skills.py
from core.tool_service.skills.base import skill

@skill(name="format_phone_number")
async def format_phone_number(args: dict) -> dict:
    """格式化电话号码"""
    phone = args.get("phone", "")
    # 实现逻辑
    return {"formatted": "..."}

@skill(name="format_currency")
async def format_currency(args: dict) -> dict:
    """格式化货币金额"""
    amount = args.get("amount", 0)
    currency = args.get("currency", "CNY")
    # 实现逻辑
    return {"formatted": "¥1,000.00"}
```

## 工具注册机制

### 自动注册

工具通过装饰器**自动注册**，不需要手动调用注册函数：

1. **Skill 工具**：使用 `@skill` 装饰器
   ```python
   from core.tool_service.skills.base import skill
   
   @skill(name="format_phone_number")
   async def format_phone_number(args: dict) -> dict:
       """格式化电话号码"""
       # 装饰器会自动将工具注册到 tool_gateway
       return {"formatted": "..."}
   ```
   
   当模块被导入时，装饰器就会执行，工具自动注册。

2. **MCP 工具**：使用 FastMCP 的 `@mcp.tool()`
   ```python
   from mcp.server.fastmcp import FastMCP
   
   mcp = FastMCP("common-time")
   
   @mcp.tool()
   async def get_current_time(timezone: str = "UTC") -> dict:
       """获取当前时间"""
       # FastMCP 会管理这些工具
       return {"time": "..."}
   ```

### 使用公共工具

只需要在启动时导入模块，工具就会自动注册：

```python
# app/gateway/lifespan.py

# 导入 Skills（导入即自动注册）
from core.tool_service.common_tools.skills import format_skills

# 导入 MCP 工具（如果需要）
# from core.tool_service.common_tools.mcp import time_tools
```

然后在 Agent 配置中引用工具名称：

```python
# domain_agents/policy/register.py
def register():
    agent_gateway.register(AgentMeta(
        agent_id="policy-assistant",
        tools=[
            # 领域工具
            "mcp:query_policy_basic",
            "format_policy_id",
            # 公共工具（已通过导入自动注册）
            "format_phone_number",  # Skill
            "common-time:get_current_time",  # MCP
        ],
        # ...
    ))
```

## 最佳实践

### 1. 工具命名

- MCP 工具：使用描述性的动词短语
  - `get_current_time`
  - `calculate_date_diff`
  - `format_text`

- Skill 工具：使用 `动词_名词` 格式
  - `format_phone_number`
  - `validate_email`
  - `parse_json`

### 2. 文档注释

每个工具都应该有清晰的文档：

```python
@mcp.tool()
async def my_tool(arg1: str, arg2: int) -> dict:
    """
    工具的简短描述。
    
    详细说明工具的功能、使用场景。
    
    Args:
        arg1: 参数1的说明
        arg2: 参数2的说明
    
    Returns:
        返回值的说明
    
    Examples:
        >>> await my_tool("test", 123)
        {"result": "..."}
    """
    pass
```

### 3. 错误处理

```python
@mcp.tool()
async def my_tool(arg: str) -> dict:
    try:
        # 业务逻辑
        return {"result": "..."}
    except ValueError as e:
        return {"error": f"参数错误: {str(e)}"}
    except Exception as e:
        logger.error("tool_failed", tool="my_tool", error=str(e))
        return {"error": "执行失败，请稍后重试"}
```

### 4. 测试

为每个公共工具编写测试：

```python
# tests/core/tool_service/common_tools/test_time_tools.py
async def test_get_current_time():
    result = await get_current_time(timezone="Asia/Shanghai")
    assert "time" in result
    assert result["timezone"] == "Asia/Shanghai"
```

## 迁移指南

如果发现某个工具被多个领域使用，可以将其迁移到 common_tools：

1. 将工具文件移动到 `core/tool_service/common_tools/mcp/` 或 `core/tool_service/common_tools/skills/`
2. 更新导入路径
3. 在 `app/gateway/lifespan.py` 中导入模块
4. 更新测试文件路径
5. 更新文档

## 注意事项

1. **避免过度抽象**：不要过早地将工具移到 common_tools，等到确实有多个领域需要时再迁移
2. **保持独立性**：公共工具不应该依赖特定的领域模块
3. **版本管理**：公共工具的修改可能影响多个领域，需要谨慎测试
4. **文档完善**：公共工具需要更详细的文档，因为使用者可能不熟悉其实现
