# Skill 概念澄清

> 版本：2.0  
> 日期：2026-04-02  
> 状态：已更新执行流程详解

**最新更新（v2.0）**：
- 新增 Skill 执行流程详解
- 明确 LLM 推理过程
- 强调 Skill 是 LLM 驱动，非简单函数

## 一、Skill 的定义

### 1.1 什么是 Skill？

**Skill（技能）是一种基于 LLM 的复合能力**，它包含：

1. **Prompt 模板**：定义任务的指令和上下文
2. **内部工具集**：Skill 可以调用的工具列表
3. **LLM 执行**：由 LLM 理解任务、调用工具、生成结果

### 1.2 Skill vs Tool

| 维度 | Tool（工具） | Skill（技能） |
|------|-------------|--------------|
| **本质** | 确定性函数 | LLM 驱动的能力 |
| **执行方式** | 直接调用代码 | LLM 推理 + 工具调用 |
| **输入** | 结构化参数 | 自然语言 + 结构化参数 |
| **输出** | 确定性结果 | LLM 生成的结果 |
| **复杂度** | 简单、原子化 | 复杂、组合式 |
| **示例** | `query_policy_basic(policy_id)` | `analyze_policy_risk(policy_id, context)` |

### 1.3 示例对比

#### Tool 示例（确定性）

```python
# Tool: 查询保单基本信息
@tool(name="query_policy_basic")
async def query_policy_basic(policy_id: str) -> dict:
    """查询保单基本信息"""
    client = get_internal_api_client()
    data = await client.get(f"/policy-service/api/v1/policies/{policy_id}/basic")
    return {
        "policy_id": data["policyId"],
        "status": data["status"],
        "effective_date": data["effectiveDate"],
    }

# 调用：
result = await tool_gateway.invoke("query_policy_basic", {"policy_id": "P2024001"})
# 返回：{"policy_id": "P2024001", "status": "ACTIVE", ...}
```

#### Skill 示例（LLM 驱动）

```python
# Skill: 分析保单风险
skill = {
    "name": "analyze_policy_risk",
    "description": "分析保单的风险等级",
    "prompt_template": """
你是保险风险分析专家。请分析保单 {policy_id} 的风险等级。

分析步骤：
1. 查询保单基本信息
2. 查询历史理赔记录
3. 查询客户信用评分
4. 综合评估风险等级（低/中/高）

请使用以下工具：
- query_policy_basic: 查询保单信息
- list_claims_by_policy: 查询理赔记录
- query_customer_credit: 查询客户信用

最后给出风险等级和理由。
    """,
    "available_tools": [
        "query_policy_basic",
        "list_claims_by_policy",
        "query_customer_credit",
    ],
    "llm_config": {
        "model": "gpt-4",
        "temperature": 0.3,
    },
}

# 调用：
result = await skill_gateway.invoke(
    "analyze_policy_risk",
    {"policy_id": "P2024001"},
    context=context,
)

# LLM 执行流程：
# 1. LLM 读取 prompt 和任务
# 2. LLM 决定调用 query_policy_basic("P2024001")
# 3. LLM 决定调用 list_claims_by_policy("P2024001")
# 4. LLM 决定调用 query_customer_credit(...)
# 5. LLM 综合信息，生成分析报告

# 返回：
{
    "risk_level": "中",
    "reason": "该保单客户有 2 次理赔记录，但金额较小，信用评分良好，综合评估为中等风险。",
    "details": {
        "policy_status": "ACTIVE",
        "claim_count": 2,
        "credit_score": 750,
    }
}
```

---

## 二、Skill 的架构设计

### 2.1 Skill 的组成

```
┌─────────────────────────────────────────────────────────┐
│                    Skill Definition                      │
│  ┌───────────────────────────────────────────────────┐  │
│  │  name: "analyze_policy_risk"                      │  │
│  │  description: "分析保单风险等级"                   │  │
│  │  prompt_template: "你是保险风险分析专家..."       │  │
│  │  available_tools: [                               │  │
│  │    "query_policy_basic",                          │  │
│  │    "list_claims_by_policy",                       │  │
│  │    "query_customer_credit"                        │  │
│  │  ]                                                 │  │
│  │  llm_config: {model: "gpt-4", temperature: 0.3}  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│                  Skill Executor                          │
│  1. 渲染 prompt 模板                                     │
│  2. 从 tool_gateway 获取可用工具                         │
│  3. 创建 LLM Agent（带指定工具）                         │
│  4. 执行 Agent（LLM 推理 + 工具调用）                    │
│  5. 返回结果                                             │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│                  LLM Agent (LangGraph)                   │
│  - 理解任务（基于 prompt）                               │
│  - 决策调用哪些工具（动态推理）                          │
│  - 调用工具获取信息                                      │
│  - 综合信息生成结果                                      │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│                  Tool Gateway                            │
│  - query_policy_basic                                    │
│  - list_claims_by_policy                                 │
│  - query_customer_credit                                 │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Skill 执行流程详解

```
用户调用 Skill
    ↓
tool_gateway.invoke("analyze_policy_risk", {"policy_id": "P001"})
    ↓
SkillAdapter.invoke_tool()
    ↓
1. 渲染 prompt 模板
   "你是保险风险分析专家。请分析保单 P001 的风险等级..."
    ↓
2. 从 tool_gateway 获取可用工具
   [query_policy_basic, list_claims_by_policy, query_customer_credit]
    ↓
3. 创建 LLM Agent
   agent = create_react_agent(model=llm, tools=tool_functions)
    ↓
4. 执行 Agent
   result = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    ↓
   LLM 推理过程：
   - LLM 读取 prompt，理解任务
   - LLM 决定：先调用 query_policy_basic("P001")
   - Tool Gateway 执行工具，返回结果
   - LLM 决定：再调用 list_claims_by_policy("P001")
   - Tool Gateway 执行工具，返回结果
   - LLM 决定：再调用 query_customer_credit(...)
   - Tool Gateway 执行工具，返回结果
   - LLM 综合所有信息，生成分析报告
    ↓
5. 返回结果
   {
     "skill": "analyze_policy_risk",
     "result": "该保单风险等级为【中】。理由如下：...",
     "tool_calls": 3
   }
```

### 2.2 Skill Adapter 重新设计

```python
# core/tool_service/adapters/skill_adapter.py
from __future__ import annotations
from typing import Any, Dict, List
from langgraph.prebuilt import create_react_agent
from core.ai_core.llm.client import llm_gateway
from core.ai_core.prompt.manager import prompt_gateway
from shared.logging.logger import get_logger
from .base import ToolAdapter
from ..types import ToolMetadata, ToolContext, ToolType

logger = get_logger(__name__)


class SkillDefinition:
    """Skill 定义"""
    
    def __init__(
        self,
        name: str,
        description: str,
        prompt_template: str,
        available_tools: List[str],
        llm_config: dict | None = None,
        input_schema: dict | None = None,
    ):
        self.name = name
        self.description = description
        self.prompt_template = prompt_template
        self.available_tools = available_tools
        self.llm_config = llm_config or {"model": "gpt-4", "temperature": 0.3}
        self.input_schema = input_schema or {}


class SkillAdapter(ToolAdapter):
    """
    Skill 工具适配器（重新设计）。
    
    Skill 是基于 LLM 的复合能力：
    - Prompt 模板
    - 可用工具列表
    - LLM 执行
    """
    
    def __init__(self, domain: str, tool_gateway):
        """
        Args:
            domain: 域名
            tool_gateway: 工具网关（用于获取可用工具）
        """
        self.domain = domain
        self.tool_gateway = tool_gateway
        self._skills: Dict[str, SkillDefinition] = {}
    
    def register_skill(self, skill_def: SkillDefinition):
        """
        注册一个 Skill。
        
        Args:
            skill_def: Skill 定义
        """
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
            metadata = ToolMetadata(
                name=name,
                description=skill_def.description,
                type=ToolType.INTERNAL,
                category=self.domain,
                input_schema=skill_def.input_schema,
                source_domain=self.domain,
                tags=["skill", "llm", self.domain],
            )
            tools.append(metadata)
        
        logger.info(
            "skill_tools_loaded",
            domain=self.domain,
            count=len(tools),
        )
        
        return tools
    
    async def validate_tool(self, metadata: ToolMetadata) -> tuple[bool, list[str]]:
        """验证 Skill"""
        errors = []
        
        if not metadata.name:
            errors.append("Skill 名称不能为空")
        
        if metadata.name not in self._skills:
            errors.append(f"Skill 未注册: {metadata.name}")
        else:
            skill_def = self._skills[metadata.name]
            
            # 验证 prompt 模板
            if not skill_def.prompt_template:
                errors.append(f"Skill prompt 模板不能为空: {metadata.name}")
            
            # 验证可用工具
            if not skill_def.available_tools:
                errors.append(f"Skill 必须指定可用工具: {metadata.name}")
            
            # 验证工具是否存在
            all_tool_names = {t["name"] for t in self.tool_gateway.list_tools()}
            for tool_name in skill_def.available_tools:
                if tool_name not in all_tool_names:
                    errors.append(f"Skill 引用的工具不存在: {tool_name}")
        
        return (len(errors) == 0, errors)
    
    async def invoke_tool(
        self,
        metadata: ToolMetadata,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Any:
        """
        执行 Skill（通过 LLM Agent）。
        
        执行流程：
        1. 渲染 prompt 模板
        2. 获取可用工具
        3. 创建 LLM Agent
        4. 执行 Agent
        5. 返回结果
        """
        skill_def = self._skills.get(metadata.name)
        if not skill_def:
            raise ValueError(f"Skill not found: {metadata.name}")
        
        # 1. 渲染 prompt 模板
        prompt = self._render_prompt(skill_def.prompt_template, arguments)
        
        # 2. 获取可用工具（从 tool_gateway）
        tool_functions = []
        for tool_name in skill_def.available_tools:
            tool_entry = self.tool_gateway._tools.get(tool_name)
            if tool_entry:
                tool_functions.append(self._wrap_tool_for_agent(tool_entry, context))
        
        if not tool_functions:
            raise ValueError(f"No available tools for skill: {metadata.name}")
        
        # 3. 创建 LLM Agent
        llm = llm_gateway.get_chat([], scene=skill_def.llm_config.get("model", "gpt-4"))
        
        agent = create_react_agent(
            model=llm,
            tools=tool_functions,
        )
        
        # 4. 执行 Agent
        logger.info(
            "skill_executing",
            skill_name=metadata.name,
            tool_count=len(tool_functions),
        )
        
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": prompt}]
        })
        
        # 5. 提取结果
        final_message = result["messages"][-1]
        
        return {
            "skill": metadata.name,
            "result": final_message.content,
            "tool_calls": len([m for m in result["messages"] if hasattr(m, "tool_calls")]),
        }
    
    def _render_prompt(self, template: str, arguments: dict) -> str:
        """渲染 prompt 模板"""
        try:
            return template.format(**arguments)
        except KeyError as e:
            raise ValueError(f"Prompt template missing argument: {e}")
    
    def _wrap_tool_for_agent(self, tool_entry, context: ToolContext):
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
    
    def get_adapter_type(self) -> str:
        return "skill"
```


---

## 三、Skill 的使用示例

### 3.1 定义 Skill

```python
# domain_agents/policy/skills/policy_skills.py
from core.tool_service.adapters.skill_adapter import SkillDefinition

# Skill 1: 分析保单风险
analyze_policy_risk_skill = SkillDefinition(
    name="analyze_policy_risk",
    description="分析保单的风险等级（低/中/高）",
    prompt_template="""
你是保险风险分析专家。请分析保单 {policy_id} 的风险等级。

分析步骤：
1. 查询保单基本信息（状态、金额、期限等）
2. 查询历史理赔记录（次数、金额）
3. 查询客户信用评分
4. 综合评估风险等级

可用工具：
- query_policy_basic: 查询保单基本信息
- list_claims_by_policy: 查询理赔记录
- query_customer_credit: 查询客户信用

请给出风险等级（低/中/高）和详细理由。
    """,
    available_tools=[
        "query_policy_basic",
        "list_claims_by_policy",
        "query_customer_credit",
    ],
    llm_config={
        "model": "gpt-4",
        "temperature": 0.3,
    },
    input_schema={
        "type": "object",
        "properties": {
            "policy_id": {"type": "string", "description": "保单号"},
        },
        "required": ["policy_id"],
    },
)


# Skill 2: 生成保单推荐
recommend_policy_skill = SkillDefinition(
    name="recommend_policy",
    description="根据客户信息推荐合适的保单",
    prompt_template="""
你是保险产品推荐专家。请根据客户 {customer_id} 的信息推荐合适的保单。

分析步骤：
1. 查询客户基本信息（年龄、职业、收入等）
2. 查询客户现有保单
3. 分析客户需求和风险偏好
4. 推荐 2-3 款合适的保单产品

可用工具：
- query_customer_info: 查询客户信息
- list_policies_by_company: 查询客户现有保单
- search_faq: 搜索产品信息

请给出推荐理由和产品特点。
    """,
    available_tools=[
        "query_customer_info",
        "list_policies_by_company",
        "search_faq",
    ],
    llm_config={
        "model": "gpt-4",
        "temperature": 0.5,
    },
    input_schema={
        "type": "object",
        "properties": {
            "customer_id": {"type": "string", "description": "客户 ID"},
        },
        "required": ["customer_id"],
    },
)
```

### 3.2 注册 Skill

```python
# app/gateway/lifespan.py
from core.tool_service.adapters.skill_adapter import SkillAdapter
from domain_agents.policy.skills.policy_skills import (
    analyze_policy_risk_skill,
    recommend_policy_skill,
)

@asynccontextmanager
async def lifespan(_: FastAPI):
    # ... 先注册所有 Tool ...
    
    # 注册 Skill Adapter
    policy_skill_adapter = SkillAdapter(domain="policy", tool_gateway=tool_gateway)
    
    # 注册具体的 Skill
    policy_skill_adapter.register_skill(analyze_policy_risk_skill)
    policy_skill_adapter.register_skill(recommend_policy_skill)
    
    # 加载 Skill 到 tool_gateway
    tool_gateway.register_adapter(policy_skill_adapter)
    await tool_gateway.load_tools_from_adapter(policy_skill_adapter)
    
    yield
```

### 3.3 调用 Skill

```python
# 在 Agent 或 API 中调用 Skill
from core.tool_service.registry import tool_gateway
from core.tool_service.types import ToolContext

async def analyze_policy(policy_id: str, context: ToolContext):
    """分析保单风险"""
    
    # 调用 Skill（就像调用普通工具一样）
    result = await tool_gateway.invoke(
        tool_name="analyze_policy_risk",
        arguments={"policy_id": policy_id},
        context=context,
    )
    
    return result

# 调用示例
context = ToolContext(tenant_id="tenant_a", user_id="user_123")
result = await analyze_policy("P2024001", context)

# 返回：
{
    "skill": "analyze_policy_risk",
    "result": "该保单风险等级为【中】。理由如下：\n1. 保单状态正常，承保金额适中\n2. 客户有 2 次理赔记录，但金额较小\n3. 客户信用评分 750，属于良好水平\n综合评估为中等风险。",
    "tool_calls": 3  # LLM 调用了 3 次工具
}
```

---

## 四、Skill vs Tool 的使用场景

### 4.1 何时使用 Tool？

✅ **使用 Tool 的场景**：

1. **确定性操作**：
   - 查询数据库
   - 调用 API
   - 数据转换
   - 计算逻辑

2. **简单、原子化**：
   - 单一职责
   - 输入输出明确
   - 不需要推理

3. **性能要求高**：
   - 需要快速响应
   - 不能有 LLM 延迟

**示例**：
```python
# Tool: 查询保单
@tool(name="query_policy_basic")
async def query_policy_basic(policy_id: str) -> dict:
    return await db.query(...)

# Tool: 格式化日期
@tool(name="format_date")
def format_date(date_str: str, format: str) -> str:
    return datetime.strptime(date_str, "%Y-%m-%d").strftime(format)
```

### 4.2 何时使用 Skill？

✅ **使用 Skill 的场景**：

1. **需要推理和决策**：
   - 分析、评估、判断
   - 需要综合多个信息源
   - 需要上下文理解

2. **复杂、组合式任务**：
   - 需要调用多个工具
   - 需要动态决策调用顺序
   - 需要生成自然语言结果

3. **灵活性要求高**：
   - 任务步骤不固定
   - 需要根据情况调整
   - 需要处理异常情况

**示例**：
```python
# Skill: 分析保单风险
analyze_policy_risk_skill = SkillDefinition(
    name="analyze_policy_risk",
    prompt_template="分析保单风险...",
    available_tools=["query_policy_basic", "list_claims_by_policy", ...],
)

# Skill: 生成理赔报告
generate_claim_report_skill = SkillDefinition(
    name="generate_claim_report",
    prompt_template="生成理赔报告...",
    available_tools=["query_claim_status", "query_policy_basic", ...],
)
```

### 4.3 对比表

| 场景 | 使用 Tool | 使用 Skill |
|------|----------|-----------|
| 查询保单信息 | ✅ | ❌ |
| 分析保单风险 | ❌ | ✅ |
| 计算保费 | ✅ | ❌ |
| 推荐保单产品 | ❌ | ✅ |
| 格式化数据 | ✅ | ❌ |
| 生成理赔报告 | ❌ | ✅ |
| 调用第三方 API | ✅ | ❌ |
| 客户咨询回答 | ❌ | ✅ |

---

## 五、架构层次

```
┌─────────────────────────────────────────────────────────┐
│                    LangGraph Agent                       │
│  - 顶层决策和编排                                        │
│  - 可以调用 Tool 和 Skill                                │
└────────────────────────┬────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                                 ▼
┌──────────────────┐            ┌──────────────────┐
│      Tool        │            │      Skill       │
│  - 确定性函数     │            │  - LLM 驱动      │
│  - 直接执行       │            │  - 可调用 Tool   │
└──────────────────┘            └────────┬─────────┘
                                         │
                                         ▼
                                ┌──────────────────┐
                                │  LLM Agent       │
                                │  - 推理          │
                                │  - 调用 Tool     │
                                │  - 生成结果      │
                                └──────────────────┘
```

**关键点**：
1. **Tool 是原子能力**：直接执行，确定性
2. **Skill 是复合能力**：LLM 驱动，可以调用多个 Tool
3. **Agent 是顶层编排**：可以调用 Tool 和 Skill

---

## 六、总结

### 6.1 核心概念

- **Tool**：确定性函数，直接执行
- **Skill**：LLM 驱动的复合能力，Prompt + Tools + LLM
- **Agent**：顶层编排，决策调用 Tool 和 Skill

### 6.2 Skill 的本质

```
Skill = Prompt Template + Available Tools + LLM Execution
```

**不是**：简单的 Python 函数  
**而是**：基于 LLM 的智能能力

### 6.3 实现要点

1. **Skill 定义**：
   - 名称和描述
   - Prompt 模板
   - 可用工具列表
   - LLM 配置

2. **Skill 执行**：
   - 渲染 prompt
   - 创建 LLM Agent（带指定工具）
   - 执行 Agent
   - 返回结果

3. **Skill 注册**：
   - 通过 SkillAdapter 注册
   - 加载到 tool_gateway
   - 像普通工具一样调用

---

**文档维护者**：Agent Platform Team  
**最后更新**：2026-04-02
