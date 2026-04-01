# Batch 2 — Tool Service 层重构开发任务

## 概述

Tool Service 层是当前架构最大的缺口，需要统一 Skill + MCP 工具注册，建立标准执行层，支持 ReAct 和显式编排两种模式。

**前置依赖**: Batch 1 完成

---

## Task 2.1 — tool_service 注册表强化

**优先级**: P0  
**预计工时**: 4 天  
**依赖**: Batch 1 完成  
**被依赖**: 2.2, 2.3, 2.4, 3.3

### 目标

重写 `ToolRegistry`，统一 Skill + MCP 工具注册，`ToolCandidate.tool` 类型从 `Any` 改为 `str`，所有执行通过 `tool_gateway.invoke()` 路由。

### 实现清单

#### 1. `core/tool_service/registry.py` 重写

```python
@dataclass
class ToolMeta:
    name: str                      # 全局唯一，格式 skill:{name} 或 {provider}:{name}
    description: str
    keywords: list[str]
    input_schema: dict
    output_schema: dict
    provider: str                  # "skill" / "mcp" / "ext_{n}"
    source: Literal["skill", "mcp_internal", "mcp_external"]
    enabled: bool = True

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolMeta] = {}
        self._skill_funcs: dict[str, Callable] = {}
        self._mcp_providers: dict[str, McpProvider] = {}

    def register_skill(
        self,
        name: str,
        func: Callable,
        description: str = "",
        keywords: list[str] | None = None,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
    ) -> None:
        """
        注册 Skill 工具
        tool_name 格式：skill:{name}
        """

    async def register_mcp_provider(
        self,
        provider: str,
        mcp_provider: McpProvider,
    ) -> None:
        """
        注册 MCP Provider，自动发现其所有工具
        tool_name 格式：{provider}:{tool_name}
        """

    def list_tools(self, enabled_only: bool = True) -> list[ToolMeta]:
        """列出所有工具元信息"""

    async def invoke(
        self,
        tool_name: str,
        arguments: dict,
        *,
        tenant_id: str = "",
        timeout: float = 30.0,
    ) -> ToolInvokeResult:
        """
        统一执行入口，根据 tool_name 路由到对应执行器
        - skill:{name} → 调用 _skill_funcs[name]
        - {provider}:{name} → 调用 _mcp_providers[provider].call_tool(name, args)
        """

    def get_candidates(self, enabled_only: bool = True) -> list[ToolCandidate]:
        """返回可供 router 选择的工具候选列表"""

@dataclass
class ToolInvokeResult:
    tool_name: str
    status: Literal["success", "error"]
    output: Any
    duration_ms: int
    error: str = ""
    metadata: dict = field(default_factory=dict)

@dataclass
class ToolCandidate:
    name: str
    description: str
    keywords: list[str]
    tool: str              # 改为 tool_name，不再是 Callable
```

#### 2. `core/tool_service/skills/base.py` 装饰器增强

```python
def skill(
    name: str,
    description: str = "",
    keywords: list[str] | None = None,
    input_schema: dict | None = None,
    output_schema: dict | None = None,
):
    """
    @skill 装饰器，自动注册到全局 ToolRegistry
    
    示例：
    @skill(
        name="query_policy_basic",
        description="查询保单基本信息，包括状态、生效日期、承保金额",
        keywords=["保单", "查询", "状态", "生效", "到期"],
        input_schema={
            "type": "object",
            "properties": {
                "policy_id": {"type": "string", "description": "保单号"}
            },
            "required": ["policy_id"]
        },
    )
    async def query_policy_basic(args: dict) -> dict:
        ...
    """
    def decorator(func: Callable):
        tool_registry.register_skill(
            name=name,
            func=func,
            description=description or func.__doc__ or "",
            keywords=keywords or [],
            input_schema=input_schema or {},
            output_schema=output_schema or {},
        )
        return func
    return decorator
```

#### 3. domain_agents tools 迁移

迁移原则：

- 所有 `domain_agents/*/tools/*.py` 中的工具函数改用 `@skill` 装饰器
- `AgentMeta.tools` 字段改为存储 `tool_name` 字符串列表
- 不再直接将工具函数传入 LangGraph `ToolNode`

迁移示例（`domain_agents/insurance/tools/policy.py`）：

```python
# 旧代码
async def query_policy_basic(policy_id: str) -> dict:
    ...

# 新代码
from core.tool_service.skills.base import skill

@skill(
    name="query_policy_basic",
    description="查询保单基本信息",
    keywords=["保单", "查询", "状态"],
    input_schema={
        "type": "object",
        "properties": {
            "policy_id": {"type": "string"}
        },
        "required": ["policy_id"]
    },
)
async def query_policy_basic(args: dict) -> dict:
    policy_id = args["policy_id"]
    ...
```

PDF 解析工具示例（`domain_agents/doc/tools/doc_tools.py`）：

```python
from core.tool_service.skills.base import skill
from shared.libs.pdf import extract_text_from_pdf

@skill(
    name="parse_pdf",
    description="解析 PDF 文件，提取文本内容",
    keywords=["PDF", "解析", "文档", "提取"],
    input_schema={
        "type": "object",
        "properties": {
            "pdf_bytes": {
                "type": "string",
                "description": "PDF 文件的 base64 编码"
            }
        },
        "required": ["pdf_bytes"]
    },
)
async def parse_pdf(args: dict) -> dict:
    """
    解析 PDF 工具
    
    场景：doc_agent 需要解析用户上传的 PDF
    实现：内部调用 shared.libs.pdf，外部通过 tool_service 暴露
    特点：有租户隔离、有鉴权、有可观测性
    """
    import base64
    
    pdf_bytes = base64.b64decode(args["pdf_bytes"])
    
    # 直接调用 shared.libs 的解析能力
    text = extract_text_from_pdf(pdf_bytes)
    
    return {
        "text": text,
        "status": "success",
        "length": len(text),
    }
```

**注意**：
- IngestGateway 直接调用 `shared.libs.pdf`（内部调用，无需鉴权）
- doc_agent 通过 `@skill` 包装后调用（业务工具，需要鉴权和可观测性）
- 两者共享同一份解析实现，但调用路径不同

`AgentMeta` 更新：

```python
# domain_agents/insurance/meta.py
meta = AgentMeta(
    name="insurance_agent",
    tools=["skill:query_policy_basic", "skill:search_faq"],  # 改为 tool_name 列表
    ...
)
```

#### 4. `core/tool_service/client/gateway.py` 更新

`ToolGateway` 增加 `invoke` 方法：

```python
class ToolGateway:
    async def invoke(
        self,
        tool_name: str,
        arguments: dict,
        *,
        tenant_id: str = "",
        timeout: float = 30.0,
    ) -> ToolInvokeResult:
        """调用 ToolRegistry.invoke()"""
        return await self.registry.invoke(
            tool_name=tool_name,
            arguments=arguments,
            tenant_id=tenant_id,
            timeout=timeout,
        )
```

### 验收标准

- [ ] Skill 注册单测（注册后可通过 `list_tools()` 查询）
- [ ] MCP Provider 注册单测（自动发现工具）
- [ ] `invoke("skill:test_tool", {...})` 路由到正确函数
- [ ] `invoke("mcp_provider:test_tool", {...})` 路由到 MCP
- [ ] `ToolCandidate.tool` 类型为 `str`
- [ ] domain_agents 至少一个 domain 完成工具迁移
- [ ] 迁移后的工具可通过 `tool_gateway.invoke()` 调用

---

## Task 2.2 — Tool 执行层：ToolExecutorGateway

**优先级**: P0  
**预计工时**: 3 天  
**依赖**: 2.1  
**被依赖**: 2.3, 2.4

### 目标

构建 `ToolExecutorGateway` 和 `ToolResultAggregator`，支持批量并发执行、失败隔离、多种聚合策略。

### 实现清单

#### 1. 目录结构

```
core/agent_engine/tools/
├── router.py          # 已有，tool 选择
├── executor.py        # 新增，ToolExecutorGateway
└── aggregator.py      # 新增，ToolResultAggregator
```

#### 2. `core/agent_engine/tools/executor.py`

```python
@dataclass
class ToolResult:
    tool_name: str
    status: Literal["success", "error"]
    output: str
    duration_ms: int
    error: str = ""
    metadata: dict = field(default_factory=dict)

class ToolExecutorGateway:
    def __init__(self, tool_gateway: ToolGateway):
        self.tool_gateway = tool_gateway

    async def run_batch(
        self,
        tool_names: list[str],
        input_text: str,
        arguments: dict | None = None,
        *,
        tenant_id: str,
        conversation_id: str,
        max_concurrency: int = 3,
        timeout_seconds: float = 10.0,
    ) -> list[ToolResult]:
        """
        并发执行多个 tool
        1. 如果 arguments 为空，从 input_text 推断参数（简单实现：传空 dict）
        2. 使用 asyncio.Semaphore 控制并发数
        3. 单个 tool 失败不影响其他 tool
        4. 超时自动取消
        """

    async def run_single(
        self,
        tool_name: str,
        arguments: dict,
        *,
        tenant_id: str,
        conversation_id: str,
        timeout_seconds: float = 10.0,
    ) -> ToolResult:
        """
        执行单个 tool
        1. 调用 tool_gateway.invoke()
        2. 捕获异常转为 ToolResult(status="error")
        3. 记录执行时长
        """

    async def _execute_one(
        self,
        tool_name: str,
        arguments: dict,
        tenant_id: str,
        timeout_seconds: float,
    ) -> ToolResult:
        """内部方法：执行单个工具并处理异常"""
```

执行失败处理逻辑：

```python
try:
    start = time.time()
    result = await asyncio.wait_for(
        self.tool_gateway.invoke(tool_name, arguments, tenant_id=tenant_id),
        timeout=timeout_seconds,
    )
    duration_ms = int((time.time() - start) * 1000)
    return ToolResult(
        tool_name=tool_name,
        status=result.status,
        output=str(result.output),
        duration_ms=duration_ms,
        error=result.error,
    )
except asyncio.TimeoutError:
    return ToolResult(
        tool_name=tool_name,
        status="error",
        output="",
        duration_ms=int(timeout_seconds * 1000),
        error=f"Tool execution timeout after {timeout_seconds}s",
    )
except Exception as e:
    return ToolResult(
        tool_name=tool_name,
        status="error",
        output="",
        duration_ms=0,
        error=str(e),
    )
```

#### 3. `core/agent_engine/tools/aggregator.py`

```python
class AggregationStrategy(StrEnum):
    CONCAT = "concat"              # 全部结果拼接（默认）
    FIRST_SUCCESS = "first_success"  # 取第一个成功结果
    STRUCTURED = "structured"        # 按 tool_name 分组结构化输出

@dataclass
class ToolAggregationResult:
    strategy: AggregationStrategy
    context_text: str              # 注入 LLM 的最终文本
    success_count: int
    error_count: int
    results: list[ToolResult]
    has_failure: bool

class ToolResultAggregator:
    def aggregate(
        self,
        results: list[ToolResult],
        strategy: AggregationStrategy = AggregationStrategy.CONCAT,
        locale: str = "zh-CN",
    ) -> ToolAggregationResult:
        """
        聚合工具执行结果
        
        CONCAT 示例：
        工具1结果
        工具2结果
        
        FIRST_SUCCESS 示例：
        工具1结果（只取第一个成功的）
        
        STRUCTURED 示例：
        【工具执行结果】
        [query_policy_basic]
        保单 P2024001 状态：有效
        
        [search_faq]
        理赔流程：...
        """
```

#### 4. `OrchestratorState` 扩展

```python
# core/agent_engine/workflows/state.py
class OrchestratorState(TypedDict):
    # 已有字段...
    tool_results: list[dict[str, Any]]   # 原始 ToolResult 列表
    tool_context: str                     # 汇总后注入 LLM 的文本
```

### 验收标准

- [ ] `run_batch` 并发执行 3 个工具，全部成功
- [ ] `run_batch` 中 1 个工具失败，其他 2 个成功
- [ ] `run_batch` 超时测试（timeout_seconds=1）
- [ ] `max_concurrency=2` 时最多同时执行 2 个工具
- [ ] 三种聚合策略单测（CONCAT / FIRST_SUCCESS / STRUCTURED）
- [ ] `locale="en-US"` 时标签为英文
- [ ] 全部工具失败时 `has_failure=True`

---

## Task 2.3 — plan_execute 集成 tools executor

**优先级**: P0  
**预计工时**: 3 天  
**依赖**: 2.1, 2.2  
**被依赖**: 无

### 目标

扩展 `plan_execute` graph，支持 `executor=tools` 模式，planner 可决策使用工具执行。

### 实现清单

#### 1. planner 决策扩展

`core/agent_engine/planners/types.py`：

```python
SubagentPlannerExecutor = Literal["llm", "subagents", "tools"]

@dataclass
class SubagentPlannerDecision:
    executor: SubagentPlannerExecutor
    selected_subagents: list[str] = field(default_factory=list)
    selected_tools: list[str] = field(default_factory=list)  # 新增
    aggregation_strategy: str = "structured"  # 新增
    # ... 其他字段
```

#### 2. `RuleSubagentPlannerProvider` 决策逻辑

```python
# core/agent_engine/planners/subagent_planner_provider.py
class RuleSubagentPlannerProvider:
    async def plan(self, state, config) -> list[dict]:
        meta = self._get_agent_meta(state)
        user_input = _last_human(state["messages"])
        
        # 决策优先级
        if meta.sub_agents and self._is_parallel_intent(user_input):
            return self._plan_subagents(meta, user_input)
        elif meta.tools and self._is_tool_intent(user_input):
            return self._plan_tools(meta, user_input)
        else:
            return self._plan_llm(user_input)
    
    def _plan_tools(self, meta: AgentMeta, user_input: str) -> list[dict]:
        """
        生成 tools 执行计划
        1. 从 meta.tools 中选择相关工具（简单实现：全选）
        2. 返回 executor="tools" 的 step
        """
        return [{
            "step_id": "step_1",
            "goal": user_input,
            "executor": "tools",
            "selected_tools": meta.tools,
            "aggregation_strategy": "structured",
        }]
    
    def _is_tool_intent(self, user_input: str) -> bool:
        """判断是否需要工具调用（关键词匹配）"""
        tool_keywords = ["查询", "搜索", "获取", "查找"]
        return any(kw in user_input for kw in tool_keywords)
```

#### 3. `plan_execute.py` executor 节点扩展

```python
# core/agent_engine/workflows/plan_execute.py
async def executor(state: OrchestratorState, config=None) -> dict:
    plan = state["plan"]
    if not plan:
        return {"plan": []}
    
    step = plan.pop(0)
    executor_type = step.get("executor", "llm")
    
    match executor_type:
        case "subagents":
            return await _execute_subagents_step(step, state, config)
        case "tools":
            return await _execute_tools_step(step, state, config)
        case _:
            return await _execute_llm_step(step, state)

async def _execute_tools_step(step: dict, state: OrchestratorState, config) -> dict:
    """
    执行 tools 步骤
    1. 从 step 中获取 selected_tools
    2. 调用 tool_executor_gateway.run_batch()
    3. 聚合结果
    4. 写入 tool_results 和 tool_context
    """
    tool_names = step.get("selected_tools", [])
    if not tool_names:
        return {"plan": state["plan"]}
    
    # 执行工具
    results = await tool_executor_gateway.run_batch(
        tool_names=tool_names,
        input_text=step.get("goal", ""),
        tenant_id=state["tenant_id"],
        conversation_id=state["conversation_id"],
    )
    
    # 聚合结果
    aggregated = tool_result_aggregator.aggregate(
        results,
        strategy=step.get("aggregation_strategy", AggregationStrategy.STRUCTURED),
        locale=state.get("locale", "zh-CN"),
    )
    
    # 失败降级：如果全部失败，下一轮 replanner 会切换为 llm
    return {
        "tool_results": [r.__dict__ for r in results],
        "tool_context": aggregated.context_text,
        "past_steps": [{
            "step_id": step["step_id"],
            "goal": step["goal"],
            "result": aggregated.context_text,
            "tool_results": [r.__dict__ for r in results],
            "has_failure": aggregated.has_failure,
        }],
        "step_count": state.get("step_count", 0) + 1,
        "plan": state["plan"],
    }
```

#### 4. `ContextInjector` 更新

```python
# core/agent_engine/context/injector.py
class ContextInjector:
    async def __call__(self, state, next_action):
        # ... 已有逻辑
        
        # 新增：注入 tool_context
        if state.get("tool_context"):
            system_parts.append(f"\n{state['tool_context']}")
        
        # ... 其他逻辑
```

### 验收标准

- [ ] planner 决策 `executor="tools"` 单测
- [ ] `_execute_tools_step` 执行成功，`tool_context` 正确写入
- [ ] 全部工具失败时，`has_failure=True`
- [ ] `tool_context` 注入 LLM 的 system prompt
- [ ] E2E 测试：用户输入 "查询保单 P001" → planner 选择 tools → 执行成功

---

## Task 2.4 — command graph ReAct 模式对齐

**优先级**: P1  
**预计工时**: 2 天  
**依赖**: 2.1  
**被依赖**: 无

### 目标

command graph（`base_agent.py`）保持 LangGraph `ToolNode` 的 ReAct 模式，但工具来源改为 tool_service。

### 实现清单

#### 1. `core/agent_engine/workflows/base_agent.py` 更新

```python
def build_base_agent(meta: AgentMeta, ...):
    # 从 tool_gateway 获取工具的可调用对象
    tool_callables = _build_tool_callables(meta.tools)
    tool_node = ToolNode(tool_callables)
    llm = llm_gateway.get_chat(tool_callables, scene=llm_scene)
    
    # ... 其他逻辑

def _build_tool_callables(tool_names: list[str]) -> list:
    """
    从 tool_gateway 的注册表中获取工具，
    包装为 LangChain tool 格式（供 ToolNode 使用）
    
    实现：
    1. 遍历 tool_names
    2. 从 tool_registry.list_tools() 获取 ToolMeta
    3. 包装为 LangChain StructuredTool
    """
    from langchain_core.tools import StructuredTool
    
    tools = []
    for tool_name in tool_names:
        meta = tool_registry.get_tool_meta(tool_name)
        if not meta:
            continue
        
        # 创建异步调用函数
        async def _invoke(args: dict, tool_name=tool_name):
            result = await tool_gateway.invoke(tool_name, args)
            if result.status == "error":
                raise Exception(result.error)
            return result.output
        
        tool = StructuredTool(
            name=meta.name,
            description=meta.description,
            coroutine=_invoke,
            args_schema=meta.input_schema,
        )
        tools.append(tool)
    
    return tools
```

#### 2. `ToolRegistry` 增加 `get_tool_meta` 方法

```python
# core/tool_service/registry.py
class ToolRegistry:
    def get_tool_meta(self, tool_name: str) -> ToolMeta | None:
        """根据 tool_name 获取工具元信息"""
        return self._tools.get(tool_name)
```

### 验收标准

- [ ] `_build_tool_callables` 单测（返回 LangChain tool 列表）
- [ ] command graph 通过 tool_gateway 调用工具的 E2E 测试
- [ ] LLM 主动发起 tool_call → ToolNode 执行 → 结果回到 LLM
- [ ] 工具执行失败时 LLM 收到错误信息

---

## 架构防腐门禁

每个 Task 完成时检查：

- [ ] `domain_agents` 不直接 import 工具函数
- [ ] `ToolCandidate.tool` 类型为 `str`
- [ ] 所有工具执行通过 `tool_gateway.invoke()` 路由
- [ ] `AgentMeta.tools` 存储 `tool_name` 字符串列表

---

## Batch 2 完成标志

- [ ] 所有 Task 验收标准通过
- [ ] 集成测试：plan_execute 和 command graph 都能正确调用工具
- [ ] 性能测试：3 个工具并发执行 P95 < 2s
- [ ] 文档：Tool 注册和执行流程文档
