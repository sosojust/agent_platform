# Batch 3 — AI 能力层 + Prompt 统一治理开发任务

## 概述

AI 能力层包含 Prompt 多语言支持、LLM Gateway 补齐、Agent State 重构，是国际化能力的最终落地层。

**前置依赖**: Batch 1 + Batch 2 完成

---

## Task 3.1 — PromptGateway 多语扩展

**优先级**: P0  
**预计工时**: 4 天  
**依赖**: 1.2（i18n 基础层）  
**被依赖**: 3.3

### 目标

扩展 `PromptGateway`，支持多语言 prompt 管理，消除所有硬编码 prompt，建立 Langfuse + 本地文件的双层 fallback 机制。

### 实现清单

#### 1. `core/ai_core/prompt/gateway.py` 接口扩展

```python
class PromptGateway:
    def get(
        self,
        name: str,
        variables: dict | None = None,
        locale: str | None = None,
        version: str | None = None,
    ) -> str:
        """
        查找顺序：
        1. Langfuse: {name}_{locale}
        2. Langfuse: {name}_{fallback_locale}
        3. Langfuse: {name}
        4. 本地文件: prompts/{locale}/{name}.txt
        5. 本地文件: prompts/{fallback_locale}/{name}.txt
        6. 本地文件: prompts/{DEFAULT_LOCALE}/{name}.txt
        
        locale 不传则从 current_locale() 读取
        缓存 key 改为 {name}:{locale}:{version}
        """
```

实现逻辑：

```python
def get(self, name: str, variables: dict | None = None, locale: str | None = None, version: str | None = None) -> str:
    locale = locale or get_current_locale()
    cache_key = f"{name}:{locale}:{version or 'latest'}"
    
    # 检查缓存
    if cached := self._cache.get(cache_key):
        return self._render(cached, variables)
    
    # 尝试 Langfuse
    fallback_chain = get_fallback_chain(locale)
    for loc in fallback_chain:
        if prompt := self._fetch_from_langfuse(f"{name}_{loc}", version):
            self._cache[cache_key] = prompt
            return self._render(prompt, variables)
    
    # 尝试 Langfuse 无 locale 后缀
    if prompt := self._fetch_from_langfuse(name, version):
        self._cache[cache_key] = prompt
        return self._render(prompt, variables)
    
    # 尝试本地文件
    for loc in fallback_chain:
        if prompt := self._load_local_file(name, loc):
            self._cache[cache_key] = prompt
            return self._render(prompt, variables)
    
    raise PromptNotFoundError(f"Prompt {name} not found for locale {locale}")

def _load_local_file(self, name: str, locale: str) -> str | None:
    """从本地文件加载 prompt"""
    path = Path(__file__).parent / "prompts" / locale / f"{name}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None
```

#### 2. 本地 prompt 文件目录重构

```
core/ai_core/prompt/prompts/
├── zh-CN/
│   ├── memory_extractor_sys.txt
│   ├── memory_compressor_summary_sys.txt
│   ├── plan_execute_planner_sys.txt
│   ├── plan_execute_executor_sys.txt
│   ├── plan_execute_finalize_sys.txt
│   ├── subagent_planner_sys.txt
│   ├── tool_router_select_sys.txt
│   ├── tool_router_select_user.txt
│   └── query_rewriter_sys.txt
├── en-US/
│   ├── memory_extractor_sys.txt
│   ├── memory_compressor_summary_sys.txt
│   ├── plan_execute_planner_sys.txt
│   ├── plan_execute_executor_sys.txt
│   ├── plan_execute_finalize_sys.txt
│   ├── subagent_planner_sys.txt
│   ├── tool_router_select_sys.txt
│   ├── tool_router_select_user.txt
│   └── query_rewriter_sys.txt
└── ja-JP/
    └── ...（按需）
```

domain system prompt 目录：

```
domain_agents/{domain}/prompts/
├── zh-CN/
│   └── system.txt
├── en-US/
│   └── system.txt
└── ja-JP/
    └── system.txt
```

#### 3. 硬编码 prompt 迁移清单

| 当前位置 | Prompt Key | 迁移目标 |
| --- | --- | --- |
| `memory/extractor.py` `SYSTEM_PROMPT` | `memory_extractor_sys` | `prompts/zh-CN/memory_extractor_sys.txt` |
| `memory/compressor.py` 摘要指令 | `memory_compressor_summary_sys` | `prompts/zh-CN/memory_compressor_summary_sys.txt` |
| `tools/router.py` fallback | `tool_router_select_sys` / `tool_router_select_user` | `prompts/zh-CN/tool_router_select_*.txt` |
| `plan_execute.py` planner | `plan_execute_planner_sys` | `prompts/zh-CN/plan_execute_planner_sys.txt` |
| `plan_execute.py` executor | `plan_execute_executor_sys` | `prompts/zh-CN/plan_execute_executor_sys.txt` |
| `plan_execute.py` finalize | `plan_execute_finalize_sys` | `prompts/zh-CN/plan_execute_finalize_sys.txt` |
| `subagent_planner_provider.py` | `subagent_planner_sys` | `prompts/zh-CN/subagent_planner_sys.txt` |
| `retrieval/rewriter.py` | `query_rewriter_sys` | `prompts/zh-CN/query_rewriter_sys.txt` |

迁移步骤：

1. 创建 `prompts/zh-CN/{name}.txt` 文件，复制原硬编码内容
2. 创建 `prompts/en-US/{name}.txt` 文件，提供英文翻译
3. 修改原代码，改为 `prompt_gateway.get("{name}", locale=locale)`
4. 删除硬编码字符串

#### 4. domain_agents prompt 迁移

以 `insurance` domain 为例：

```python
# domain_agents/insurance/agent.py
# 旧代码
SYSTEM_PROMPT = """你是保险领域的专业助手..."""

# 新代码
system_prompt = prompt_gateway.get(
    "insurance_agent_system",
    locale=state.get("locale", "zh-CN"),
)
```

创建文件：

```
domain_agents/insurance/prompts/
├── zh-CN/
│   └── system.txt  # 内容：你是保险领域的专业助手...
├── en-US/
│   └── system.txt  # 内容：You are a professional insurance assistant...
```

`PromptGateway` 增加 domain prompt 加载逻辑：

```python
def _load_local_file(self, name: str, locale: str) -> str | None:
    # 先尝试 core prompt
    path = Path(__file__).parent / "prompts" / locale / f"{name}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    
    # 尝试 domain prompt（格式：{domain}_agent_system）
    if "_agent_system" in name:
        domain = name.replace("_agent_system", "")
        domain_path = Path(__file__).parent.parent.parent / "domain_agents" / domain / "prompts" / locale / "system.txt"
        if domain_path.exists():
            return domain_path.read_text(encoding="utf-8")
    
    return None
```

### 验收标准

- [ ] `get("memory_extractor_sys", locale="zh-CN")` 返回中文 prompt
- [ ] `get("memory_extractor_sys", locale="en-US")` 返回英文 prompt
- [ ] `get("memory_extractor_sys", locale="ja-JP")` fallback 到中文
- [ ] Langfuse 不可用时本地文件兜底
- [ ] 缓存 key 包含 locale
- [ ] 所有硬编码 prompt 已迁移（代码中无多行字符串 prompt）
- [ ] domain prompt 加载测试（`insurance_agent_system`）
- [ ] 变量插值测试：`get("test", variables={"name": "value"})`

---

## Task 3.2 — LLM Gateway 补齐

**优先级**: P1  
**预计工时**: 2 天  
**依赖**: 1.2（i18n 基础层）  
**被依赖**: 无

### 目标

LLM Gateway 透传 `locale` 到 metadata，错误信息国际化。

### 实现清单

#### 1. `core/ai_core/llm/gateway.py` 更新

```python
class LLMGateway:
    async def complete(
        self,
        messages: list[dict],
        *,
        scene: str = "default",
        locale: str | None = None,
        **kwargs,
    ) -> dict:
        """
        locale 透传到 metadata，便于 Langfuse 按语言维度分析
        """
        locale = locale or get_current_locale()
        metadata = kwargs.get("metadata", {})
        metadata["locale"] = locale
        metadata["tenant_id"] = get_current_tenant_id()
        metadata["user_id"] = get_current_user_id()
        metadata["channel_id"] = get_current_channel_id()
        kwargs["metadata"] = metadata
        
        try:
            return await self._complete(messages, scene=scene, **kwargs)
        except Exception as e:
            # 错误信息国际化
            error_key = self._map_error_to_key(e)
            raise LLMError(t(error_key, locale=locale)) from e
    
    def _map_error_to_key(self, error: Exception) -> str:
        """映射异常到 i18n key"""
        if "timeout" in str(error).lower():
            return "error.provider_timeout"
        elif "rate" in str(error).lower():
            return "error.provider_rate_limited"
        else:
            return "error.provider_unknown"
```

#### 2. `shared/i18n/locales/zh-CN.json` 补充错误文案

```json
{
  "error.provider_timeout": "模型响应超时，请稍后重试",
  "error.provider_rate_limited": "请求过于频繁，请稍后重试",
  "error.provider_unknown": "模型服务异常，请稍后重试",
  "error.provider_context_length": "输入内容过长，请精简后重试"
}
```

`en-US.json` 提供对应翻译。

#### 3. `stream` 方法同步更新

```python
async def stream(
    self,
    messages: list[dict],
    *,
    scene: str = "default",
    locale: str | None = None,
    **kwargs,
) -> AsyncIterator[dict]:
    locale = locale or get_current_locale()
    metadata = kwargs.get("metadata", {})
    metadata["locale"] = locale
    # ... 其他 metadata
    kwargs["metadata"] = metadata
    
    try:
        async for chunk in self._stream(messages, scene=scene, **kwargs):
            yield chunk
    except Exception as e:
        error_key = self._map_error_to_key(e)
        raise LLMError(t(error_key, locale=locale)) from e
```

### 验收标准

- [ ] `complete` 调用时 metadata 包含 `locale`
- [ ] `locale="en-US"` 时超时错误为英文
- [ ] `locale="zh-CN"` 时超时错误为中文
- [ ] Langfuse trace 中可按 locale 过滤

---

## Task 3.3 — Agent State 和节点重构

**优先级**: P0  
**预计工时**: 4 天  
**依赖**: 1.1, 1.2, 1.6, 1.7, 2.1, 3.1  
**被依赖**: 无

### 目标

扩展 `AgentState`，合并检索节点，更新 `ContextInjector`，支持完整的国际化和工具执行上下文注入。

### 实现清单

#### 1. `core/agent_engine/workflows/state.py` 扩展

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    conversation_id: str
    tenant_id: str
    tenant_type: str     # 新增
    channel_id: str      # 新增
    user_id: str         # 新增
    locale: str          # 新增
    timezone: str        # 新增
    memory_context: str
    rag_context: str
    tool_results: list[dict]    # 新增
    tool_context: str           # 新增
    step_count: int
    metadata: dict[str, Any]

class OrchestratorState(AgentState):
    plan: list[dict]
    past_steps: list[dict]
    # ... 其他字段
```

#### 2. 检索节点合并

`core/agent_engine/workflows/nodes.py`：

```python
def make_retrieve_node(config: MemoryConfig, plan: RetrievalPlan):
    """
    合并 retrieve_memory 和 retrieve_rag 为单个 retrieve 节点
    内部并发执行
    """
    async def retrieve(state: AgentState) -> dict:
        query = _last_human(state["messages"])
        
        # 并发执行 memory 和 rag 检索
        memory_task = memory_gateway.build_context(
            query=query,
            conversation_id=state["conversation_id"],
            user_id=state["user_id"],
            tenant_id=state["tenant_id"],
            channel_id=state["channel_id"],
            locale=state.get("locale", "zh-CN"),
            config=config,
            retrieval_plan=plan,
        )
        
        rag_task = retrieval_gateway.retrieve(
            query=query,
            user_id=state["user_id"],
            tenant_id=state["tenant_id"],
            channel_id=state["channel_id"],
            plan=plan,
        )
        
        memory_ctx, rag_result = await asyncio.gather(memory_task, rag_task)
        
        return {
            "memory_context": memory_ctx,
            "rag_context": rag_result.as_context_string(
                locale=state.get("locale", "zh-CN")
            ),
        }
    
    return retrieve
```

#### 3. `ContextInjector` 更新

```python
# core/agent_engine/context/injector.py
class ContextInjector:
    def __init__(self, system_prompt_key: str):
        self.system_prompt_key = system_prompt_key
    
    async def __call__(self, state: AgentState, next_action):
        locale = state.get("locale", "zh-CN")
        
        # 1. 获取 system prompt（多语言）
        system_parts = [
            prompt_gateway.get(
                self.system_prompt_key,
                variables={"tenant_id": state.get("tenant_id")},
                locale=locale,
            )
        ]
        
        # 2. 注入 memory_context
        if state.get("memory_context"):
            system_parts.append(f"\n{state['memory_context']}")
        
        # 3. 注入 rag_context
        if state.get("rag_context"):
            system_parts.append(f"\n{state['rag_context']}")
        
        # 4. 注入 tool_context
        if state.get("tool_context"):
            system_parts.append(f"\n{state['tool_context']}")
        
        # 5. 非默认语言时追加语言指令
        if locale != DEFAULT_LOCALE:
            lang_name = LOCALE_LANGUAGE_NAME.get(locale, locale)
            system_parts.append(
                f"\n{t('instruction.respond_in_locale', locale=locale, language=lang_name)}"
            )
        
        system_prompt = "\n".join(system_parts)
        
        # 注入到 messages
        messages = state["messages"].copy()
        if messages and isinstance(messages[0], SystemMessage):
            messages[0] = SystemMessage(content=system_prompt)
        else:
            messages.insert(0, SystemMessage(content=system_prompt))
        
        return await next_action({**state, "messages": messages})
```

`LOCALE_LANGUAGE_NAME` 映射：

```python
# shared/i18n/locale.py
LOCALE_LANGUAGE_NAME = {
    "zh-CN": "中文",
    "en-US": "English",
    "ja-JP": "日本語",
}
```

#### 4. `agents.py` 路由层更新

```python
# core/agent_engine/agents.py
async def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    # 初始化 state
    initial_state = make_initial_state(
        messages=[HumanMessage(content=request.input)],
        conversation_id=conversation_id,
        tenant_id=get_current_tenant_id(),
        tenant_type=get_current_tenant_type(),
        channel_id=get_current_channel_id(),
        user_id=get_current_user_id(),
        locale=get_current_locale(),
        timezone=get_current_timezone(),
    )
    
    # ... 其他逻辑
```

#### 5. Graph 构建更新

```python
# core/agent_engine/workflows/base_agent.py
def build_base_agent(meta: AgentMeta, ...):
    graph = StateGraph(AgentState)
    
    # 合并后的检索节点
    retrieve_node = make_retrieve_node(memory_config, retrieval_plan)
    graph.add_node("retrieve", retrieve_node)
    
    # 注入节点
    inject_node = ContextInjector(system_prompt_key=f"{meta.name}_system")
    graph.add_node("inject", inject_node)
    
    # ... 其他节点
    
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "inject")
    graph.add_edge("inject", "agent")
    # ...
```

### 验收标准

- [ ] State 全字段透传 E2E 测试
- [ ] `locale="en-US"` 时 system prompt 为英文
- [ ] `locale="en-US"` 时语言指令为 "Please respond in English."
- [ ] `tool_context` 正确注入 system prompt
- [ ] 检索节点并发执行测试（memory + rag）
- [ ] `rag_context` 的 `as_context_string(locale="en-US")` 标签为英文
- [ ] 完整流程测试：用户输入 → 检索 → 注入 → LLM 回答

---

## 架构防腐门禁

每个 Task 完成时检查：

- [ ] 所有 prompt 字符串不在 `ai_core/prompt/` 和 `domain_agents/*/prompts/` 目录外硬编码
- [ ] LLM SDK 只出现在 `ai_core/llm/`
- [ ] `core/` 和 `shared/` 不反向依赖 `domain_agents/`

---

## Batch 3 完成标志

- [ ] 所有 Task 验收标准通过
- [ ] 集成测试：完整流程（中文/英文/日文）
- [ ] 性能测试：prompt 加载 P95 < 50ms（含缓存）
- [ ] 文档：Prompt 管理和国际化指南
