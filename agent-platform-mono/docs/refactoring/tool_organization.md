# 工具组织架构改进

## 问题

在之前的架构中，存在两个问题：

1. **domain_agents 中没有 skills 目录**
   - 只有 `tools/` 目录用于 MCP 工具
   - 没有地方放置简单的 Skill 工具
   - 导致所有工具都必须使用 MCP，即使是简单的函数

2. **缺少公共工具存放位置**
   - 跨领域的通用工具没有统一的存放位置
   - 可能导致工具重复实现
   - 不利于工具复用

## 解决方案

### 1. 在 domain_agents 中添加 skills 目录

为每个领域添加 `skills/` 目录，用于存放简单的函数式工具。

**目录结构**：
```
domain_agents/
  policy/
    tools/          # MCP 工具（复杂业务逻辑）
      __init__.py
      policy_tools.py
    skills/         # Skill 工具（简单函数）
      __init__.py
      policy_skills.py
    register.py
    memory_config.py
```

**何时使用 skills**：
- 简单的数据转换
- 格式化和验证
- 不需要外部调用的逻辑
- 纯函数式操作

**示例**：
```python
# domain_agents/policy/skills/policy_skills.py
from core.tool_service.skills.base import skill

@skill(name="format_policy_id")
async def format_policy_id(args: dict) -> dict:
    """格式化保单号：去除空格、转大写"""
    pid = str(args.get("policy_id", "")).strip().upper()
    return {"normalized": pid}

@skill(name="validate_policy_status")
async def validate_policy_status(args: dict) -> dict:
    """验证保单状态是否有效"""
    status = str(args.get("status", "")).upper()
    valid_statuses = {"ACTIVE", "EXPIRED", "CANCELLED", "PENDING"}
    return {
        "valid": status in valid_statuses,
        "status": status
    }
```

### 2. 创建 common_tools 目录

创建顶层的 `common_tools/` 目录，用于存放跨领域的通用工具。

**目录结构**：
```
common_tools/
  mcp/              # 公共 MCP 工具
    __init__.py
    time_tools.py       # 时间处理
    text_tools.py       # 文本处理
    math_tools.py       # 数学计算
  skills/           # 公共 Skill 工具
    __init__.py
    format_skills.py    # 格式化工具
    validation_skills.py # 验证工具
  README.md
```

**何时使用 common_tools**：

✅ 应该放在 common_tools：
- 跨多个领域使用的工具
- 与业务领域无关的工具
- 纯技术性功能
- 可独立测试的工具

示例：
- 时间日期处理
- 文本格式化
- 数据验证
- 数学计算
- 通用 API 调用（天气、汇率等）

❌ 应该放在 domain_agents：
- 领域特定的工具
- 包含业务逻辑的工具
- 需要调用特定业务服务的工具
- 依赖领域数据模型的工具

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

@mcp.tool()
async def calculate_date_diff(start: str, end: str) -> dict:
    """计算两个日期之间的天数差"""
    # 通用日期计算逻辑
    return {"days": 10}
```

```python
# common_tools/skills/format_skills.py
from core.tool_service.skills.base import skill

@skill(name="format_phone_number")
async def format_phone_number(args: dict) -> dict:
    """格式化电话号码"""
    phone = args.get("phone", "")
    # 通用格式化逻辑
    return {"formatted": "138-1234-5678"}

@skill(name="format_currency")
async def format_currency(args: dict) -> dict:
    """格式化货币金额"""
    amount = args.get("amount", 0)
    currency = args.get("currency", "CNY")
    # 通用货币格式化逻辑
    return {"formatted": "¥1,000.00"}
```

## 修改内容

### 新增目录

1. **domain_agents/*/skills/**
   - `domain_agents/policy/skills/`
   - `domain_agents/claim/skills/`
   - `domain_agents/customer/skills/`

2. **common_tools/**
   - `common_tools/mcp/`
   - `common_tools/skills/`

### 新增文件

1. **示例 Skill 工具**
   - `domain_agents/policy/skills/example_skills.py`
   - `common_tools/skills/format_skills.py`

2. **示例 MCP 工具**
   - `common_tools/mcp/time_tools.py`

3. **文档**
   - `common_tools/README.md`

## 工具分类决策树

```
是否跨多个领域使用？
├─ 是 → 是否包含业务逻辑？
│       ├─ 否 → common_tools/
│       └─ 是 → 考虑抽象业务逻辑，或保留在各领域
└─ 否 → 是否需要外部调用？
        ├─ 是 → domain_agents/*/tools/ (MCP)
        └─ 否 → domain_agents/*/skills/ (Skill)
```

## 工具注册

### 领域工具注册

```python
# domain_agents/policy/register.py
from domain_agents.policy.tools.policy_tools import policy_tools
from domain_agents.policy.skills import policy_skills  # 导入即注册

def register():
    agent_gateway.register(AgentMeta(
        agent_id="policy-assistant",
        tools=[
            # 领域 MCP 工具
            "mcp:query_policy_basic",
            "mcp:list_policies_by_company",
            # 领域 Skill 工具
            "format_policy_id",
            "validate_policy_status",
        ],
        # ...
    ))
```

### 公共工具注册

```python
# app/gateway/lifespan.py

# 导入公共 Skills（导入即自动注册）
from core.tool_service.common_tools.skills import format_skills

# 如果有公共 MCP 工具，也可以注册
# from core.tool_service.common_tools.mcp import time_tools
```

## 最佳实践

### 1. 工具命名

- **领域工具**：使用领域前缀
  - MCP: `policy:query_basic`, `claim:query_status`
  - Skill: `format_policy_id`, `validate_claim_amount`

- **公共工具**：使用通用名称
  - MCP: `common-time:get_current_time`
  - Skill: `format_phone_number`, `format_currency`

### 2. 工具迁移

如果发现某个工具被多个领域使用：

1. 评估是否包含业务逻辑
2. 如果不包含，迁移到 `common_tools/`
3. 更新所有引用
4. 更新测试

### 3. 避免过度抽象

- 不要过早地将工具移到 common_tools
- 等到确实有 2-3 个领域需要时再迁移
- 保持工具的独立性和可测试性

## 优势

1. **结构清晰**：MCP 和 Skill 分离，职责明确
2. **易于复用**：公共工具统一管理
3. **避免重复**：跨领域工具只实现一次
4. **易于维护**：工具分类清晰，便于查找和修改
5. **灵活扩展**：新增工具有明确的存放位置

## 示例项目结构

```
agent-platform-mono/
├── common_tools/              # 公共工具
│   ├── mcp/
│   │   ├── time_tools.py
│   │   └── text_tools.py
│   ├── skills/
│   │   ├── format_skills.py
│   │   └── validation_skills.py
│   └── README.md
├── domain_agents/             # 领域 Agent
│   ├── policy/
│   │   ├── tools/            # MCP 工具
│   │   │   └── policy_tools.py
│   │   ├── skills/           # Skill 工具
│   │   │   └── policy_skills.py
│   │   └── register.py
│   ├── claim/
│   │   ├── tools/
│   │   ├── skills/
│   │   └── register.py
│   └── customer/
│       ├── tools/
│       ├── skills/
│       └── register.py
└── core/
    └── tool_service/          # 工具基础设施
        ├── registry.py
        ├── mcp/
        └── skills/
```
