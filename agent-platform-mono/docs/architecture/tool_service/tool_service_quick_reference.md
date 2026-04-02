# Tool Service 快速参考

> 版本：2.0  
> 日期：2026-04-02  
> 更新：v6.0 目录结构（按工具类型划分 + Base 继承）

本文档提供 Tool Service 架构的快速参考。

---

## 一、核心概念速查

### 1.1 Tool vs Skill

| | Tool | Skill |
|---|------|-------|
| **是什么** | 确定性函数 | LLM Agent |
| **执行** | 直接调用 | LLM 推理 + 工具调用 |
| **示例** | `query_policy_basic(id)` | `analyze_policy_risk(id)` |

### 1.2 Adapter 类型

| Adapter | 用途 | 本质 |
|---------|------|------|
| **External MCP** | 对接外部 MCP Server | MCP 协议客户端 |
| **Internal MCP** | 对接内部微服务 | HTTP Client + MCP 封装 |
| **Skill** | 执行 LLM 驱动的 Skill | LLM Agent 执行器 |
| **Function** | 调用 Python 函数 | 函数包装器 |

---

## 二、快速记忆

### 2.1 一句话定义

```
Tool    = 函数调用
Skill   = LLM Agent（Prompt + Tools + LLM）
MCP     = 协议抽象（External 和 Internal）
Adapter = 适配不同来源的工具
```

### 2.2 架构层次

```
LangGraph Agent（顶层编排）
    ↓
Tool Runtime（ToolGateway + ToolRouter + PermissionChecker）
    ↓
Adapters（External MCP / Internal MCP / Skill / Function）
    ↓
执行层（外部服务 / 内部服务 / LLM / 函数）
```

### 2.3 MCP 的两种用途

```
MCP 协议
    ├── External MCP → 对接外部 MCP Server
    └── Internal MCP → 对接内部微服务（HTTP + MCP 封装）
```

---

## 三、常见问题

### Q1: Skill 是什么？

**A**: Skill 不是简单的 Python 函数，而是基于 LLM 的复合能力。

```python
# ❌ Skill 不是这样
def analyze_risk(policy_id):
    return "高风险"

# ✅ Skill 是这样
skill = SkillDefinition(
    prompt="分析保单风险...",
    tools=["query_policy", "list_claims"],
    llm_config={...}
)
# LLM 会推理、调用工具、生成结果
```

### Q2: Internal MCP Adapter 是什么？

**A**: 本质是 HTTP Adapter 的 MCP 协议封装。

```
Internal MCP Adapter = HTTP Client + MCP 协议抽象 + 上下文透传
```

### Q3: 为什么要用 Adapter？

**A**: 统一抽象，解耦实现，灵活扩展。

```python
# 业务层只看到统一接口
await tool_gateway.invoke("query_policy_basic", {...})

# 底层可以是：
# - External MCP Server
# - Internal HTTP Service
# - Python Function
# - LLM Skill
```

### Q4: Tool 和 Skill 如何选择？

| 场景 | 使用 |
|------|------|
| 查询数据库 | Tool |
| 调用 API | Tool |
| 分析、评估、判断 | Skill |
| 需要推理和决策 | Skill |
| 需要调用多个工具 | Skill |

---

## 四、代码示例

### 4.1 注册 Internal MCP 工具

```python
# 创建 Adapter
policy_adapter = InternalMCPAdapter(
    domain="policy",
    service_name="policy-service",
    base_url="http://policy-service",
)

# 注册工具
policy_adapter.register_tool(
    name="query_policy_basic",
    description="查询保单基本信息",
    endpoint="/api/v1/policies/{policy_id}/basic",
    method="GET",
)

# 加载到 tool_gateway
tool_gateway.register_adapter(policy_adapter)
await tool_gateway.load_tools_from_adapter(policy_adapter)
```

### 4.2 注册 Skill

```python
# 定义 Skill
analyze_risk_skill = SkillDefinition(
    name="analyze_policy_risk",
    description="分析保单风险等级",
    prompt_template="""
你是保险风险分析专家。请分析保单 {policy_id} 的风险等级。
可用工具：query_policy_basic, list_claims, query_credit
    """,
    available_tools=["query_policy_basic", "list_claims", "query_credit"],
    llm_config={"model": "gpt-4", "temperature": 0.3},
)

# 创建 Adapter
skill_adapter = SkillAdapter(domain="policy", tool_gateway=tool_gateway)
skill_adapter.register_skill(analyze_risk_skill)

# 加载到 tool_gateway
tool_gateway.register_adapter(skill_adapter)
await tool_gateway.load_tools_from_adapter(skill_adapter)
```

### 4.3 调用工具

```python
# 创建上下文
context = ToolContext(
    tenant_id="tenant_a",
    user_id="user_123",
    channel_id="web",
)

# 调用 Tool（确定性）
result = await tool_gateway.invoke(
    tool_name="query_policy_basic",
    arguments={"policy_id": "P2024001"},
    context=context,
)
# 返回：{"policy_id": "P2024001", "status": "ACTIVE", ...}

# 调用 Skill（LLM 驱动）
result = await tool_gateway.invoke(
    tool_name="analyze_policy_risk",
    arguments={"policy_id": "P2024001"},
    context=context,
)
# 返回：
# {
#     "skill": "analyze_policy_risk",
#     "result": "该保单风险等级为【中】。理由如下：...",
#     "tool_calls": 3
# }
```

---

## 五、目录结构

```
core/tool_service/
├── __init__.py                       # 导出统一接口
├── types.py                          # 通用类型定义
├── registry.py                       # ToolGateway
├── router.py                         # ToolRouter
│
├── base/                             # 基础抽象层
│   ├── adapter.py                    # ToolAdapter 基类
│   ├── validator.py                  # BaseValidator 基类
│   └── permissions.py                # BasePermissionChecker 基类
│
├── external_mcp/                     # 外部 MCP 工具
│   ├── adapter.py
│   ├── validator.py
│   ├── client.py
│   └── types.py
│
├── internal_mcp/                     # 内部 MCP 工具
│   ├── adapter.py
│   ├── validator.py
│   ├── client.py
│   └── types.py
│
├── skill/                            # Skill 工具
│   ├── adapter.py
│   ├── validator.py
│   ├── executor.py
│   └── types.py
│
└── function/                         # Function 工具
    ├── adapter.py
    ├── validator.py
    └── types.py
```

**设计原则**：按工具类型划分 + Base 继承

---

## 六、关键文档

| 文档 | 用途 |
|------|------|
| `tool_service_final_design.md` | 完整架构设计（v6.0，必读） |
| `skill_concept_clarification.md` | Skill 概念澄清 |
| `tool_service_updates_v6.md` | v6.0 更新说明（目录结构变化） |
| `tool_service_updates_v5.md` | v5.0 更新说明（概念澄清） |
| `tool_service_quick_reference.md` | 快速参考（本文档） |

---

## 七、记忆口诀

```
Tool 是函数，Skill 是 Agent
MCP 有两种，External 和 Internal
Internal 本质是 HTTP 封装
Adapter 统一，业务解耦
```

---

**文档维护者**：Agent Platform Team  
**最后更新**：2026-04-02
